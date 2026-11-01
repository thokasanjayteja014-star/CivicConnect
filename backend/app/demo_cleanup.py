"""Remove demo sample data that leaked into the production (public) tables.

Before the demo engine pinned its schema with a SET statement, a connection pooler that drops
libpq startup options (Supabase's Supavisor) let the demo seed write into production. This
removes exactly that dataset: users with @demo.civicconnect emails, areas and departments whose
source reference is the demo marker, and everything attached to them. It runs on every startup,
in one transaction, and does nothing when no demo rows are present.
"""

from sqlalchemy import text

from app.core.db import get_engine
from app.core.environment import PRODUCTION

DEMO_EMAIL_PATTERN = "%@demo.civicconnect"
DEMO_SOURCE = "Demonstration sample data (not an official record)"

_PURGE_SQL = """
SET LOCAL search_path TO public;
CREATE TEMP TABLE d_users ON COMMIT DROP AS
  SELECT id FROM users WHERE email LIKE '%@demo.civicconnect';
CREATE TEMP TABLE d_jur ON COMMIT DROP AS
  SELECT id FROM jurisdictions WHERE source_reference = 'Demonstration sample data (not an official record)';
CREATE TEMP TABLE d_dept ON COMMIT DROP AS
  SELECT id FROM departments WHERE source_reference = 'Demonstration sample data (not an official record)';
CREATE TEMP TABLE d_units ON COMMIT DROP AS
  SELECT id FROM department_units
  WHERE department_id IN (SELECT id FROM d_dept) OR jurisdiction_id IN (SELECT id FROM d_jur);
CREATE TEMP TABLE d_off ON COMMIT DROP AS
  SELECT id FROM officers
  WHERE user_id IN (SELECT id FROM d_users) OR unit_id IN (SELECT id FROM d_units)
     OR department_id IN (SELECT id FROM d_dept);
CREATE TEMP TABLE d_c ON COMMIT DROP AS
  SELECT id FROM complaints
  WHERE citizen_id IN (SELECT id FROM d_users) OR department_unit_id IN (SELECT id FROM d_units)
     OR jurisdiction_id IN (SELECT id FROM d_jur) OR department_id IN (SELECT id FROM d_dept);
CREATE TEMP TABLE d_pi ON COMMIT DROP AS
  SELECT id FROM public_issues
  WHERE department_unit_id IN (SELECT id FROM d_units) OR jurisdiction_id IN (SELECT id FROM d_jur)
     OR department_id IN (SELECT id FROM d_dept) OR created_by IN (SELECT id FROM d_users)
     OR id IN (SELECT issue_id FROM public_issue_complaints WHERE complaint_id IN (SELECT id FROM d_c));

-- public issues
DELETE FROM public_issue_complaints WHERE issue_id IN (SELECT id FROM d_pi) OR complaint_id IN (SELECT id FROM d_c);
DELETE FROM public_issue_updates WHERE issue_id IN (SELECT id FROM d_pi) OR author_id IN (SELECT id FROM d_users);
DELETE FROM public_issues WHERE id IN (SELECT id FROM d_pi);

-- everything attached to demo complaints
UPDATE complaints SET ai_analysis_id = NULL WHERE id IN (SELECT id FROM d_c);
DELETE FROM resolution_evidence WHERE complaint_id IN (SELECT id FROM d_c) OR uploaded_by IN (SELECT id FROM d_users);
DELETE FROM ai_analyses WHERE complaint_id IN (SELECT id FROM d_c) OR requested_by IN (SELECT id FROM d_users);
DELETE FROM assignments WHERE complaint_id IN (SELECT id FROM d_c) OR officer_id IN (SELECT id FROM d_off)
  OR department_unit_id IN (SELECT id FROM d_units) OR assigned_by IN (SELECT id FROM d_users);
DELETE FROM citizen_feedback WHERE complaint_id IN (SELECT id FROM d_c) OR citizen_id IN (SELECT id FROM d_users);
DELETE FROM complaint_relationships WHERE source_complaint_id IN (SELECT id FROM d_c) OR related_complaint_id IN (SELECT id FROM d_c);
DELETE FROM complaint_remarks WHERE complaint_id IN (SELECT id FROM d_c) OR author_id IN (SELECT id FROM d_users);
DELETE FROM media WHERE complaint_id IN (SELECT id FROM d_c) OR uploaded_by IN (SELECT id FROM d_users);
DELETE FROM notifications WHERE complaint_id IN (SELECT id FROM d_c) OR recipient_id IN (SELECT id FROM d_users);
DELETE FROM priority_assessments WHERE complaint_id IN (SELECT id FROM d_c);
DELETE FROM routing_decisions WHERE complaint_id IN (SELECT id FROM d_c) OR officer_id IN (SELECT id FROM d_off)
  OR department_unit_id IN (SELECT id FROM d_units) OR department_id IN (SELECT id FROM d_dept)
  OR jurisdiction_id IN (SELECT id FROM d_jur);
DELETE FROM status_history WHERE complaint_id IN (SELECT id FROM d_c);
DELETE FROM verification_decisions WHERE complaint_id IN (SELECT id FROM d_c) OR verifier_id IN (SELECT id FROM d_users);
DELETE FROM escalations WHERE complaint_id IN (SELECT id FROM d_c) OR department_unit_id IN (SELECT id FROM d_units);
DELETE FROM complaints WHERE id IN (SELECT id FROM d_c);

-- demo staff, departments and areas
DELETE FROM audit_logs WHERE actor_id IN (SELECT id FROM d_users);
DELETE FROM officer_areas WHERE officer_id IN (SELECT id FROM d_off) OR jurisdiction_id IN (SELECT id FROM d_jur);
DELETE FROM officers WHERE id IN (SELECT id FROM d_off);
DELETE FROM responsibility_rules WHERE department_id IN (SELECT id FROM d_dept);
DELETE FROM escalation_policies WHERE department_id IN (SELECT id FROM d_dept);
DELETE FROM department_units WHERE id IN (SELECT id FROM d_units);
DELETE FROM departments WHERE id IN (SELECT id FROM d_dept);
-- areas: remove the deepest level first (ward -> corporation -> district -> state)
DO $$
BEGIN
  FOR i IN 1..10 LOOP
    DELETE FROM jurisdictions
    WHERE id IN (SELECT id FROM d_jur)
      AND id NOT IN (SELECT parent_id FROM jurisdictions WHERE parent_id IS NOT NULL);
    EXIT WHEN NOT FOUND;
  END LOOP;
END $$;
DELETE FROM users WHERE id IN (SELECT id FROM d_users);
"""


def purge_demo_from_production() -> int:
    """Delete leaked demo rows from production. Returns the number of demo users found."""
    engine = get_engine(PRODUCTION)
    with engine.begin() as conn:
        found = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM public.users WHERE email LIKE :email)"
                " + (SELECT count(*) FROM public.jurisdictions WHERE source_reference = :src)"
                " + (SELECT count(*) FROM public.departments WHERE source_reference = :src)"
            ),
            {"email": DEMO_EMAIL_PATTERN, "src": DEMO_SOURCE},
        ).scalar_one()
        if not found:
            return 0
        cur = conn.connection.cursor()
        try:
            cur.execute(_PURGE_SQL)
        finally:
            cur.close()
    return int(found)
