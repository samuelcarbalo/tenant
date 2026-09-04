from rest_framework import permissions

LEVEL1_FORBIDDEN_MESSAGE = (
    "No tienes privilegios de Super Admin Nivel 1 para realizar esta acción"
)


def user_admin_level(user) -> int:
    try:
        return int(getattr(user, "admin_level", 0) or 0)
    except (TypeError, ValueError):
        return 0


def user_is_super_admin_l1(user) -> bool:
    if not user:
        return False
    level = user_admin_level(user)
    if level == 1:
        return True
    if level == 2:
        return False
    # Superusuarios de plataforma anteriores a admin_level se tratan como Nivel 1.
    return bool(getattr(user, "is_superuser", False))


def user_is_super_admin_l2(user) -> bool:
    """Administrador Delegado (Nivel 2)."""
    return user_admin_level(user) == 2


def user_is_shop_super_admin(user) -> bool:
    """Super Admin Nivel 1 o Nivel 2, o Administrador de la organización."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = str(getattr(user, "role", "") or "")
    hierarchy = str(getattr(user, "hierarchy_role", "") or "")
    if role in ("SUPER_ADMIN_L1", "SUPER_ADMIN_L2", "SUPER_ADMIN", "super_admin", "admin"):
        return True
    if hierarchy in ("SUPER_ADMIN_L1", "SUPER_ADMIN_L2", "SUPER_ADMIN"):
        return True
    return user_is_super_admin_l1(user) or user_is_super_admin_l2(user)


SHOP_PRODUCT_FORBIDDEN_MESSAGE = (
    "No tienes permisos para editar o eliminar este producto."
)


def user_can_query_own_shop_products(user) -> bool:
    """Vendedor/admin: puede listar su inventario con created_by_me."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user_can_manage_content(user) or user_is_shop_super_admin(user)


# Roles con permiso de gestión de productos de tienda (case-insensitive).
SHOP_PRODUCT_MANAGE_ROLES = frozenset(
    {
        "ADMIN",
        "SUPER_ADMIN_L1",
        "SUPER_ADMIN_L2",
        "MANAGER",
        "SUPER_ADMIN",
    }
)


def user_has_shop_product_manage_role(user) -> bool:
    """True si role/hierarchy_role está en ADMIN / SUPER_ADMIN_* / MANAGER."""
    if not user:
        return False
    role = str(getattr(user, "role", "") or "").strip().upper()
    hierarchy = str(getattr(user, "hierarchy_role", "") or "").strip().upper()
    return role in SHOP_PRODUCT_MANAGE_ROLES or hierarchy in SHOP_PRODUCT_MANAGE_ROLES


def user_can_manage_shop_product(user, product) -> bool:
    """
    Escritura / can_manage sobre un producto:
    - creador (created_by == user), o
    - is_superuser, o
    - role en ADMIN / SUPER_ADMIN_L1 / SUPER_ADMIN_L2 / MANAGER, o
    - shop super-admin (admin_level / flags equivalentes).

    Productos legacy sin created_by: el manager de la misma organización
    sigue tratándose como operador de la tienda.
    """
    if not user or not getattr(user, "is_authenticated", False) or product is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user_has_shop_product_manage_role(user) or user_is_shop_super_admin(user):
        return True
    created_by_id = getattr(product, "created_by_id", None)
    user_id = getattr(user, "id", None)
    if created_by_id and user_id and str(created_by_id) == str(user_id):
        return True
    if created_by_id is None and str(getattr(user, "role", "") or "").lower() == "manager":
        return getattr(product, "organization_id", None) == getattr(user, "organization_id", None)
    return False


def user_is_protected_platform_admin(user) -> bool:
    """Super Admin Nivel 1 o 2: no modificables por administradores de menor nivel."""
    if not user:
        return False
    if user_admin_level(user) in (1, 2):
        return True
    return bool(getattr(user, "is_superuser", False))


def user_is_platform_elevated(user) -> bool:
    """Superuser / staff / role admin de plataforma (sin org o cross-tenant)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", None) == "admin"
    )


def user_can_manage_content(user) -> bool:
    """Puede crear/editar contenido de módulos (manager de org o admin de plataforma)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user_is_platform_elevated(user):
        return True
    return getattr(user, "role", None) == "manager"


def resolve_request_organization(request):
    """
    Organización de escritura: middleware (X-Tenant) → user.organization → primera activa.
    Necesario para superusuarios de plataforma sin organización propia.
    """
    org = getattr(request, "current_organization", None)
    if org is not None:
        return org

    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        user_org = getattr(user, "organization", None)
        if user_org is not None:
            return user_org

    from organizations.models import Organization

    slug = None
    if hasattr(request, "headers"):
        slug = request.headers.get("X-Tenant")
    if slug:
        org = Organization.objects.filter(slug=slug, is_active=True).first()
        if org:
            return org
    return Organization.objects.filter(is_active=True).order_by("created_at").first()


