let currentSection = 0;
const totalSections = 8;
const sectionValidators = [];

function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}
function getNum(id) {
    const v = document.getElementById(id)?.value;
    const n = parseInt(v);
    return isNaN(n) ? null : n;
}
function getFloat(id) {
    const v = document.getElementById(id)?.value;
    if (!v) return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
}
function getChecked(id) {
    return document.getElementById(id)?.checked || false;
}

function gatherSectionData(sectionIdx) {
    const d = {};
    switch (sectionIdx) {
        case 0:
            d.reporterName = getVal('reporterName');
            d.reporterRole = getVal('reporterRole');
            d.reporterOrganisation = getVal('reporterOrganisation');
            d.reporterEmail = getVal('reporterEmail');
            d.reporterPhone = getVal('reporterPhone') || null;
            break;
        case 1:
            d.aircraftMake = getVal('aircraftMake');
            d.aircraftModel = getVal('aircraftModel');
            d.aircraftReg = getVal('aircraftReg');
            d.aircraftSerial = getVal('aircraftSerial') || null;
            d.aircraftCategory = getVal('aircraftCategory');
            d.operator = getVal('operator');
            d.operatorIcao = getVal('operatorIcao') || null;
            d.etops = getChecked('etops');
            break;
        case 2:
            d.engineMake = getVal('engineMake') || null;
            d.engineModel = getVal('engineModel') || null;
            d.engineSerial = getVal('engineSerial') || null;
            d.propellerMake = getVal('propellerMake') || null;
            d.propellerModel = getVal('propellerModel') || null;
            break;
        case 3:
            d.flightPhase = getVal('flightPhase');
            d.flightType = getVal('flightType');
            d.flightNumber = getVal('flightNumber') || null;
            d.callSign = getVal('callSign') || null;
            d.departureAirport = getVal('departureAirport')?.toUpperCase() || null;
            d.destinationAirport = getVal('destinationAirport')?.toUpperCase() || null;
            break;
        case 4:
            d.crewCount = getNum('crewCount');
            d.passengerCount = getNum('passengerCount');
            d.fatalInjuries = getNum('fatalInjuries');
            d.seriousInjuries = getNum('seriousInjuries');
            d.minorInjuries = getNum('minorInjuries');
            break;
        case 5:
            d.occurrenceDate = getVal('occurrenceDate');
            d.occurrenceType = getVal('occurrenceType');
            d.occurrenceClass = getVal('occurrenceClass');
            d.location = getVal('location');
            d.country = getVal('country') || null;
            d.latitude = getFloat('latitude');
            d.longitude = getFloat('longitude');
            d.narrative = getVal('narrative');
            break;
        case 6:
            d.occurrenceCategory = getVal('occurrenceCategory');
            const hfChecks = document.querySelectorAll('.hf-checkbox:checked');
            d.humanFactors = Array.from(hfChecks).map(cb => cb.value);
            d.contributingFactors = getVal('contributingFactors')
                ? getVal('contributingFactors').split(',').map(s => s.trim()).filter(Boolean)
                : [];
            d.investigationStatus = getVal('investigationStatus') || null;
            d.investigationAgency = getVal('investigationAgency') || null;
            d.organisationComments = getVal('organisationComments') || null;
            d.manufacturerAdvised = getChecked('manufacturerAdvised');
            d.fdrRetained = getChecked('fdrRetained');
            break;
        case 7:
            d.severity = getNum('severityLevel');
            d.probability = getNum('probabilityLevel');
            break;
    }
    return d;
}

