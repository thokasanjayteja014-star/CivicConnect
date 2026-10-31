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


def in_department_scope(actor: Actor, department_id: uuid.UUID | None) -> bool:
    """System admins see every department; department users only their own active department."""
    if actor.is_system_admin:
        return True
    if actor.role in DEPARTMENT_ROLES:
        return actor.officer_active and department_id is not None and actor.department_id == department_id
    return False


def can_view_complaint(actor: Actor, complaint) -> bool:
    if actor.role == Role.CITIZEN:
        return complaint.citizen_id == actor.user_id
    return in_department_scope(actor, complaint.department_id)


def has_permission(actor: Actor, permission: Permission, department_id: uuid.UUID | None) -> bool:
    granted = ROLE_DEFAULT_PERMISSIONS.get(actor.role, set()) | actor.explicit_permissions
    if permission not in granted:
        return False
    return in_department_scope(actor, department_id)


def require_permission(actor: Actor, permission: Permission, department_id: uuid.UUID | None) -> None:
    if not has_permission(actor, permission, department_id):
        raise err("FORBIDDEN")
