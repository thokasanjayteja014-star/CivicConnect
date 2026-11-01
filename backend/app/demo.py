"""Separate demonstration environment.

Everything here runs against the isolated demo schema (see app.core.environment). The
sample data is clearly marked PROTOTYPE and never touches production tables. The seed
goes through the real services (routing, auto-assignment, escalation, public issues), so
the demo behaves exactly like production.

  python -m app.demo ensure   # create + migrate + seed the demo schema if empty (startup)
  python -m app.demo reset    # drop and rebuild the demo schema (never touches production)
"""
from __future__ import annotations

import io
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text, update

from app.core.config import get_settings
from app.core.db import SessionLocal, get_engine, reset_engine
from app.core.environment import DEMO, PRODUCTION, is_demo, use_env
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.models import (
    Assignment,
    Complaint,
    ComplaintRemark,
    Department,
    DepartmentUnit,
    Jurisdiction,
    Officer,
    OfficerArea,
    PublicIssue,
    PublicIssueComplaint,
    PublicIssueUpdate,
    ResponsibilityRule,
    StatusHistory,
    User,
)
from app.models.enums import (
    AccountStatus,
    Category,
    ComplaintStatus as S,
    PublicIssueProgress,
    PublicIssueStatus,
    Role,
    VerificationDecisionType,
    VerificationStatus,
)
from app.security import create_access_token, hash_password

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_lock = threading.Lock()

DEMO_USERS = {
    "SYSTEM_ADMIN": "admin@demo.civicconnect",
    "DEPARTMENT_ADMIN": "roads.admin@demo.civicconnect",
    "OFFICER": "roads.officer1@demo.civicconnect",
    "CITIZEN": "citizen@demo.civicconnect",
}


# ---------------- schema management ----------------
def _schema() -> str:
    return get_settings().DEMO_SCHEMA


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    cfg.attributes["schema"] = _schema()
    command.upgrade(cfg, "head")


def _drop_schema() -> None:
    reset_engine(DEMO)
    with get_engine(PRODUCTION).begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{_schema()}" CASCADE'))


def ensure(seed_if_empty: bool = True) -> bool:
    """Create, migrate and (if empty) seed the demo schema. Returns True when it seeded."""
    with _lock:
        _migrate()
        with use_env(DEMO):
            db = SessionLocal()
            try:
                empty = not db.scalar(select(func.count()).select_from(User))
            finally:
                db.close()
            if empty and seed_if_empty:
                seed()
                return True
    return False


def reset() -> None:
    with _lock:
        _drop_schema()
        _migrate()
        with use_env(DEMO):
            seed()
    _clear_demo_media()


def _clear_demo_media() -> None:
    from app.services.storage import get_storage

    st = get_storage()
    if str(getattr(st, "kind", "")).startswith("local"):
        import shutil
        shutil.rmtree(os.path.join(str(st.root), "demo"), ignore_errors=True)


# ---------------- sample data ----------------
def _rect(lng1, lat1, lng2, lat2) -> dict:
    return {"type": "Polygon", "coordinates": [[[lng1, lat1], [lng2, lat1], [lng2, lat2], [lng1, lat2], [lng1, lat1]]]}


def _png(shade: int) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (shade, shade, shade)).save(buf, "PNG")
    return buf.getvalue()


@contextmanager
def _no_ai():
    """The seed must not call external AI services."""
    from app.ai import ai_service
    original = ai_service.generate_text_embedding
    ai_service.generate_text_embedding = lambda *a, **k: None
    try:
        yield
    finally:
        ai_service.generate_text_embedding = original