function validateSection(sectionIdx) {
    const d = gatherSectionData(sectionIdx);
    const errors = [];
    switch (sectionIdx) {
        case 0:
            if (!d.reporterName) errors.push('Full name is required');
            if (!d.reporterRole) errors.push('Role is required');
            if (!d.reporterOrganisation) errors.push('Organisation is required');
            if (!d.reporterEmail) errors.push('Email is required');
            if (d.reporterEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.reporterEmail)) errors.push('Invalid email format');
            break;
        case 1:
            if (!d.aircraftMake) errors.push('Aircraft make is required');
            if (!d.aircraftModel) errors.push('Aircraft model is required');
            if (!d.aircraftReg) errors.push('Registration is required');
            if (!d.aircraftCategory) errors.push('Aircraft category is required');
            if (!d.operator) errors.push('Operator is required');
            break;
        case 2:
            break;
        case 3:
            if (!d.flightPhase) errors.push('Flight phase is required');
            if (!d.flightType) errors.push('Flight type is required');
            break;
        case 4:
            break;
        case 5:
            if (!d.occurrenceDate) errors.push('Date/time is required');
            if (!d.occurrenceType) errors.push('Occurrence type is required');
            if (!d.occurrenceClass) errors.push('Occurrence class is required');
            if (!d.location) errors.push('Location is required');
            if (!d.narrative || d.narrative.length < 10) errors.push('Narrative must be at least 10 characters');
            break;
        case 6:
            if (!d.occurrenceCategory) errors.push('Occurrence category is required');
            break;
        case 7:
            break;
    }
    return { valid: errors.length === 0, errors };
}

function updateSectionStatus(sectionIdx) {
    const { valid, errors } = validateSection(sectionIdx);
    const statusEl = document.getElementById('status' + sectionIdx);
    if (!statusEl) return;
    if (valid) {
        statusEl.className = 'status-icon completed';
        statusEl.innerHTML = '<i class="fas fa-check-circle"></i>';
    } else if (sectionIdx === 2 || sectionIdx === 4 || sectionIdx === 7) {
        statusEl.className = 'status-icon completed';
        statusEl.innerHTML = '<i class="fas fa-check-circle"></i>';
    } else {
        statusEl.className = 'status-icon pending';
        statusEl.innerHTML = '<i class="fas fa-circle"></i>';
    }
}

function updateProgress() {
    let completed = 0;
    for (let i = 0; i < totalSections; i++) {
        const { valid } = validateSection(i);
        if (valid || i === 2 || i === 4 || i === 7) completed++;
    }
    const pct = Math.round((completed / totalSections) * 100);
    document.getElementById('progressFill').style.width = pct + '%';
}

function showSection(idx) {
    const panels = document.querySelectorAll('.section-panel');
    panels.forEach(p => p.classList.remove('active'));
    panels[idx].classList.add('active');

    const navs = document.querySelectorAll('.nav-section');
    navs.forEach(n => n.classList.remove('active'));
    navs[idx].classList.add('active');

    document.getElementById('prevBtn').style.display = idx === 0 ? 'none' : 'inline-block';
    const isLast = idx === totalSections - 1;
    document.getElementById('nextBtn').style.display = isLast ? 'none' : 'inline-block';
    document.getElementById('submitBtn').style.display = isLast ? 'inline-block' : 'none';

    currentSection = idx;

    if (currentSection === totalSections - 1) {
        buildReview();
        updateRiskDisplay();
    }

    updateSectionStatus(idx);
    updateProgress();
    document.querySelector('.mor-content').scrollTop = 0;
}

function nextSection() {
    const { valid, errors } = validateSection(currentSection);
    if (currentSection !== 2 && currentSection !== 4 && currentSection !== 7) {
        if (!valid) {
            document.getElementById('errorText').textContent = errors.join('; ');
            document.getElementById('errorMessage').style.display = 'block';
            setTimeout(() => document.getElementById('errorMessage').style.display = 'none', 3000);
            return;
        }
    }
    document.getElementById('errorMessage').style.display = 'none';
    if (currentSection < totalSections - 1) showSection(currentSection + 1);
}

function prevSection() {
    if (currentSection > 0) showSection(currentSection - 1);
    document.getElementById('errorMessage').style.display = 'none';
}

