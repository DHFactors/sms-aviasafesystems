let currentSection = 0;
const totalSections = 6;

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
            d.isAnonymous = getChecked('toggleAnonymous');
            if (!d.isAnonymous) {
                d.reporterName = getVal('reporterName') || null;
                d.reporterRole = getVal('reporterRole') || null;
                d.reporterOrganisation = getVal('reporterOrganisation') || null;
                d.reporterEmail = getVal('reporterEmail') || null;
                d.reporterPhone = getVal('reporterPhone') || null;
            } else {
                d.reporterName = null;
                d.reporterRole = null;
                d.reporterOrganisation = null;
                d.reporterEmail = null;
                d.reporterPhone = null;
            }
            break;
        case 1:
            d.aircraftMake = getVal('aircraftMake') || null;
            d.aircraftModel = getVal('aircraftModel') || null;
            d.aircraftReg = getVal('aircraftReg') || null;
            d.aircraftSerial = getVal('aircraftSerial') || null;
            d.aircraftCategory = getVal('aircraftCategory') || null;
            d.operator = getVal('operator') || null;
            d.operatorIcao = getVal('operatorIcao') || null;
            break;
        case 2:
            d.flightPhase = getVal('flightPhase') || null;
            d.flightType = getVal('flightType') || null;
            d.flightNumber = getVal('flightNumber') || null;
            d.callSign = getVal('callSign') || null;
            d.departureAirport = getVal('departureAirport')?.toUpperCase() || null;
            d.destinationAirport = getVal('destinationAirport')?.toUpperCase() || null;
            break;
        case 3:
            d.occurrenceDate = getVal('occurrenceDate');
            d.occurrenceType = getVal('occurrenceType') || null;
            d.occurrenceClass = getVal('occurrenceClass') || null;
            d.location = getVal('location');
            d.country = getVal('country') || null;
            d.latitude = getFloat('latitude');
            d.longitude = getFloat('longitude');
            d.occurrenceCategory = getVal('occurrenceCategory') || null;
            const hfChecks = document.querySelectorAll('.hf-checkbox:checked');
            d.humanFactors = Array.from(hfChecks).map(cb => cb.value);
            d.narrative = getVal('narrative');
            break;
        case 4:
            d.severity = getNum('severityLevel');
            d.probability = getNum('probabilityLevel');
            break;
        case 5:
            break;
    }
    return d;
}

