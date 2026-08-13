/**
 * FOLDER/FILE PATH: public/survey/app.js
 * VERSION NO: 3.1.0
 * DATE: 2026-08-07
 * PURPOSE OF THE FILE: Core multi-tenant survey runtime engine. Dynamically resolves 
 * the active aviation tenant profile (airline or regulator) from subdomains or URL parameters,
 * renders bilingual ICAO-aligned questions from the master data contract, manages 
 * client interaction states, and submits validated responses to the backend
 * survey endpoint (POST /api/v1/surveys) which validates, scores, and persists them.
 */

import { MASTER_QUESTIONS } from './default_q.js';

// ── STATE MANAGEMENT ──
let currentLang = 'en';
let activeTenantId = 'unknown-tenant';
const TOTAL_QUESTIONS = MASTER_QUESTIONS.length;

// Static localization bundles for application shell
const i18n = {
    en: {
        aware: "Aware", unaware: "Unaware",
        agree5: "Strongly Agree", agree4: "Agree", opinion3: "No Opinion", disagree2: "Disagree", disagree1: "Strongly Disagree",
        progressOf: "of", progressAns: "answered",
        validationErr: "⚠️ Please answer all 23 questions before submitting.",
        submitting: "Submitting response securely...",
        submitErr: "Submission failed. Please check your network connection.",
        successTitle: "Submission Successful",
        successBody: "Your response has been recorded anonymously within the tenant safety system.",
        surveyTitle: "SMS Maturity Assessment",
        surveySubtitle: "Based on Safety Management System's 4 pillars and 12 elements. This survey is conducted aligning Annex 19, Doc 9859, Doc 10159 and state requirements."
    },
    ne: {
        aware: "जानकार", unaware: "अजानकार",
        agree5: "कडा सहमत", agree4: "सहमत", opinion3: "कुनै राय छैन", disagree2: "असहमत", disagree1: "कडा असहमत",
        progressOf: "मध्ये", progressAns: "उत्तर दिइएको",
        validationErr: "⚠️ कृपया पेश गर्नुअघि सबै २३ प्रश्नहरूको उत्तर दिनुहोस्।",
        submitting: "विवरण सुरक्षित रूपमा पेश हुँदैछ...",
        submitErr: "त्रुटि! कृपया नेटवर्क जडान जाँच गर्नुहोस्।",
        successTitle: "सफलतापूर्वक पेश भयो",
        successBody: "तपाईंको जवाफ प्रणालीमा अज्ञात रूपमा सुरक्षित गरिएको छ।",
        surveyTitle: "SMS स्वास्थ्य मूल्याङ्कन",
        surveySubtitle: "सुरक्षा व्यवस्थापन प्रणालीका ४ स्तम्भ र १२ तत्वहरूमा आधारित। यो सर्वेक्षण Annex 19, Doc 9859, Doc 10159 र राज्यका आवश्यकताहरूसँग मिलाएर सञ्चालन गरिएको छ।"
    }
};

// ── DYNAMIC TENANT RESOLUTION ENGINE ──
function resolveTenantContext() {
    const host = window.location.hostname;
    const urlParams = new URLSearchParams(window.location.search);

    // Sandbox URL tracking query parameter fallback (?tenant=sita-air)
    if (urlParams.has('tenant')) {
        return urlParams.get('tenant').toLowerCase();
    }

    // Production Domain Route Mapping Matrix
    const routes = {
        'smssurvey.gsacharya.com': 'sita-air',
        'sms.nac.com.np': 'nepal-airlines',
        'ssp.caanepal.gov.np': 'caan-ops', // CAAN operating as an infrastructure service provider tenant
        'localhost': 'sita-air' // Development environment bypass targeting test instance
    };

    return routes[host] || 'unknown-tenant';
}

// ── INITIALIZATION LIFECYCLE ──
document.addEventListener('DOMContentLoaded', async () => {
    activeTenantId = resolveTenantContext();

    // No tenant context (no ?tenant= and no recognized hostname route):
    // show the informational popup and redirect home after the countdown.
    if (activeTenantId === 'unknown-tenant') {
        showTenantPopup();
        return;
    }

    initInterfaceHooks();
});

// ── POPUP FOR VISITORS WITHOUT A TENANT CONTEXT ──
function showTenantPopup() {
    document.getElementById('loadingScreen')?.classList.add('hidden');
    const notFound = document.getElementById('notFoundScreen');
    if (notFound) notFound.style.display = 'none';
    const popup = document.getElementById('surveyPopup');
    if (!popup) {
        window.location.href = '/';
        return;
    }
    popup.style.display = 'flex';
    startPopupCountdown();
}