function buildReview() {
    const container = document.getElementById('reviewContainer');
    let html = '';
    const sections = ['Reporter', 'Aircraft', 'Engine/Propeller', 'Flight', 'People', 'Occurrence', 'Category/Factors'];
    const sectionKeys = [
        ['reporterName', 'reporterRole', 'reporterOrganisation', 'reporterEmail', 'reporterPhone'],
        ['aircraftMake', 'aircraftModel', 'aircraftReg', 'aircraftSerial', 'aircraftCategory', 'operator', 'operatorIcao', 'etops'],
        ['engineMake', 'engineModel', 'engineSerial', 'propellerMake', 'propellerModel'],
        ['flightPhase', 'flightType', 'flightNumber', 'callSign', 'departureAirport', 'destinationAirport'],
        ['crewCount', 'passengerCount', 'fatalInjuries', 'seriousInjuries', 'minorInjuries'],
        ['occurrenceType', 'occurrenceClass', 'location', 'country', 'latitude', 'longitude', 'narrative'],
        ['occurrenceCategory', 'humanFactors', 'investigationStatus', 'investigationAgency', 'manufacturerAdvised', 'fdrRetained'],
    ];
    const labels = {
        reporterName: 'Name', reporterRole: 'Role', reporterOrganisation: 'Organisation',
        reporterEmail: 'Email', reporterPhone: 'Phone',
        aircraftMake: 'Make', aircraftModel: 'Model', aircraftReg: 'Registration',
        aircraftSerial: 'Serial No.', aircraftCategory: 'Category', operator: 'Operator',
        operatorIcao: 'Operator ICAO', etops: 'ETOPS',
        engineMake: 'Engine Make', engineModel: 'Engine Model', engineSerial: 'Engine Serial',
        propellerMake: 'Propeller Make', propellerModel: 'Propeller Model',
        flightPhase: 'Phase', flightType: 'Type', flightNumber: 'Flight No.',
        callSign: 'Call Sign', departureAirport: 'Departure', destinationAirport: 'Destination',
        crewCount: 'Crew', passengerCount: 'Passengers', fatalInjuries: 'Fatal',
        seriousInjuries: 'Serious', minorInjuries: 'Minor',
        occurrenceType: 'Type', occurrenceClass: 'Class', location: 'Location',
        country: 'Country', latitude: 'Latitude', longitude: 'Longitude',
        narrative: 'Narrative',
        occurrenceCategory: 'Category', humanFactors: 'Human Factors',
        investigationStatus: 'Investigation Status', investigationAgency: 'Investigation Agency',
        manufacturerAdvised: 'Manufacturer Advised', fdrRetained: 'FDR/CVR Retained',
    };
    for (let i = 0; i < sections.length; i++) {
        const data = gatherSectionData(i);
        const keys = sectionKeys[i];
        let hasData = keys.some(k => {
            const v = data[k];
            return v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0) && v !== false;
        });
        if (!hasData) continue;
        html += '<div class="review-section"><h4>' + sections[i] + '</h4>';
        for (const k of keys) {
            let v = data[k];
            if (v === null || v === undefined || v === '' || v === false) continue;
            if (Array.isArray(v) && v.length === 0) continue;
            if (Array.isArray(v)) v = v.join(', ');
            if (typeof v === 'boolean') v = v ? 'Yes' : 'No';
            html += '<div class="review-row"><span class="review-label">' + (labels[k] || k) + '</span><span class="review-value">' + v + '</span></div>';
        }
        html += '</div>';
    }
    container.innerHTML = html || '<p class="form-hint">No data entered yet.</p>';
}

function updateRiskDisplay() {
    const sev = getNum('severityLevel');
    const prob = getNum('probabilityLevel');
    const el = document.getElementById('riskIndexValue');
    if (sev !== null && prob !== null && sev >= 1 && sev <= 5 && prob >= 1 && prob <= 5) {
        const idx = sev * prob;
        el.textContent = idx;
        let color;
        if (idx <= 3) color = 'var(--color-success)';
        else if (idx <= 7) color = '#e67e22';
        else color = 'var(--color-danger)';
        el.style.color = color;
    } else {
        el.textContent = '—';
        el.style.color = 'inherit';
    }
}

