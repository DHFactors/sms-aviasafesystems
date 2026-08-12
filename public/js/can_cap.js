const CanCapAPI = {
    // CAN
    listCans: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.hazard_id) qs.set('hazard_id', params.hazard_id);
        if (params.status) qs.set('status', params.status);
        if (params.priority) qs.set('priority', params.priority);
        if (params.assigned_to) qs.set('assigned_to', params.assigned_to);
        if (params.search) qs.set('search', params.search);
        const n = Number(params.days);
        if (n > 0) qs.set('days', n);
        return ApiClient.get(`/api/v1/cans?${qs.toString()}`);
    },

    getCan: (canId) => ApiClient.get(`/api/v1/cans/${canId}`),

    issueCan: (data) => ApiClient.post('/api/v1/cans', data),

    updateCanStatus: (canId, status) =>
        ApiClient._request('PATCH', `/api/v1/cans/${canId}/status?status=${status}`),

    deleteCan: (canId) => ApiClient.del(`/api/v1/cans/${canId}`),

    getStats: () => ApiClient.get('/api/v1/cans/stats'),

    // CAP
    submitCap: (canId, data) => ApiClient.post(`/api/v1/cans/${canId}/caps`, data),

    listCaps: (canId) => ApiClient.get(`/api/v1/cans/${canId}/caps`),

    listAllCaps: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.status) qs.set('status', params.status);
        if (params.can_id) qs.set('can_id', params.can_id);
        if (params.search) qs.set('search', params.search);
        const n = Number(params.days);
        if (n > 0) qs.set('days', n);
        return ApiClient.get(`/api/v1/cans/caps?${qs.toString()}`);
    },

    getCap: (capId) => ApiClient.get(`/api/v1/cans/caps/${capId}`),

    updateCap: (capId, data) => ApiClient.patch ? ApiClient._request('PATCH', `/api/v1/cans/caps/${capId}`, data) : ApiClient.put(`/api/v1/cans/caps/${capId}`, data),

    reviewCap: (capId, data) => ApiClient._request('PATCH', `/api/v1/cans/caps/${capId}/review`, data),

    updateCapStatus: (capId, status) =>
        ApiClient._request('PATCH', `/api/v1/cans/caps/${capId}/status?status=${status}`),
};

const CAN_STATUSES = ['Open', 'Under Review', 'Closed', 'Escalated'];
const CAN_PRIORITIES = ['High', 'Medium', 'Low'];
const CAP_STATUSES = ['In Progress', 'Under Review', 'Completed', 'Revision Required', 'Overdue'];

function canStatusBadgeClass(status) {
    const map = { 'Open': 'badge-new', 'Under Review': 'badge-warning', 'Closed': 'badge-completed', 'Escalated': 'badge-danger' };
    return map[status] || 'badge-default';
}

function capStatusBadgeClass(status) {
    const map = {
        'In Progress': 'badge-processing',
        'Under Review': 'badge-warning',
        'Completed': 'badge-completed',
        'Revision Required': 'badge-critical',
        'Overdue': 'badge-danger'
    };
    return map[status] || 'badge-default';
}

function canPriorityBadgeClass(priority) {
    const map = { 'High': 'badge-critical', 'Medium': 'badge-warning', 'Low': 'badge-low' };
    return map[priority] || 'badge-default';
}

function formatCanDate(d) {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); }
    catch { return '-'; }
}

ApiClient.patch = function(path, body) {
    return ApiClient._request('PATCH', path, body);
};

// ============================================================================
// Global CAN/CAP dashboard table loader (used by safety.html date filter)
// Renders CAN rows into #cansTableBody when present and returns the fetched
// list so callers (reloadDashboardData) can await it.
// days = 0 / null / undefined means "All Time" (no date cutoff).
// ============================================================================
async function fetchCans(days) {
    const tbody = document.getElementById('cansTableBody');
    if (!tbody) {
        try {
            return await CanCapAPI.listCans({ days });
        } catch (e) {
            console.error('fetchCans failed:', e);
            return [];
        }
    }

    const countEl = document.getElementById('canCapCount');
    const stateEl = document.getElementById('cansTableState');
    if (stateEl) {
        stateEl.style.display = 'block';
        stateEl.textContent = 'Loading CANs...';
    }

    try {
        const cans = await CanCapAPI.listCans({ days });
        if (countEl) countEl.textContent = cans.length;
        if (stateEl) stateEl.style.display = 'none';

        tbody.innerHTML = '';
        if (!cans || cans.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:2rem;"><i class="fas fa-inbox"></i> No CANs found for the selected period.</td></tr>';
            return [];
        }

        for (const c of cans) {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', () => {
                window.location.href = `/can_cap/can_detail.html?id=${c.id}`;
            });
            tr.innerHTML = `
                <td><strong>${c.can_reference || '-'}</strong></td>
                <td>${c.title || '-'}</td>
                <td><span class="badge ${canPriorityBadgeClass(c.priority)}">${c.priority || '-'}</span></td>
                <td><span class="badge ${canStatusBadgeClass(c.status)}">${c.status || '-'}</span></td>
                <td>${c.assigned_to || '-'}</td>
                <td>${formatCanDate(c.target_completion_date)}</td>
                <td>${formatCanDate(c.issued_at)}</td>
            `;
            tbody.appendChild(tr);
        }
        return cans;
    } catch (err) {
        if (stateEl) stateEl.style.display = 'none';
        console.error('fetchCans failed:', err);
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#dc3545;padding:2rem;"><i class="fas fa-exclamation-circle"></i> Error loading CANs: ${err.message}</td></tr>`;
        return [];
    }
}

window.fetchCans = fetchCans;