function startPopupCountdown() {
    const countdownSpan = document.getElementById('countdownTimer');
    let countdown = 10;
    if (countdownSpan) countdownSpan.textContent = countdown;
    const timerInterval = setInterval(function () {
        countdown -= 1;
        if (countdownSpan) countdownSpan.textContent = Math.max(countdown, 0);
        if (countdown <= 0) {
            clearInterval(timerInterval);
            closePopupAndRedirect();
        }
    }, 1000);
}

function closePopupAndRedirect() {
    const popup = document.getElementById('surveyPopup');
    if (popup) popup.style.display = 'none';
    window.location.href = '/';
}

function initInterfaceHooks() {
    document.getElementById('loadingScreen')?.classList.add('hidden');
    document.getElementById('mainContent').style.display = 'block';

    renderBilingualQuestions();
    updateProgressMetrics();
    updateShellText();
    loadSurveyInstructions();

    // Wire up UX event drivers
    document.getElementById('btn-en')?.addEventListener('click', () => switchLanguage('en'));
    document.getElementById('btn-ne')?.addEventListener('click', () => switchLanguage('ne'));
    document.getElementById('surveyForm')?.addEventListener('submit', (e) => executeSubmission(e));
    const popupCloseBtn = document.getElementById('popupCloseBtn');
    if (popupCloseBtn) popupCloseBtn.addEventListener('click', closePopupAndRedirect);
    const popup = document.getElementById('surveyPopup');
    if (popup) popup.addEventListener('click', function (e) {
        if (e.target === popup) closePopupAndRedirect();
    });
}

function updateShellText() {
    const ui = i18n[currentLang];
    const titleEl = document.getElementById('headerTitle');
    const subtitleEl = document.getElementById('headerSubtitle');
    if (titleEl) titleEl.textContent = ui.surveyTitle;
    if (subtitleEl) subtitleEl.textContent = ui.surveySubtitle;
}