function gatherAllData() {
    const d = {};
    for (let i = 0; i < totalSections; i++) {
        Object.assign(d, gatherSectionData(i));
    }
    d.occurrence_date_time = d.occurrenceDate;
    delete d.occurrenceDate;
    d.occurrence_location = d.location;
    delete d.location;
    d.occurrence_country = d.country;
    delete d.country;
    d.occurrence_latitude = d.latitude;
    delete d.latitude;
    d.occurrence_longitude = d.longitude;
    delete d.longitude;
    d.aircraft_registration = d.aircraftReg;
    delete d.aircraftReg;
    d.aircraft_serial_number = d.aircraftSerial;
    delete d.aircraftSerial;
    d.operator_icao = d.operatorIcao;
    delete d.operatorIcao;
    d.engine_serial_number = d.engineSerial;
    delete d.engineSerial;
    d.propeller_make = d.propellerMake;
    delete d.propellerMake;
    d.propeller_model = d.propellerModel;
    delete d.propellerModel;
    d.flight_number = d.flightNumber;
    delete d.flightNumber;
    d.call_sign = d.callSign;
    delete d.callSign;
    d.departure_airport = d.departureAirport;
    delete d.departureAirport;
    d.destination_airport = d.destinationAirport;
    delete d.destinationAirport;
    d.crew_count = d.crewCount;
    delete d.crewCount;
    d.passenger_count = d.passengerCount;
    delete d.passengerCount;
    d.fatal_injuries = d.fatalInjuries;
    delete d.fatalInjuries;
    d.serious_injuries = d.seriousInjuries;
    delete d.seriousInjuries;
    d.minor_injuries = d.minorInjuries;
    delete d.minorInjuries;
    d.occurrence_type = d.occurrenceType;
    delete d.occurrenceType;
    d.occurrence_class = d.occurrenceClass;
    delete d.occurrenceClass;
    d.occurrence_category = d.occurrenceCategory;
    delete d.occurrenceCategory;
    d.human_factors = d.humanFactors;
    delete d.humanFactors;
    d.contributing_factors = d.contributingFactors;
    delete d.contributingFactors;
    d.investigation_status = d.investigationStatus;
    delete d.investigationStatus;
    d.investigation_agency = d.investigationAgency;
    delete d.investigationAgency;
    d.organisation_comments = d.organisationComments;
    delete d.organisationComments;
    d.manufacturer_advised = d.manufacturerAdvised;
    delete d.manufacturerAdvised;
    d.fdr_data_retained = d.fdrRetained;
    delete d.fdrRetained;
    d.reporter_name = d.reporterName;
    delete d.reporterName;
    d.reporter_role = d.reporterRole;
    delete d.reporterRole;
    d.reporter_email = d.reporterEmail;
    delete d.reporterEmail;
    d.reporter_phone = d.reporterPhone;
    delete d.reporterPhone;
    d.reporter_organisation = d.reporterOrganisation;
    delete d.reporterOrganisation;
    d.severity = d.severity;
    d.probability = d.probability;
    d.aircraft_category = d.aircraftCategory;
    delete d.aircraftCategory;
    d.etops = d.etops || false;
    d.flight_phase = d.flightPhase;
    delete d.flightPhase;
    d.flight_type = d.flightType;
    delete d.flightType;
    d.aircraft_make = d.aircraftMake;
    delete d.aircraftMake;
    d.aircraft_model = d.aircraftModel;
    delete d.aircraftModel;
    d.engine_make = d.engineMake;
    delete d.engineMake;
    d.engine_model = d.engineModel;
    delete d.engineModel;
    d.operator = d.operator;
    d.narrative = d.narrative;
    d.country = d.occurrence_country;
    d.location = d.occurrence_location;
    return d;
}

