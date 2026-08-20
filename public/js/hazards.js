const HazardsAPI = {
    list: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.status) qs.set('status', params.status);
        if (params.priority) qs.set('priority', params.priority);
        if (params.source) qs.set('source', params.source);
        if (params.taxonomy) qs.set('taxonomy', params.taxonomy);
        if (params.tenant_id) qs.set('tenant_id', params.tenant_id);
        if (params.search) qs.set('search', params.search);
        return ApiClient.get(`/api/hazards?${qs.toString()}`);
    },

    get: (hazardId) => ApiClient.get(`/api/hazards/${hazardId}`),

    create: (data) => ApiClient.post('/api/hazards', data),

    update: (hazardId, data) => ApiClient.put(`/api/hazards/${hazardId}`, data),

    updateStatus: (hazardId, status) =>
        ApiClient._request('PATCH', `/api/hazards/${hazardId}/status?status=${status}`),

    assign: (hazardId, assignedTo, assignedToUid) =>
        ApiClient._request('PATCH', `/api/hazards/${hazardId}/assign?assigned_to=${encodeURIComponent(assignedTo)}&assigned_to_uid=${assignedToUid}`),

    getStats: () => ApiClient.get('/api/hazards/stats'),

    // ── CAAN CAR-19 SRM (Bow-Tie) ──
    sramCalculate: (hazardId, payload) =>
        ApiClient.post(`/api/hazards/${hazardId}/sram/calculate`, payload),

    sramSave: (hazardId, payload) =>
        ApiClient.put(`/api/hazards/${hazardId}/sram/save`, payload),
};

const HAZARD_STATUSES = ['Open', 'Processing', 'Under Review', 'Closed', 'Reopened'];
const HAZARD_PRIORITIES = ['H', 'M', 'L'];
const HAZARD_SOURCES = [
    'VSR', 'MOR', 'Quality Audit', 'Safety Inspection', 'Flight Diversion',
    'CAAN Audit', 'Internal Audit', 'Safety Survey', 'IOR', 'MOC', 'SRM Request', 'Incident'
];
const HAZARD_CREATION_SOURCES = [
    'VSR', 'MOR', 'Internal Audit', 'Quality Audit', 'CAAN Audit', 'Flight Diversion'
];
const HAZARD_TAXONOMIES = [
    'Organizational-Facilities',
    'Organizational-Documentation, Processes and Procedures',
    'Technical', 'Wildlife', 'Human Factors', 'Environmental', 'Other'
];

function hazardStatusBadgeClass(status) {
    const map = {
        'Open': 'badge-new',
        'Processing': 'badge-processing',
        'Under Review': 'badge-warning',
        'Closed': 'badge-completed',
        'Reopened': 'badge-critical'
    };
    return map[status] || 'badge-default';
}

function hazardPriorityBadgeClass(priority) {
    const map = { 'H': 'badge-critical', 'M': 'badge-warning', 'L': 'badge-low' };
    return map[priority] || 'badge-default';
}

function normalizeHazardRiskLevel(riskLevel) {
    if (riskLevel === null || riskLevel === undefined) return 'High';
    const norm = String(riskLevel).trim().toUpperCase();
    if (norm === 'LOW' || norm === 'ACCEPTABLE' || norm === 'LEVEL II') return 'Low';
    if (norm === 'VERY HIGH' || norm === 'CRITICAL' || norm === 'INTOLERABLE' || norm === 'SEVERE' || norm === 'LEVEL IV') return 'Very High';
    return 'High';
}

function hazardRiskBadgeClass(riskLevel) {
    const map = { Low: 'badge-low', High: 'badge-high', 'Very High': 'badge-critical' };
    return map[normalizeHazardRiskLevel(riskLevel)] || 'badge-default';
}

function calculateRiskIndex(severity, probability) {
    if (severity == null || probability == null) return null;
    return severity * probability;
}

window.ICAO_THRESHOLDS = window.ICAO_THRESHOLDS || { lowMax: 5, mediumMax: 9, highMax: 15 };

function classifyHazardRisk(riskIndex) {
    if (riskIndex == null) return 'Unknown';
    if (riskIndex <= ICAO_THRESHOLDS.lowMax) return 'Low';
    if (riskIndex <= ICAO_THRESHOLDS.highMax) return 'High';
    return 'Very High';
}

function getRiskOutcome(severity, probability) {
    const ri = calculateRiskIndex(severity, probability);
    if (ri == null) return null;
    if (ri <= ICAO_THRESHOLDS.lowMax) return 'Acceptable';
    if (ri <= ICAO_THRESHOLDS.highMax) return 'Tolerable';
    return 'Intolerable';
}

function formatDate(d) {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); }
    catch { return '-'; }
}
