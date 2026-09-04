// RBAC - Role-Based Menu
const RBAC_PERMISSIONS = {
    'tenant_admin': ['module1', 'module2', 'module3', 'settings'],
    'safety_manager': ['module1', 'module2', 'module3'],
    'department_head': ['module2'],
    'employee': ['module2'],
    'regulator': ['module5'],
};

const MENU_CONFIG = {
    'module1': { label: 'Maturity Assessment', icon: 'fa-chart-simple', href: '/module1/maturity.html' },
    'module2': { label: 'Safety Reports', icon: 'fa-triangle-exclamation', href: '/safety.html' },
    'module3': { label: 'Safety Dashboard', icon: 'fa-gauge-high', href: '/dashboard/index.html' },
    'module5': { label: 'Regulator Dashboard', icon: 'fa-landmark', href: '/module5/regulator-dashboard.html' },
    'settings': { label: 'Settings', icon: 'fa-gear', href: '/settings/team.html' },
};

function getUserRole() {
    // Retrieve role from Firebase user context or localStorage
    if (typeof window !== 'undefined' && window.currentUser && window.currentUser.role) {
        return window.currentUser.role;
    }
    // Try to get from token claims stored in localStorage
    try {
        const stored = localStorage.getItem('userRole') || sessionStorage.getItem('userRole');
        if (stored) return stored;
    } catch (e) {}
    // Fallback to firebase auth
    if (typeof firebase !== 'undefined' && firebase.auth && firebase.auth().currentUser) {
        // Will be populated after getIdTokenResult
        return null;
    }
    return null;
}

function getMenuItems(role) {
    const modules = RBAC_PERMISSIONS[role] || [];
    return modules.map(m => MENU_CONFIG[m]).filter(Boolean);
}

function renderMenu(role) {
    const menuItems = getMenuItems(role);
    const container = document.getElementById('rbac-menu') || document.getElementById('sidebar-menu') || document.querySelector('nav');
    if (!container) {
        console.warn('RBAC menu container not found');
        return;
    }
    // Clear and render
    // Keep existing non-RBAC items, or replace
    const html = menuItems.map(item => 
        `<a href="${item.href}" class="menu-item" data-module="${item.href}"><i class="fas ${item.icon}"></i> ${item.label}</a>`
    ).join('');
    // If container is sidebar, append; otherwise replace
    if (container.id === 'rbac-menu') {
        container.innerHTML = html;
    } else {
        // Try to find rbac section
        let rbacSection = document.getElementById('rbac-menu');
        if (!rbacSection) {
            rbacSection = document.createElement('div');
            rbacSection.id = 'rbac-menu';
            rbacSection.innerHTML = html;
            container.appendChild(rbacSection);
        } else {
            rbacSection.innerHTML = html;
        }
    }
    console.log(`RBAC menu rendered for role ${role}: ${menuItems.length} items`);
}

// Auto-render on auth state change if available
if (typeof firebase !== 'undefined' && firebase.auth) {
    firebase.auth().onAuthStateChanged(async (user) => {
        if (user) {
            try {
                const tokenResult = await user.getIdTokenResult();
                const role = tokenResult.claims.role || 'employee';
                // Normalize legacy roles
                const normalized = {
                    'AIRLINE_ADMIN': 'tenant_admin',
                    'TENANT_ADMIN': 'tenant_admin',
                    'CAAN_SMD': 'regulator',
                    'DEPT_ADMIN': 'department_head',
                    'USER': 'employee',
                    'STAFF': 'employee'
                }[role] || role;
                window.currentUser = { ...window.currentUser, role: normalized, claims: tokenResult.claims };
                renderMenu(normalized);
            } catch (e) {
                console.warn('RBAC: failed to get role', e);
            }
        }
    });
}

if (typeof window !== 'undefined') {
    window.getUserRole = getUserRole;
    window.getMenuItems = getMenuItems;
    window.renderMenu = renderMenu;
}
