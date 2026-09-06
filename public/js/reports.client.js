/* ============================================================================
   FILE: reports.client.js
   PATH: public/js/reports.client.js
   PURPOSE: Unified Reports client — merges aggregated (Quarterly/Annual) and
            occurrence (VSR/MOR) APIs + dashboard widget helpers.
            Replaces reports.js + report.js (kept for compat, deprecated).
   ============================================================================ */

const ReportsClient = {
    // ── Aggregated (Quarterly/Annual) — previously reports.js ──
    generateQuarterly: (year, quarter) => {
        const qs = `year=${year}&quarter=${quarter}`;
        return ApiClient.post(`/api/reporting/quarterly?${qs}`);
    },
    listQuarterly: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.year) qs.set('year', params.year);
        if (params.tenant_id) qs.set('tenant_id', params.tenant_id);
        return ApiClient.get(`/api/reporting/quarterly?${qs.toString()}`);
    },
    getQuarterly: (reportId) => ApiClient.get(`/api/reporting/quarterly/${reportId}`),
    exportQuarterly: (reportId) => ApiClient._request('GET', `/api/reporting/quarterly/${reportId}/export`),
    generateAnnual: (year) => {
        const qs = `year=${year}`;
        return ApiClient.post(`/api/reporting/annual?${qs}`);
    },
    listAnnual: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.year) qs.set('year', params.year);
        if (params.tenant_id) qs.set('tenant_id', params.tenant_id);
        return ApiClient.get(`/api/reporting/annual?${qs.toString()}`);
    },
    getAnnual: (reportId) => ApiClient.get(`/api/reporting/annual/${reportId}`),
    exportAnnual: (reportId) => ApiClient._request('GET', `/api/reporting/annual/${reportId}/export`),

    // ── Occurrence (VSR/MOR) — previously report.js ──
    submitReport: async function(data, reportType) {
        const user = firebase.auth().currentUser;
        if (!user) throw new Error('You must be logged in to submit a report.');
        const token = await user.getIdToken();
        const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
        const payload = {
            narrative: data.narrative,
            location: data.location,
            occurrence_date: new Date(data.occurrenceDate || data.date).toISOString(),
            report_type: reportType,
            is_anonymous: data.isAnonymous || false,
            flight_number: data.flightNumber || null,
            aircraft_registration: data.aircraftReg || null,
            severity_level: data.severityLevel ?? null,
            probability_level: data.probabilityLevel ?? null,
            occurrence_class: data.occurrenceClass || null,
            latitude: data.latitude ?? null,
            longitude: data.longitude ?? null,
            country: data.country || null,
            aircraft_make: data.aircraftMake || null,
            aircraft_model: data.aircraftModel || null,
            aircraft_serial_number: data.aircraftSerial || null,
            operator: data.operator || null,
            operator_icao: data.operatorIcao || null,
            aircraft_category: data.aircraftCategory || null,
            engine_make: data.engineMake || null,
            engine_model: data.engineModel || null,
            engine_serial_number: data.engineSerial || null,
            flight_phase: data.flightPhase || null,
            flight_type: data.flightType || null,
            departure_airport: data.departureAirport || null,
            destination_airport: data.destinationAirport || null,
            aircraft_utilisation_hours: data.aircraftUtilHours ?? null,
            aircraft_utilisation_cycles: data.aircraftUtilCycles ?? null,
            crew_count: data.crewCount ?? null,
            passenger_count: data.passengerCount ?? null,
            fatal_injuries: data.fatalInjuries ?? null,
            serious_injuries: data.seriousInjuries ?? null,
            minor_injuries: data.minorInjuries ?? null,
            occurrence_category: data.occurrenceCategory || null,
            human_factors: data.humanFactors || null,
            contributing_factors: data.contributingFactors || null,
            investigation_agency: data.investigationAgency || null,
            reporter_name: data.reporterName || null,
            reporter_role: data.reporterRole || null,
            reporter_email: data.reporterEmail || null,
            reporter_phone: data.reporterPhone || null,
            reporter_organisation: data.reporterOrganisation || null,
            reporting_date: data.reportingDate || new Date().toISOString(),
        };
        if (data.occurrence_type) payload.occurrence_type = data.occurrence_type;
        const response = await fetch(`${baseUrl}/api/v1/reports/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || `HTTP ${response.status}: Failed to submit report`);
        }
        return response.json();
    },
    submitMOR: function(data) { return this.submitReport({ ...data, isAnonymous: false }, 'mandatory'); },
    submitVSR: function(data) { return this.submitReport({ ...data, isAnonymous: data.isAnonymous !== undefined ? data.isAnonymous : true }, 'voluntary'); },
    getReport: async function(reportId) {
        const user = firebase.auth().currentUser;
        if (!user) throw new Error('Not authenticated');
        const token = await user.getIdToken();
        const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
        const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!response.ok) throw new Error((await response.json().catch(()=>({detail:'Not found'}))).detail || `HTTP ${response.status}`);
        return response.json();
    },
    confirmRiskAssessment: async function(reportId, severity, probability, notes) {
        const user = firebase.auth().currentUser;
        if (!user) throw new Error('Not authenticated');
        const token = await user.getIdToken();
        const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
        const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}/risk-assessment`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ severity, probability, notes: notes || null }),
        });
        if (!response.ok) throw new Error((await response.json().catch(()=>({detail:'Request failed'}))).detail || `HTTP ${response.status}`);
        return response.json();
    },
};

// Backward compat aliases (deprecated)
const ReportsAPI = ReportsClient;
async function submitReport(data, reportType) { return ReportsClient.submitReport(data, reportType); }
async function submitMOR(data) { return ReportsClient.submitMOR(data); }
async function submitVSR(data) { return ReportsClient.submitVSR(data); }
async function getReport(reportId) { return ReportsClient.getReport(reportId); }
async function confirmRiskAssessment(a,b,c,d) { return ReportsClient.confirmRiskAssessment(a,b,c,d); }
function formatReportDate(d) {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); } catch { return '-'; }
}
function reportStatusBadgeClass(status) {
    const map = { 'completed': 'badge-completed', 'generating': 'badge-warning', 'draft': 'badge-default', 'failed': 'badge-critical' };
    return map[status] || 'badge-default';
}
async function downloadPdf(reportId, type) {
    try {
        const token = await ApiClient._getToken();
        const baseUrl = ApiClient._baseUrl();
        const url = `${baseUrl}/api/reporting/${type}/${reportId}/export`;
        const response = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!response.ok) throw new Error('Download failed');
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${type}_report_${reportId}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (err) { alert('Error downloading PDF: ' + err.message); }
}