class IsCoachOfTeam(permissions.BasePermission):
    """
    Permiso que verifica si el usuario autenticado es el coach (coach_email) del equipo.
    Se usa para crear/editar/eliminar jugadores de un equipo específico.
    """

    def has_permission(self, request, view):
        # Para acciones de lista/retrieve, permitir si es coach de algún equipo
        if view.action in ["list", "retrieve"]:
            return True
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj puede ser Player, Team, etc.
        if not request.user or not request.user.is_authenticated:
            return False

        # Si es superuser, permitir todo
        if request.user.is_superuser:
            return True

        # Obtener el equipo del jugador
        if hasattr(obj, "team"):
            team = obj.team
        elif hasattr(obj, "tournament"):
            # obj es un Team
            team = obj
        else:
            return False

        # Verificar si el email del usuario coincide con coach_email del equipo
        return request.user.email == team.coach_email


class IsOrganizationMember(permissions.BasePermission):
    """
    Permiso que verifica si el usuario pertenece a la organización
    especificada en el request (cabecera X-Tenant, X-Organization-ID, o del usuario).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Superusers tienen acceso a todo
        if request.user.is_superuser:
            return True

        # Obtener slug o ID de las cabeceras
        org_slug = request.headers.get("X-Tenant")
        org_id = request.headers.get("X-Organization-ID")

        if org_slug:
            return request.user.organization and request.user.organization.slug == org_slug

        if not org_id:
            org_id = getattr(request.user, "organization_id", None)

        if not org_id:
            return False

        return str(request.user.organization_id) == str(org_id)


class IsOrganizationAdmin(permissions.BasePermission):
    """
    Permiso para administradores de organización.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        return request.user.is_staff and getattr(request.user, "role", None) == "admin"


class CanManageShopProduct(permissions.BasePermission):
    """
    Lectura pública. Alta: manager/admin de contenido.
    PUT/PATCH/DELETE: solo created_by o Super Admin L1/L2.
    """

    message = SHOP_PRODUCT_FORBIDDEN_MESSAGE

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return user_can_manage_content(user) or user_is_shop_super_admin(user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        allowed = user_can_manage_shop_product(request.user, obj)
        if not allowed:
            self.message = SHOP_PRODUCT_FORBIDDEN_MESSAGE
        return allowed


class IsSuperAdminLevel1(permissions.BasePermission):
    """Solo Super Admin Root (Nivel 1) puede gestionar roles administrativos."""

    message = LEVEL1_FORBIDDEN_MESSAGE

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return user_is_super_admin_l1(user)


class IsSuperUser(permissions.BasePermission):
    """Solo superusuarios de la plataforma (is_superuser)."""

    message = "Se requieren permisos de superusuario."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_superuser)


class IsSportsSuperAdminOrOrgMember(permissions.BasePermission):
    """
    Permiso para el módulo de Deportes/Torneos.
    - Super Admin (is_superuser o admin_level == 1): acceso total a cualquier método HTTP.
    - Resto de usuarios autenticados: requieren pertenecer a la organización del tenant.
    """

    message = "No tienes permisos para realizar esta operación en el módulo de Deportes."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Super Admin siempre pasa
        if _is_sports_super_admin(request.user):
            return True
        # Resto: verificar membresía de organización (igual que IsOrganizationMember)
        org_slug = request.headers.get("X-Tenant")
        org_id = request.headers.get("X-Organization-ID")
        if org_slug:
            return request.user.organization and request.user.organization.slug == org_slug
        if not org_id:
            org_id = getattr(request.user, "organization_id", None)
        if not org_id:
            return False
        return str(request.user.organization_id) == str(org_id)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        # Super Admin: acceso total a cualquier objeto
        if _is_sports_super_admin(request.user):
            return True
        return True  # La verificación de objeto se delega a la vista si es necesario


def _is_sports_super_admin(user) -> bool:
    """Retorna True si el usuario es Super Admin con acceso total al módulo de Deportes."""
    if not user:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user_admin_level(user) == 1:
        return True
    if getattr(user, "role", None) in ("SUPER_ADMIN", "super_admin"):
        return True
    return False


class IsMercadoPagoConfigAdmin(permissions.BasePermission):
    """IsAdminUser (is_staff) o IsSuperUser (is_superuser) — credenciales Mercado Pago."""

    message = "Se requieren permisos de administrador (staff o superusuario)."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_staff or user.is_superuser)
