"""
Role-based access.

Roles are Django groups so they can be managed from the admin panel:
    Admin        - superusers / staff: everything, including user management
    Pharmacist   - billing, medicine catalogue, read access to everything else
    Store Staff  - suppliers, purchase orders and stock batches; read-only medicines
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

ADMIN = "Admin"
PHARMACIST = "Pharmacist"
STORE_STAFF = "Store Staff"
ROLES = (ADMIN, PHARMACIST, STORE_STAFF)


def get_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser or user.is_staff:
        return ADMIN
    names = set(user.groups.values_list("name", flat=True))
    for role in (PHARMACIST, STORE_STAFF):
        if role in names:
            return role
    return None


class RolePermission(BasePermission):
    """
    Views declare `write_roles`. Any authenticated user with a role may read;
    only the listed roles (plus Admin) may create/update/delete.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view):
        role = get_role(request.user)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        write_roles = getattr(view, "write_roles", ())
        return role == ADMIN or role in write_roles


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) == ADMIN
