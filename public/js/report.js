async function submitReport(data, reportType) {
    const user = firebase.auth().currentUser;
    if (!user) {
        throw new Error('You must be logged in to submit a report.');
    }

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

    if (data.occurrence_type) {
        payload.occurrence_type = data.occurrence_type;
    }

    const response = await fetch(`${baseUrl}/api/v1/reports/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${response.status}: Failed to submit report`);
    }

    return response.json();
}

async function submitMOR(data) {
    return submitReport({
        ...data,
        isAnonymous: false,
    }, 'mandatory');
}

async function submitVSR(data) {
    return submitReport({
        ...data,
        isAnonymous: data.isAnonymous !== undefined ? data.isAnonymous : true,
    }, 'voluntary');
}

async function getReport(reportId) {
    const user = firebase.auth().currentUser;
    if (!user) throw new Error('Not authenticated');
    const token = await user.getIdToken();
    const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
    const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Not found' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

async function confirmRiskAssessment(reportId, severity, probability, notes) {
    const user = firebase.auth().currentUser;
    if (!user) throw new Error('Not authenticated');
    const token = await user.getIdToken();
    const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
    const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}/risk-assessment`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
            severity: severity,
            probability: probability,
            notes: notes || null,
        }),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

async function getRiskMatrix() {
    const user = firebase.auth().currentUser;
    if (!user) throw new Error('Not authenticated');
    const token = await user.getIdToken();
    const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
    const response = await fetch(`${baseUrl}/api/v1/admin/risk-matrix`, {
        headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

async function updateRiskMatrix(thresholds) {
    const user = firebase.auth().currentUser;
    if (!user) throw new Error('Not authenticated');
    const token = await user.getIdToken();
    const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
    const response = await fetch(`${baseUrl}/api/v1/admin/risk-matrix`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
            thresholds: {
                low_max: thresholds.lowMax,
                medium_max: thresholds.mediumMax,
                high_max: thresholds.highMax,
            },
        }),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

function getRiskLevelLabel(index) {
    if (index === null || index === undefined) return { text: 'N/A', class: 'badge-default' };
    if (index <= 5) return { text: 'Low', class: 'badge-low' };
    if (index <= 15) return { text: 'High', class: 'badge-high' };
    return { text: 'Very High', class: 'badge-critical' };
}