def seed() -> None:
    assert is_demo(), "seed() must run inside the demo environment"
    from app.geospatial import geojson_to_geometry
    from app.schemas import ComplaintCreate
    from app.security.deps import build_actor
    from app.services import workflow
    from app.services.complaints import create_complaint
    from app.services.escalation import run_overdue_escalations, set_due_at

    db = SessionLocal()
    try:
        P = VerificationStatus.PROTOTYPE
        src = "Demonstration sample data (not an official record)"

        def juris(name, jtype, parent, boundary):
            j = Jurisdiction(name=name, jurisdiction_type=jtype, parent_id=parent.id if parent else None,
                             boundary=geojson_to_geometry(db, boundary), is_prototype=True, verification_status=P,
                             source_reference=src, description="Sample jurisdiction for the demonstration environment.")
            db.add(j)
            db.flush()
            return j

        state = juris("Karnataka", "STATE", None, _rect(74.0, 15.0, 76.0, 16.5))
        dharwad = juris("Dharwad District", "DISTRICT", state, _rect(74.8, 15.2, 75.4, 15.7))
        hdmc = juris("Hubballi-Dharwad Municipal Corporation", "MUNICIPAL_CORPORATION", dharwad, _rect(74.97, 15.42, 75.09, 15.49))
        w1 = juris("Ward 1 – Vidyagiri", "WARD", hdmc, _rect(74.97, 15.42, 75.0, 15.49))
        w2 = juris("Ward 2 – Saptapur", "WARD", hdmc, _rect(75.0, 15.42, 75.03, 15.49))
        w3 = juris("Ward 3 – Malmaddi", "WARD", hdmc, _rect(75.03, 15.42, 75.06, 15.49))
        # Ward 4 has no officer yet: its complaints wait in the department administrator's unassigned queue.
        juris("Ward 4 – Gokul Road", "WARD", hdmc, _rect(75.06, 15.42, 75.09, 15.49))
        belagavi = juris("Belagavi District", "DISTRICT", state, _rect(74.3, 15.7, 74.8, 16.1))
        bcc = juris("Belagavi City Corporation", "MUNICIPAL_CORPORATION", belagavi, _rect(74.45, 15.82, 74.56, 15.9))
        juris("Ward 10 – Tilakwadi", "WARD", bcc, _rect(74.48, 15.83, 74.53, 15.87))

        def dept(name, category, desc, cats):
            d = Department(name=name, category=category, description=desc, is_prototype=True, verification_status=P,
                           source_reference=src)
            db.add(d)
            db.flush()
            for cat, label in cats:
                db.add(ResponsibilityRule(department_id=d.id, category=cat, name=label, active=True, verified=False,
                                          verification_status=P, source_reference=src))
            return d

        roads = dept("Roads & Infrastructure", "Engineering", "Road surfaces, footpaths and public works.",
                     [(Category.ROAD_INFRASTRUCTURE, "Pothole and road surface repair"),
                      (Category.PUBLIC_INFRASTRUCTURE, "Footpaths and public structures")])
        water = dept("Water Supply", "Utilities", "Drinking water distribution and leak repair.",
                     [(Category.WATER_SUPPLY, "Pipeline leaks and supply interruptions")])
        sanitation = dept("Solid Waste & Sanitation", "Public health", "Garbage collection and street cleaning.",
                          [(Category.SANITATION, "Garbage collection")])
        drainage = dept("Storm Water Drainage", "Engineering", "Drains, culverts and flooding.",
                        [(Category.DRAINAGE, "Drain blockage and overflow")])
        lights = dept("Street Lighting", "Electrical", "Streetlight installation and repair.",
                      [(Category.STREETLIGHT, "Streetlight repair")])

        def unit(d, j):
            u = DepartmentUnit(department_id=d.id, jurisdiction_id=j.id)
            db.add(u)
            db.flush()
            return u

        u_roads = unit(roads, hdmc)
        u_water = unit(water, hdmc)
        unit(sanitation, hdmc)
        unit(drainage, hdmc)
        u_lights = unit(lights, hdmc)
        u_roads_bgm = unit(roads, bcc)

        pw = hash_password(uuid.uuid4().hex)

        def user(name, email, role, u=None, designation=None, areas=()):
            x = User(full_name=name, email=email, password_hash=pw, role=role, account_status=AccountStatus.ACTIVE,
                     notify_email=False, notify_sms=False, notify_push=False)
            db.add(x)
            db.flush()
            o = None
            if u is not None:
                o = Officer(user_id=x.id, department_id=u.department_id, unit_id=u.id, designation=designation)
                db.add(o)
                db.flush()
                for a in areas:
                    db.add(OfficerArea(officer_id=o.id, jurisdiction_id=a.id))
            db.flush()
            return x, o

        admin, _ = user("Demo Main Administrator", DEMO_USERS["SYSTEM_ADMIN"], Role.SYSTEM_ADMIN)
        dadmin, _ = user("Asha Kulkarni", DEMO_USERS["DEPARTMENT_ADMIN"], Role.DEPARTMENT_ADMIN, u_roads, "Executive Engineer (Roads)")
        off1, o1 = user("Ravi Patil", DEMO_USERS["OFFICER"], Role.OFFICER, u_roads, "Assistant Engineer", (w1, w2))
        off2, o2 = user("Meena Desai", "roads.officer2@demo.civicconnect", Role.OFFICER, u_roads, "Assistant Engineer", (w3,))
        user("Suresh Hegde", "water.admin@demo.civicconnect", Role.DEPARTMENT_ADMIN, u_water, "Executive Engineer (Water)")
        woff, _ = user("Imran Shaikh", "water.officer@demo.civicconnect", Role.OFFICER, u_water, "Junior Engineer")
        user("Kavya Rao", "lights.officer@demo.civicconnect", Role.OFFICER, u_lights, "Electrical Inspector")
        user("Prakash Joshi", "belagavi.roads.admin@demo.civicconnect", Role.DEPARTMENT_ADMIN, u_roads_bgm,
             "Executive Engineer (Roads, Belagavi)")
        citizen, _ = user("Demo Citizen", DEMO_USERS["CITIZEN"], Role.CITIZEN)
        cit2, _ = user("Lakshmi N.", "citizen2@demo.civicconnect", Role.CITIZEN)
        cit3, _ = user("Arjun M.", "citizen3@demo.civicconnect", Role.CITIZEN)
        db.commit()

        actor = lambda u: build_actor(db, db.get(User, u.id))  # noqa: E731

        def complain(who, title, desc, cat, lat, lng, landmark, days_ago, sev="MODERATE", risk="LOW", exp="STREET"):
            payload = ComplaintCreate(
                title=title, description=desc, original_description=desc, category=cat, confirmed=True,
                location={"latitude": lat, "longitude": lng, "location_source": "MAP_SELECTION", "landmark": landmark},
                observed_severity=sev, safety_risk=risk, public_exposure=exp)
            c, _, _, _ = create_complaint(db, actor(who), payload, None)
            db.commit()
            return c, days_ago

        made = []
        with _no_ai():
            made.append(complain(citizen, "Deep pothole near Vidyagiri bus stop",
                                 "A deep pothole has formed right next to the bus stop. Two-wheelers swerve into traffic to avoid it.",
                                 Category.ROAD_INFRASTRUCTURE, 15.455, 74.985, "Vidyagiri bus stop", 16, "SEVERE", "SIGNIFICANT", "NEIGHBOURHOOD"))
            made.append(complain(citizen, "Road surface broken on PB Road",
                                 "The tar surface has broken up over about 20 metres after the rains.",
                                 Category.ROAD_INFRASTRUCTURE, 15.462, 74.992, "PB Road, near petrol pump", 6))
            made.append(complain(cit2, "Potholes on Station Road",
                                 "Several potholes on Station Road between the circle and the railway gate.",
                                 Category.ROAD_INFRASTRUCTURE, 15.448, 75.012, "Station Road", 4, "SEVERE", "MODERATE", "NEIGHBOURHOOD"))
            made.append(complain(cit3, "Station Road potholes causing traffic jams",
                                 "Vehicles slow down near the railway gate because of potholes; traffic backs up every evening.",
                                 Category.ROAD_INFRASTRUCTURE, 15.4485, 75.0125, "Station Road railway gate", 3, "SEVERE", "MODERATE", "NEIGHBOURHOOD"))
            made.append(complain(cit2, "Broken footpath slab near Malmaddi school",
                                 "A footpath slab is broken and children have to walk on the road.",
                                 Category.PUBLIC_INFRASTRUCTURE, 15.444, 75.045, "Malmaddi Government School", 15, "MODERATE", "SIGNIFICANT", "STREET"))
            made.append(complain(citizen, "Water pipeline leaking for three days",
                                 "Clean water has been leaking from a pipeline joint for three days and the road is flooded.",
                                 Category.WATER_SUPPLY, 15.466, 75.021, "Saptapur 2nd cross", 3))
            made.append(complain(cit3, "Garbage not collected this week",
                                 "Garbage has not been collected from our lane for six days.",
                                 Category.SANITATION, 15.452, 75.05, "Malmaddi 4th cross", 2))
            made.append(complain(cit2, "Drain overflowing onto the road",
                                 "The roadside drain overflows whenever it rains and water enters houses.",
                                 Category.DRAINAGE, 15.471, 75.008, "Saptapur main road", 1, "SEVERE", "MODERATE", "STREET"))
            made.append(complain(citizen, "Stray cattle on the main road",
                                 "Stray cattle sit in the middle of the main road at night.",
                                 Category.OTHER, 15.458, 75.002, "Near Saptapur circle", 2))
            made.append(complain(cit3, "Pothole at Tilakwadi first gate",
                                 "Large pothole at the first railway gate in Tilakwadi.",
                                 Category.ROAD_INFRASTRUCTURE, 15.85, 74.505, "Tilakwadi first gate", 5))
            made.append(complain(citizen, "Streetlight not working",
                                 "The streetlight outside house number 14 has not worked for two weeks.",
                                 Category.STREETLIGHT, 15.459, 74.988, "Vidyagiri 3rd cross", 9))
            made.append(complain(cit2, "Speed breaker damaged on Gokul Road",
                                 "The speed breaker near the bus depot has broken apart and loose stones are scattered on the road.",
                                 Category.ROAD_INFRASTRUCTURE, 15.455, 75.075, "Gokul Road bus depot", 1))
            # Three streetlight reports close together: CivicConnect groups them into an automatic public issue.
            made.append(complain(cit2, "Street lights off on Vidyagiri 3rd cross",
                                 "Two street lights on the 3rd cross are off and the lane is completely dark at night.",
                                 Category.STREETLIGHT, 15.4594, 74.9884, "Vidyagiri 3rd cross", 4))
            made.append(complain(cit3, "Dark lane near Vidyagiri park",
                                 "The lights along the lane next to the park have not worked for over a week.",
                                 Category.STREETLIGHT, 15.4587, 74.9878, "Vidyagiri park", 2))
            made.append(complain(citizen, "Streetlight pole lamp broken",
                                 "The lamp on the pole at the corner of the 3rd cross is broken and hangs loose.",
                                 Category.STREETLIGHT, 15.4590, 74.9890, "Corner of Vidyagiri 3rd cross", 1))

        c_resolved, c_progress, c_st1, c_st2, c_foot, c_water = (m[0] for m in made[:6])
        c_light = made[10][0]
        # Officer work: accept, progress, evidence, resolution, verification
        for c in (c_resolved, c_progress):
            workflow.accept_assignment(db, actor(off1), c.id)
            workflow.change_status(db, actor(off1), c.id, S.IN_PROGRESS, reason=None, remarks="Inspection done, repair scheduled.", internal_note=None, expected_version=None)
        ev = workflow.upload_evidence(db, actor(off1), c_resolved.id, _png(90), "after-repair.png", "Pothole filled and levelled.")
        workflow.change_status(db, actor(off1), c_resolved.id, S.RESOLVED_AWAITING_VERIFICATION, reason=None, remarks="Pothole filled with hot mix and compacted.", internal_note=None, expected_version=None)
        workflow.verify_resolution(db, actor(dadmin), c_resolved.id, VerificationDecisionType.APPROVED,
                                   "Site photo reviewed; repair is satisfactory.", [ev.id], None)
        workflow.accept_assignment(db, actor(woff), c_water.id)
        workflow.change_status(db, actor(woff), c_water.id, S.IN_PROGRESS, reason=None, remarks="Valve closed; joint replacement scheduled.", internal_note=None, expected_version=None)
        lofficer = db.scalar(select(User).where(User.email == "lights.officer@demo.civicconnect"))
        workflow.change_status(db, actor(lofficer), c_light.id, S.REJECTED, reason="Duplicate of an existing streetlight repair request.", remarks=None, internal_note=None, expected_version=None)

        # Backdate to give the overview real history (shift every timestamp of the complaint uniformly).
        now = datetime.now(timezone.utc)
        for c, days in made:
            delta = timedelta(days=days, hours=3)
            db.execute(update(StatusHistory).where(StatusHistory.complaint_id == c.id)
                       .values(created_at=StatusHistory.created_at - delta))
            db.execute(update(Assignment).where(Assignment.complaint_id == c.id).values(assigned_at=Assignment.assigned_at - delta))
            db.execute(update(ComplaintRemark).where(ComplaintRemark.complaint_id == c.id)
                       .values(created_at=ComplaintRemark.created_at - delta))
            row = db.get(Complaint, c.id)
            row.created_at = row.created_at - delta
            row.updated_at = now - timedelta(days=max(days - 1, 0))
            set_due_at(db, row)
            # Spread later workflow steps over the complaint's life so durations look like real work.
            hist = db.scalars(select(StatusHistory).where(StatusHistory.complaint_id == c.id)
                              .order_by(StatusHistory.created_at, StatusHistory.id)).all()
            steps = hist[1:]  # the first entry is the submission itself
            for i, h in enumerate(steps, start=1):
                h.created_at = row.created_at + timedelta(hours=days * 24 * 0.75 * i / len(steps))
        db.commit()
        run_overdue_escalations(db)

        # Public issue: two Station Road complaints, verified and published
        issue = PublicIssue(title="Potholes on Station Road", general_location="Station Road, Saptapur (Ward 2)",
                            description="Several potholes between Station Road circle and the railway gate are slowing traffic.",
                            category=Category.ROAD_INFRASTRUCTURE, department_id=roads.id, department_unit_id=u_roads.id,
                            jurisdiction_id=w2.id, latitude=15.448, longitude=75.012, created_by=off1.id,
                            impact_level="HIGH", impact_assessment="Main access road to the railway station; heavy daily traffic.",
                            status=PublicIssueStatus.PUBLISHED, progress=PublicIssueProgress.IN_PROGRESS,
                            verified_by=dadmin.id, verified_at=now - timedelta(days=2),
                            published_by=dadmin.id, published_at=now - timedelta(days=2))
        db.add(issue)
        db.flush()
        for c in (c_st1, c_st2):
            db.add(PublicIssueComplaint(issue_id=issue.id, complaint_id=c.id, linked_by=off1.id))
        db.add(PublicIssueUpdate(issue_id=issue.id, message="Inspection completed; resurfacing work order issued.",
                                 progress=PublicIssueProgress.IN_PROGRESS, author_id=dadmin.id,
                                 created_at=now - timedelta(days=1)))
        db.commit()
        from app.services.auto_issues import run_auto_public_issues
        run_auto_public_issues(db)
        _ = (o1, o2, c_foot)
    finally:
        db.close()


