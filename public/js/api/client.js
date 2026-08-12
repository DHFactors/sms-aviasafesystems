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
            const session = await getCurrentUser();
            return (session && session.tenantId) || null;
        } catch {
            return null;
        }
    },

    _request: async (method, path, body) => {
        const token = await ApiClient._getToken();
        if (!token) return null;
        const tenantId = await ApiClient._getTenantId();

        const url = `${ApiClient._baseUrl()}${path}`;
        const opts = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
            },
        };
        if (body && method !== 'GET') {
            opts.body = JSON.stringify(body);
        }

        let response;
        try {
            response = await fetch(url, opts);
        } catch (err) {
            const detail = `Network error while reaching the API (${method} ${path}): ${err.message}`;
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
    del: (path) => ApiClient._request('DELETE', path),
};