async function submitMor() {
    if (!getChecked('confirmGoodFaith')) {
        document.getElementById('errorText').textContent = 'Please confirm the information is factual.';
        document.getElementById('errorMessage').style.display = 'block';
        return;
    }
    for (let i = 0; i < totalSections; i++) {
        if (i === 2 || i === 4 || i === 7) continue;
        const { valid, errors } = validateSection(i);
        if (!valid) {
            showSection(i);
            document.getElementById('errorText').textContent = errors.join('; ');
            document.getElementById('errorMessage').style.display = 'block';
            return;
        }
    }

    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';

    try {
        const user = await getCurrentUser();
        if (!user) {
            window.location.href = '/login.html';
            return;
        }

        const payload = gatherAllData();
        payload.reporting_date = new Date().toISOString();

        const token = await user.getIdToken();
        const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
        const response = await fetch(baseUrl + '/api/v1/reports/mor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token,
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || 'HTTP ' + response.status);
        }

        const result = await response.json();
        document.getElementById('successText').textContent = 'MOR submitted successfully! Reference: ' + result.id;
        document.getElementById('successMessage').style.display = 'block';
        document.getElementById('submitBtn').style.display = 'none';
        document.getElementById('nextBtn').style.display = 'none';

    } catch (error) {
        document.getElementById('errorText').textContent = error.message || 'Error submitting report.';
        document.getElementById('errorMessage').style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Report';
    }
}

document.addEventListener('DOMContentLoaded', async function () {
    const user = await getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }

    const tenantId = user.tenantId || getTenantFromSubdomain();
    if (!tenantId) {
        document.getElementById('tenantName').textContent = 'No Tenant Assigned';
        return;
    }
    document.getElementById('tenantName').textContent = tenantId.replace('-', ' ').toUpperCase();

    // Tenant-classification-aware ICAO ADREP category filter: flight-specific
    // categories (LOCI/CFIT/MAC/ARC/WX) only populate for AOC-holding airlines.
    if (typeof getApplicableOccurrenceCategories === 'function') {
        const allowed = getApplicableOccurrenceCategories(tenantId);
        const catSelect = document.getElementById('occurrenceCategory');
        if (catSelect) {
            Array.from(catSelect.options).forEach((opt) => {
                if (!allowed.includes(opt.value)) opt.remove();
            });
        }
    }

    const now = new Date();
    const pad = (n) => n.toString().padStart(2, '0');
    document.getElementById('occurrenceDate').value =
        now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + 'T' +
        pad(now.getHours()) + ':' + pad(now.getMinutes());

    if (user.email) {
        document.getElementById('reporterEmail').value = user.email;
    }

    document.querySelectorAll('.nav-section').forEach(el => {
        el.addEventListener('click', function () {
            const idx = parseInt(this.dataset.section);
            if (idx < currentSection) {
                showSection(idx);
            } else if (idx > currentSection) {
                const { valid, errors } = validateSection(currentSection);
                if (currentSection !== 2 && currentSection !== 4 && !valid) {
                    document.getElementById('errorText').textContent = errors.join('; ');
                    document.getElementById('errorMessage').style.display = 'block';
                    setTimeout(() => document.getElementById('errorMessage').style.display = 'none', 3000);
                    return;
                }
                showSection(idx);
            }
        });
    });

    document.querySelectorAll('.form-control, .hf-checkbox').forEach(el => {
        el.addEventListener('change', function () {
            const panel = this.closest('.section-panel');
            if (panel) {
                const idx = parseInt(panel.dataset.section);
                updateSectionStatus(idx);
                updateProgress();
            }
        });
        el.addEventListener('input', function () {
            const panel = this.closest('.section-panel');
            if (panel) {
                const idx = parseInt(panel.dataset.section);
                updateSectionStatus(idx);
                updateProgress();
            }
        });
    });

    showSection(0);
});
