from typing import Dict, List, Optional

# Module-based permissions per role
PERMISSIONS = {
    'tenant_admin': ['module1', 'module2', 'module3', 'settings'],
    'safety_manager': ['module1', 'module2', 'module3'],
    'department_head': ['module2'],
    'employee': ['module2'],
    'regulator': ['module5'],
}

# Human-readable role definitions
ROLES = {
    'tenant_admin': 'Full access to their tenant (Modules 1, 2, 3, Settings)',
    'safety_manager': 'Modules 1, 2, 3 (full access)',
    'department_head': 'Module 2 only (hazards, CAN/CAP)',
    'employee': 'Submit reports, view own submissions (Module 2 limited)',
    'regulator': 'Module 5 only (aggregated view)',
}

# Module mapping for endpoints
MODULE_ENDPOINTS = {
    'module1': ['/maturity', '/survey', '/module1'],
    'module2': ['/hazards', '/sram', '/cans', '/caps', '/reports'],
    'module3': ['/safety', '/dashboard'],
    'module5': ['/regulator', '/industry', '/aggregation', '/benchmark'],
    'settings': ['/settings', '/admin/tenants'],
}

def has_permission(role: str, module: str) -> bool:
    """Check if role has permission for module."""
    if not role or not module:
        return False
    allowed = PERMISSIONS.get(role, [])
    return module in allowed

def get_permissions(role: str) -> List[str]:
    return PERMISSIONS.get(role, [])

def get_role_display(role: str) -> str:
    return ROLES.get(role, "Unknown role")

def is_regulator(role: str) -> bool:
    return role == 'regulator'

def is_tenant_user(role: str) -> bool:
    return role in ('tenant_admin', 'safety_manager', 'department_head', 'employee')

def normalize_legacy_role(legacy_role: str) -> str:
    """Map legacy roles to new RBAC roles."""
    mapping = {
        'AIRLINE_ADMIN': 'tenant_admin',
        'TENANT_ADMIN': 'tenant_admin',
        'SUPER_ADMIN': 'tenant_admin',  # super admin has tenant_admin + regulator via separate logic
        'CAAN_SMD': 'regulator',
        'SAFETY_OFFICER': 'safety_manager',
        'DEPT_ADMIN': 'department_head',
        'USER': 'employee',
        'STAFF': 'employee',
    }
    return mapping.get(legacy_role, 'employee')
