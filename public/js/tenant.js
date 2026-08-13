/* ============================================================================
   FILE: tenant.js
   PATH: public/js/tenant.js
   VERSION: 1.0.0
   PURPOSE: Tenant resolution and branding service.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

// ============================================================================
// TENANT RESOLUTION
// ============================================================================

function getTenantFromSubdomain() {
    const hostname = window.location.hostname;
    const parts = hostname.split('.');
    
    if (parts.length >= 2 && parts[1] === 'aviasafesystems') {
        const subdomain = parts[0];
        const reserved = ['www', 'app', 'api', 'caan', 'admin', 'auth', 'docs', 'sms'];
        if (reserved.includes(subdomain)) {
            return null;  // Not a tenant subdomain
        }
        return subdomain;
    }
    
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('tenant') || null;
}

// ============================================================================
// TENANT BRANDING
// ============================================================================

async function applyTenantBranding() {
    const tenantId = getTenantFromSubdomain();
    if (!tenantId) {
        // No tenant → default branding
        document.documentElement.removeAttribute('data-tenant');
        return;
    }
    
    // Set data-tenant attribute on root
    document.documentElement.setAttribute('data-tenant', tenantId);
    
    // Try to load tenant-specific overrides
    try {
        const response = await fetch(`/css/tenant-overrides.css`);
        if (response.ok) {
            // Already loaded via link tag
            console.log(`🎨 Tenant branding applied: ${tenantId}`);
        }
    } catch (error) {
        console.warn(`No custom branding for tenant: ${tenantId}`);
    }
}

// ============================================================================
// TENANT VALIDATION
// ============================================================================

async function validateTenant(tenantId) {
    if (!tenantId) return { valid: false, error: 'No tenant provided' };
    
    try {
        const doc = await db.collection('tenants').doc(tenantId).get();
        if (!doc.exists) {
            return { valid: false, error: `Tenant "${tenantId}" not found` };
        }
        const data = doc.data();
        if (data.active === false) {
            return { valid: false, error: `Tenant "${tenantId}" is inactive` };
        }
        return { valid: true, data, tenantId };
    } catch (error) {
        return { valid: false, error: error.message };
    }
}

// ============================================================================
// TENANT METADATA
// ============================================================================

async function getTenantMetadata(tenantId) {
    try {
        const doc = await db.collection('tenants').doc(tenantId).get();
        if (!doc.exists) return null;
        return doc.data();
    } catch (error) {
        console.error('Error fetching tenant metadata:', error);
        return null;
    }
}

// ============================================================================
// INITIALIZE TENANT
// ============================================================================

async function initializeTenant() {
    const tenantId = getTenantFromSubdomain();
    
    if (tenantId) {
        // Validate tenant
        const validation = await validateTenant(tenantId);
        if (!validation.valid) {
            // Show error
            document.body.innerHTML = `
                <div style="display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background: #f8fafc; margin: 0;">
                    <div style="text-align: center; padding: 40px; max-width: 500px; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                        <i class="fas fa-building" style="font-size: 4rem; color: #ea4335; margin-bottom: 20px;"></i>
                        <h2 style="color: #ea4335;">Invalid Tenant</h2>
                        <p style="color: #5f6368;">${validation.error}</p>
                        <button onclick="window.location.href='/'" style="background: #1a6b8a; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-top: 15px;">
                            Return to Home
                        </button>
                    </div>
                </div>
            `;
            return null;
        }
        
        // Apply branding
        await applyTenantBranding();
        return tenantId;
    }
    
    return null;
}

// Run on page load
document.addEventListener('DOMContentLoaded', initializeTenant);