function validateSection(sectionIdx) {
    const d = gatherSectionData(sectionIdx);
    const errors = [];
    switch (sectionIdx) {
        case 0:
            break;
        case 1:
            break;
        case 2:
            break;
        case 3:
            if (!d.occurrenceDate) errors.push('Date/time is required');
            if (!d.location) errors.push('Location is required');
            if (!d.narrative || d.narrative.length < 10) errors.push('Narrative must be at least 10 characters');
            break;
        case 4:
            break;
        case 5:
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
    } else if (sectionIdx === 0 || sectionIdx === 1 || sectionIdx === 2 || sectionIdx === 4 || sectionIdx === 5) {
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
        if (valid || i === 0 || i === 1 || i === 2 || i === 4 || i === 5) completed++;
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
    document.querySelector('.vsr-content').scrollTop = 0;
}

function nextSection() {
    const { valid, errors } = validateSection(currentSection);
    if (currentSection === 3) {
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
    const sections = ['About You', 'Aircraft', 'Flight', 'Occurrence', 'Risk Assessment'];
    const sectionKeys = [
        ['reporterName', 'reporterRole', 'reporterOrganisation', 'reporterEmail', 'reporterPhone', 'isAnonymous'],
        ['aircraftMake', 'aircraftModel', 'aircraftReg', 'aircraftSerial', 'aircraftCategory', 'operator', 'operatorIcao'],
        ['flightPhase', 'flightType', 'flightNumber', 'callSign', 'departureAirport', 'destinationAirport'],
        ['occurrenceType', 'occurrenceClass', 'location', 'country', 'latitude', 'longitude', 'occurrenceCategory', 'humanFactors', 'narrative'],
        ['severity', 'probability'],
    ];
    const labels = {
        reporterName: 'Name', reporterRole: 'Role', reporterOrganisation: 'Organisation',
        reporterEmail: 'Email', reporterPhone: 'Phone', isAnonymous: 'Anonymous',
        aircraftMake: 'Make', aircraftModel: 'Model', aircraftReg: 'Registration',
        aircraftSerial: 'Serial No.', aircraftCategory: 'Category', operator: 'Operator',
        operatorIcao: 'Operator ICAO',
        flightPhase: 'Phase', flightType: 'Type', flightNumber: 'Flight No.',
        callSign: 'Call Sign', departureAirport: 'Departure', destinationAirport: 'Destination',
        occurrenceType: 'Type', occurrenceClass: 'Class', location: 'Location',
        country: 'Country', latitude: 'Latitude', longitude: 'Longitude',
        occurrenceCategory: 'Category', humanFactors: 'Human Factors',
        narrative: 'Narrative', severity: 'Severity', probability: 'Probability',
    };
    for (let i = 0; i < sections.length; i++) {
        const data = gatherSectionData(i);
        const keys = sectionKeys[i];
        let hasData = keys.some(k => {
            const v = data[k];
            return v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0);
        });
        if (!hasData) continue;
        html += '<div class="review-section"><h4>' + sections[i] + '</h4>';
        for (const k of keys) {
            let v = data[k];
            if (v === null || v === undefined || v === '' || v === false) continue;
            if (Array.isArray(v) && v.length === 0) continue;
            if (k === 'isAnonymous' && v === true) { v = 'Yes — Report is anonymous'; }
            else if (k === 'isAnonymous') continue;
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

function toggleAnonymity() {
    const isAnonymous = getChecked('toggleAnonymous');
    const fields = document.getElementById('reporterFields');
    fields.classList.toggle('visible', !isAnonymous);
    updateSectionStatus(0);
    updateProgress();
}

function gatherAllData() {
    const d = {};
    for (let i = 0; i < totalSections; i++) {
        Object.assign(d, gatherSectionData(i));
    }
    d.reporting_date = new Date().toISOString();
    d.is_anonymous = d.isAnonymous || false;
    delete d.isAnonymous;
    d.occurrence_date = d.occurrenceDate;
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
    d.flight_number = d.flightNumber;
    delete d.flightNumber;
    d.call_sign = d.callSign;
    delete d.callSign;
    d.departure_airport = d.departureAirport;
    delete d.departureAirport;
    d.destination_airport = d.destinationAirport;
    delete d.destinationAirport;
    d.occurrence_type = d.occurrenceType;
    delete d.occurrenceType;
    d.occurrence_class = d.occurrenceClass;
    delete d.occurrenceClass;
    d.occurrence_category = d.occurrenceCategory;
    delete d.occurrenceCategory;
    d.human_factors = d.humanFactors && d.humanFactors.length > 0 ? d.humanFactors : null;
    delete d.humanFactors;
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
    d.severity_level = d.severity;
    delete d.severity;
    d.probability_level = d.probability;
    delete d.probability;
    d.aircraft_make = d.aircraftMake;
    delete d.aircraftMake;
    d.aircraft_model = d.aircraftModel;
    delete d.aircraftModel;
    d.aircraft_category = d.aircraftCategory;
    delete d.aircraftCategory;
    d.flight_phase = d.flightPhase;
    delete d.flightPhase;
    d.flight_type = d.flightType;
    delete d.flightType;
    d.report_type = 'voluntary';
    return d;
}

async function submitVsr() {
    if (!getChecked('confirmGoodFaith')) {
        document.getElementById('errorText').textContent = 'Please confirm the report is submitted in good faith.';
        document.getElementById('errorMessage').style.display = 'block';
        return;
    }
    for (let i = 0; i < totalSections; i++) {
        if (i !== 3) continue;
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
        const token = await user.getIdToken();
        const baseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || '';
        const response = await fetch(baseUrl + '/api/v1/reports/vsr', {
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
        document.getElementById('successText').textContent = 'Report submitted successfully! Reference: ' + result.id;
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
            const keep = (opt) => allowed.includes(opt.value);
            Array.from(catSelect.options).forEach((opt) => {
                if (!keep(opt)) opt.remove();
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

    document.getElementById('toggleAnonymous').addEventListener('change', toggleAnonymity);

    document.querySelectorAll('.nav-section').forEach(el => {
        el.addEventListener('click', function () {
            const idx = parseInt(this.dataset.section);
            if (idx < currentSection) {
                showSection(idx);
            } else if (idx > currentSection) {
                const { valid, errors } = validateSection(currentSection);
                if (currentSection === 3 && !valid) {
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
