const ApiClient = {
    _baseUrl: () => (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || 'https://aviasafe-unified-platform.onrender.com',

    _waitForFirebase: () => {
        return new Promise(resolve => {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                resolve();
                return;
            }
            const check = setInterval(() => {
                if (typeof firebase !== 'undefined' && firebase.auth) {
                    clearInterval(check);
                    resolve();
                }
            }, 30);
            setTimeout(() => {
                clearInterval(check);
                resolve();
            }, 8000);
        });
    },

    _tokenRedirecting: false,

    _getToken: async () => {
        await ApiClient._waitForFirebase();
        const session = await getCurrentUser();
        if (!session) {
            if (!ApiClient._tokenRedirecting) {
                ApiClient._tokenRedirecting = true;
                window.location.href = '/login.html';
            }
            return null;
        }
        const user = firebase.auth().currentUser;
        if (!user) {
            if (!ApiClient._tokenRedirecting) {
                ApiClient._tokenRedirecting = true;
                window.location.href = '/login.html';
            }
            return null;
        }
        try {
            return await user.getIdToken();
        } catch {
            window.location.href = '/login.html';
            return null;
        }
    },

    _getTenantId: async () => {
        try {
            // Prefer the active tenant slug resolved from the subdomain / demo
            // context (single source of truth), then fall back to the session
            // tenant claim for signed-in users whose subdomain is absent.
            if (typeof TenantResolver !== 'undefined' && TenantResolver.getCurrentTenant) {
                const active = TenantResolver.getCurrentTenant();
                if (active) return active;
            }
            const session = await getCurrentUser();
            return (session && session.tenantId) || null;
        } catch {
            return null;
        }
    },

    _getUserDepartment: async () => {
        try {
            const session = await getCurrentUser();
            const email = (session && session.email) || '';
            if (email && typeof resolveDepartmentFromEmail === 'function') {
                let tenantId = null;
                if (typeof TenantResolver !== 'undefined' && TenantResolver.getCurrentTenant) {
                    tenantId = TenantResolver.getCurrentTenant();
                }
                if (!tenantId && session) tenantId = session.tenantId || null;
                return resolveDepartmentFromEmail(email, tenantId);
            }
            return null;
        } catch {
            return null;
        }
    },

    _request: async (method, path, body) => {
        const token = await ApiClient._getToken();
        if (!token) return null;
        const [tenantId, department] = await Promise.all([
            ApiClient._getTenantId(),
            ApiClient._getUserDepartment(),
        ]);

        const url = `${ApiClient._baseUrl()}${path}`;
        const opts = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
                ...(department ? { 'X-User-Department': department } : {}),
            },
        };
        if (body && method !== 'GET') {
            opts.body = JSON.stringify(body);
        }

        let response;
        let lastErr;
        // Retry on transient network failures (connection reset / cold-start on
        // the free Render tier). GET requests are idempotent so retrying is safe.
        const maxAttempts = method === 'GET' ? 3 : 1;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                response = await fetch(url, opts);
                lastErr = null;
                break;
            } catch (err) {
                lastErr = err;
                console.warn(`[ApiClient] network attempt ${attempt}/${maxAttempts} failed for ${method} ${path}: ${err.message}`);
                if (attempt < maxAttempts) {
                    await new Promise(r => setTimeout(r, 800 * attempt));
                }
            }
        }
        if (lastErr) {
            const detail = `Network error while reaching the API (${method} ${path}): ${lastErr.message}`;
            console.error('[ApiClient]', detail);
            throw new Error('Network error. Please check your connection and try again.');
        }

        if (response.status === 401) {
            console.error(`[ApiClient] Authorization failed (401) for ${method} ${path}`);
            window.location.href = '/login.html';
            return null;
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
            const detail = err.detail || `Request failed: ${response.status}`;
            console.error(`[ApiClient] ${method} ${path} failed (${response.status}):`, detail);
            throw new Error(detail);
        }

        const json = await response.json();
        return json.data !== undefined ? json.data : json;
    },

    get: (path) => ApiClient._request('GET', path),
    post: (path, body) => ApiClient._request('POST', path, body),
    put: (path, body) => ApiClient._request('PUT', path, body),
    patch: (path, body) => ApiClient._request('PATCH', path, body),
    del: (path) => ApiClient._request('DELETE', path),
};