function titleCaseTenant(tenantId) {
    return String(tenantId || '')
        .replace(/-/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── SURVEY INSTRUCTIONS (from tenant config, auth optional) ──
function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function renderInline(text) {
    return escapeHtml(text)
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderMarkdown(text) {
    const lines = String(text || '').split(/\r?\n/);
    const out = [];
    let listBuffer = null;

    const flushList = () => {
        if (listBuffer) {
            out.push('<ul>' + listBuffer.join('') + '</ul>');
            listBuffer = null;
        }
    };

    for (const raw of lines) {
        const trimmed = raw.trim();
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            if (!listBuffer) listBuffer = [];
            listBuffer.push('<li>' + renderInline(trimmed.slice(2)) + '</li>');
            continue;
        }
        flushList();
        if (!trimmed) continue;
        const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
        if (heading) {
            const level = Math.min(heading[1].length + 1, 6);
            out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        } else {
            out.push('<p>' + renderInline(trimmed) + '</p>');
        }
    }
    flushList();
    return out.join('');
}

async function loadSurveyInstructions() {
    const banner = document.getElementById('instructionsBanner');
    const tenantNameEl = document.getElementById('tenantName');
    try {
        const response = await fetch(getApiBaseUrl() + '/api/v1/tenants/' + encodeURIComponent(activeTenantId) + '/config');
        if (!response.ok) {
            showTenantPopup();
            return;
        }
        const payload = await response.json();
        const tenantName = payload?.data?.name;
        if (tenantNameEl) tenantNameEl.textContent = tenantName || titleCaseTenant(activeTenantId);
        const instructions = payload?.data?.config?.survey_instructions;
        if (!instructions || !String(instructions).trim()) {
            if (banner) banner.style.display = 'none';
        } else if (banner) {
            banner.style.display = 'block';
            banner.innerHTML = '<div class="instructions-inner">' + renderMarkdown(instructions) + '</div>';
        }
        enforceSurveyWindow(payload?.data?.surveyConfig, payload?.data?.config);
    } catch (err) {
        console.warn('Could not load survey instructions:', err);
        if (tenantNameEl) tenantNameEl.textContent = titleCaseTenant(activeTenantId);
    }
}

function enforceSurveyWindow(surveyConfig, config) {
    if (!surveyConfig && !config) return;
    const cfg = surveyConfig || {};
    const tenantConfig = config || {};

    const openDate = cfg.openDate || cfg.open_date || tenantConfig.survey_open_date;
    const closeDate = cfg.closeDate || cfg.close_date || tenantConfig.survey_close_date;

    let active = cfg.isActive;
    if (typeof active !== 'boolean') active = cfg.is_active;
    if (typeof active !== 'boolean') active = tenantConfig.is_survey_active;
    if (typeof active !== 'boolean') active = true;

    const now = new Date();
    let closed = false;
    if (active === false) {
        closed = true;
    } else {
        if (openDate && now < new Date(openDate)) closed = true;
        if (closeDate && now > new Date(closeDate)) closed = true;
    }
    if (!closed) return;

    const closedBanner = document.getElementById('surveyClosedBanner');
    if (closedBanner) {
        const reopened = active !== false && openDate && now < new Date(openDate)
            ? new Date(openDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
            : null;
        closedBanner.textContent = reopened
            ? 'This survey is currently closed. It will reopen on ' + reopened + '.'
            : 'This survey is currently closed.';
        closedBanner.style.display = 'block';
    }
    const form = document.getElementById('surveyForm');
    if (form) form.style.display = 'none';
    const progress = document.querySelector('.progress-wrap');
    if (progress) progress.style.display = 'none';
}

function getApiBaseUrl() {
    if (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) return window.APP_CONFIG.apiBaseUrl;
    const host = window.location.hostname;
    return (host.includes('beta') || host === 'localhost' || host === '127.0.0.1')
        ? 'https://sms-aviasafesystems-beta.onrender.com'
        : 'https://aviasafe-unified-platform.onrender.com';
}

// ── UI RENDERING FRAMEWORK ──
function renderBilingualQuestions() {
    const targetDiv = document.getElementById('questionsContainer');
    if (!targetDiv) return;

    targetDiv.innerHTML = '';
    const ui = i18n[currentLang];
    let activePillarCard = "";

    MASTER_QUESTIONS.forEach((q, index) => {
        // Inject structural segment breaks matching ICAO 4-Pillar framework splits
        if (q.pillar !== activePillarCard) {
            activePillarCard = q.pillar;
            const headerElement = document.createElement('div');
            headerElement.className = 'section-header-card';
            headerElement.innerHTML = `
                <div class="section-title-wrap">
                    <h3>${activePillarCard}</h3>
                </div>
            `;
            targetDiv.appendChild(headerElement);
        }

        const questionBlock = document.createElement('div');
        questionBlock.className = 'question-node';
        questionBlock.dataset.qid = q.id;

        const renderedText = currentLang === 'ne' ? q.text_ne : q.text_en;
        let controlHtml = '';

        if (q.type === 'binary') {
            controlHtml = `
                <div class="input-binary-wrap">
                    <label><input type="radio" name="${q.id}" value="true"> ${ui.aware}</label>
                    <label><input type="radio" name="${q.id}" value="false"> ${ui.unaware}</label>
                </div>
            `;
        } else {
            controlHtml = `
                <div class="input-likert-matrix">
                    <label><input type="radio" name="${q.id}" value="5"><span>${ui.agree5}</span></label>
                    <label><input type="radio" name="${q.id}" value="4"><span>${ui.agree4}</span></label>
                    <label><input type="radio" name="${q.id}" value="3"><span>${ui.opinion3}</span></label>
                    <label><input type="radio" name="${q.id}" value="2"><span>${ui.disagree2}</span></label>
                    <label><input type="radio" name="${q.id}" value="1"><span>${ui.disagree1}</span></label>
                </div>
            `;
        }

        questionBlock.innerHTML = `
            <div class="question-body">
                <span class="idx-label">${index + 1}.</span>
                <p class="txt-content">${renderedText}</p>
            </div>
            ${controlHtml}
        `;
        targetDiv.appendChild(questionBlock);
    });

    // Real-time recalculation callback hooks
    document.querySelectorAll('.question-node input[type="radio"]').forEach(radio => {
        radio.addEventListener('change', updateProgressMetrics);
    });
}

function updateProgressMetrics() {
    const itemsAnswered = document.querySelectorAll('.question-node input[type="radio"]:checked').length;
    const computedPercentage = Math.round((itemsAnswered / TOTAL_QUESTIONS) * 100);
    
    const fillTracker = document.getElementById('progressFill');
    if (fillTracker) fillTracker.style.width = `${computedPercentage}%`;

    const txtLabel = document.getElementById('progressText');
    if (txtLabel) {
        txtLabel.textContent = `${itemsAnswered} ${i18n[currentLang].progressOf} ${TOTAL_QUESTIONS} ${i18n[currentLang].progressAns}`;
    }
}

function switchLanguage(targetLang) {
    if (currentLang === targetLang) return;

    // Preserving current filled state baseline fields across structural change context shifts
    const intermediateMap = {};
    document.querySelectorAll('.question-node input[type="radio"]:checked').forEach(node => {
        intermediateMap[node.name] = node.value;
    });
    const savedComments = document.getElementById('q24_comments')?.value || '';

    currentLang = targetLang;
    document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`btn-${targetLang}`)?.classList.add('active');

    renderBilingualQuestions();

    // Re-hydrate state bindings to layout view
    Object.entries(intermediateMap).forEach(([id, val]) => {
        const inputDom = document.querySelector(`input[name="${id}"][value="${val}"]`);
        if (inputDom) inputDom.checked = true;
    });
    const commentsBox = document.getElementById('q24_comments');
    if (commentsBox) commentsBox.value = savedComments;

    updateShellText();
    updateProgressMetrics();
}

// ── BACKEND SURVEY SUBMISSION ──
async function executeSubmission(e) {
    e.preventDefault();
    const ui = i18n[currentLang];
    const formNode = e.target;
    const statusBox = document.getElementById('statusMessage');
    const actionBtn = document.getElementById('submitBtn');

    let validationPass = true;
    let fallbackScroller = null;

    // Boundary schema validation checks
    for (const q of MASTER_QUESTIONS) {
        if (!formNode.querySelector(`input[name="${q.id}"]:checked`)) {
            validationPass = false;
            const contextNode = formNode.querySelector(`[data-qid="${q.id}"]`);
            contextNode?.classList.add('missing-input-warning');
            if (!fallbackScroller) fallbackScroller = contextNode;
        } else {
            formNode.querySelector(`[data-qid="${q.id}"]`)?.classList.remove('missing-input-warning');
        }
    }

    if (!validationPass) {
        if (statusBox) {
            statusBox.className = 'status-alert-box-error';
            statusBox.textContent = ui.validationErr;
        }
        fallbackScroller?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
    }

    // Payload compilation logic mapping array objects into values
    const parseInput = id => {
        const element = formNode.querySelector(`input[name="${id}"]:checked`);
        if (!element) return null;
        return element.value === 'true' ? true : element.value === 'false' ? false : parseInt(element.value);
    };

    const answers = {};
    MASTER_QUESTIONS.forEach(q => { answers[q.id] = parseInput(q.id); });
    const comments = document.getElementById('q24_comments')?.value?.trim() || null;
    if (comments) answers['q24_comments'] = comments;

    const body = {
        tenantId: activeTenantId,
        respondentId: null,
        answers,
        department: document.getElementById('department')?.value || null,
        employee_category: document.getElementById('employee_category')?.value || null,
        years_experience: document.getElementById('years_experience')?.value || null,
        language: currentLang
    };

    // Cloud transmission configuration context
    actionBtn.disabled = true;
    if (statusBox) {
        statusBox.className = 'status-alert-box-loading';
        statusBox.textContent = ui.submitting;
    }

    try {
        const response = await fetch(getApiBaseUrl() + '/api/v1/surveys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            let message = ui.submitErr;
            try {
                const errBody = await response.json();
                const detail = errBody.detail || errBody.error?.message || errBody.message;
                if (errBody.errors) {
                    const fieldErrors = Object.entries(errBody.errors).map(([qid, msg]) => `${qid}: ${msg}`);
                    if (fieldErrors.length) message = fieldErrors.join('; ');
                } else if (typeof detail === 'string') {
                    message = detail;
                }
            } catch (_) { /* keep default message */ }
            if (statusBox) {
                statusBox.className = 'status-alert-box-error';
                statusBox.textContent = message;
            }
            actionBtn.disabled = false;
            return;
        }

        formNode.style.display = 'none';
        if (statusBox) statusBox.style.display = 'none';

        const successView = document.getElementById('successScreen');
        if (successView) {
            document.getElementById('successTitle').textContent = ui.successTitle;
            document.getElementById('successBody').textContent = ui.successBody;
            successView.style.display = 'block';
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
        console.error("Survey submission exception: ", err);
        actionBtn.disabled = false;
        if (statusBox) {
            statusBox.className = 'status-alert-box-error';
            statusBox.textContent = `${ui.submitErr} (${err.message})`;
        }
    }
}