# ---------------- API ----------------
router = APIRouter(prefix="/api/demo", tags=["demo"])


class DemoLogin(BaseModel):
    role: Role


def _require_demo():
    if not get_settings().DEMO_ENABLED:
        raise err("NOT_FOUND")
    if not is_demo():
        raise err("FORBIDDEN", message="This action is only available in the demonstration environment.")


@router.get("/status")
def status():
    s = get_settings()
    return {"enabled": s.DEMO_ENABLED, "environment": DEMO if is_demo() else PRODUCTION,
            "banner": "DEMONSTRATION ENVIRONMENT – SAMPLE DATA" if is_demo() else None,
            "roles": list(DEMO_USERS) if s.DEMO_ENABLED else []}


@router.post("/login", dependencies=[Depends(rate_limit("demo-login", "RATE_LIMIT_AUTH"))])
def demo_login(body: DemoLogin):
    """Sign in as the sample user of a role. Only works inside the demo environment."""
    _require_demo()
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.email == DEMO_USERS[body.role.value]))
        if u is None:
            db.close()
            ensure()
            db = SessionLocal()
            u = db.scalar(select(User).where(User.email == DEMO_USERS[body.role.value]))
        if u is None:
            raise err("NOT_FOUND", message="Demo data is not available yet.")
        token, exp = create_access_token(u.id, u.role.value)
        return {"access_token": token, "token_type": "bearer", "expires_at": exp,
                "user": {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role}}
    finally:
        db.close()


@router.post("/reset", dependencies=[Depends(rate_limit("demo-reset", "RATE_LIMIT_AUTH"))])
def demo_reset():
    """Rebuild the demo schema from the sample dataset. Production is never touched."""
    _require_demo()
    reset()
    return {"reset": True, "environment": DEMO}


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "ensure"
    if cmd == "ensure":
        from app.demo_cleanup import purge_demo_from_production

        removed = purge_demo_from_production()
        if removed:
            print(f"demo: removed leaked demo data from production ({removed} demo users/areas/departments).")
    if not get_settings().DEMO_ENABLED:
        print("demo: DEMO_ENABLED is false; nothing to do.")
        return
    if cmd == "ensure":
        print("demo: seeded sample data." if ensure() else "demo: schema up to date.")
    elif cmd == "reset":
        reset()
        print("demo: rebuilt from sample data.")
    else:
        sys.exit("usage: python -m app.demo [ensure|reset]")


if __name__ == "__main__":
    main(sys.argv)
