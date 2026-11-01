"""Backend role-based access control (spec 9.A, L10.9, L10.10)."""
import uuid
from dataclasses import dataclass, field

from app.core.errors import err
from app.models.enums import Permission, Role

STAFF_ROLES = {Role.OFFICER, Role.DEPARTMENT_ADMIN, Role.SYSTEM_ADMIN}
DEPARTMENT_ROLES = {Role.OFFICER, Role.DEPARTMENT_ADMIN}

# Default prototype grants. Officers get nothing extra by default; a system
# admin may grant VERIFY_RESOLUTION to an individual officer explicitly.
ROLE_DEFAULT_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.CITIZEN: set(),
    Role.OFFICER: set(),
    Role.DEPARTMENT_ADMIN: {Permission.VERIFY_RESOLUTION, Permission.DECIDE_REOPENING},
    Role.SYSTEM_ADMIN: {Permission.VERIFY_RESOLUTION, Permission.DECIDE_REOPENING},
}


@dataclass
class Actor:
    user_id: uuid.UUID
    role: Role
    full_name: str
    department_id: uuid.UUID | None = None
    officer_id: uuid.UUID | None = None
    officer_active: bool = False
    explicit_permissions: set[Permission] = field(default_factory=set)
    unit_id: uuid.UUID | None = None
    # Officers only: operational-area jurisdictions expanded with descendants; empty = whole unit.
    area_ids: frozenset = frozenset()

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_system_admin(self) -> bool:
        return self.role == Role.SYSTEM_ADMIN

    @property
    def label(self) -> str:
        return f"user:{self.user_id}"


def check_role_permissions(actor: Actor, allowed_roles: set[Role]) -> None:
    if actor.role not in allowed_roles:
        raise err("FORBIDDEN")


def _assigned_to(db, actor: Actor, complaint) -> bool:
    from sqlalchemy import select
    from app.models import Assignment
    return db is not None and actor.officer_id is not None and db.scalar(
        select(Assignment.id).where(Assignment.complaint_id == complaint.id, Assignment.officer_id == actor.officer_id).limit(1)
    ) is not None


def in_department_scope(actor: Actor, complaint, db=None) -> bool:
    """System admins see everything; department personnel only their own unit (department in a
    jurisdiction). Officers with operational areas see unit complaints in those areas plus anything
    assigned to them."""
    if actor.is_system_admin:
        return True
    if actor.role not in DEPARTMENT_ROLES or not actor.officer_active or complaint is None:
        return False
    if actor.unit_id is None or complaint.department_unit_id != actor.unit_id:
        return _assigned_to(db, actor, complaint) if actor.role == Role.OFFICER else False
    if actor.role == Role.OFFICER and actor.area_ids and complaint.jurisdiction_id not in actor.area_ids:
        return _assigned_to(db, actor, complaint)
    return True


def can_view_complaint(actor: Actor, complaint, db=None) -> bool:
    if actor.role == Role.CITIZEN:
        return complaint.citizen_id == actor.user_id
    return in_department_scope(actor, complaint, db)


def has_permission(actor: Actor, permission: Permission, complaint, db=None) -> bool:
    granted = ROLE_DEFAULT_PERMISSIONS.get(actor.role, set()) | actor.explicit_permissions
    if permission not in granted:
        return False
    return in_department_scope(actor, complaint, db)


def require_permission(actor: Actor, permission: Permission, complaint, db=None) -> None:
    if not has_permission(actor, permission, complaint, db):
        raise err("FORBIDDEN")
