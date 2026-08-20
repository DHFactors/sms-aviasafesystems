// CAAN CAR-19 aligned 3-tier risk scheme. `mediumMax` is retained for backward
// compatibility with stored tenant configs, but classification uses only
// `lowMax` / `highMax`: <= lowMax -> Low (Level II), <= highMax -> High
// (Level III), > highMax -> Very High (Level IV).
window.ICAO_THRESHOLDS = window.ICAO_THRESHOLDS || { lowMax: 5, mediumMax: 9, highMax: 15 };

const ICAO_COLORS = {
    Low: '#34a853',
    High: '#f9ab00',
    'Very High': '#ea4335',
};

const ICAO_RISK_LABELS = ['Low', 'High', 'Very High'];

// Normalise any legacy risk label/outcome into the 3-tier level. Mirrors
// backend/app/services/risk_matrix.py#normalize_tolerability:
// Low/Acceptable -> Low; Very High/Critical/Intolerable -> Very High;
// Medium/Moderate/High/Tolerable/unknown -> High.
function normalizeRiskLevel(level) {
    if (level === null || level === undefined) return 'High';
    const norm = String(level).trim().toUpperCase();
    if (norm === 'LOW' || norm === 'ACCEPTABLE' || norm === 'LEVEL II') return 'Low';
    if (norm === 'VERY HIGH' || norm === 'CRITICAL' || norm === 'INTOLERABLE' || norm === 'SEVERE' || norm === 'LEVEL IV') return 'Very High';
    return 'High';
}

function classifyRisk(riskIndex) {
    if (riskIndex === null || riskIndex === undefined) return 'Unknown';
    if (riskIndex <= ICAO_THRESHOLDS.lowMax) return 'Low';
    if (riskIndex <= ICAO_THRESHOLDS.highMax) return 'High';
    return 'Very High';
}

function getRiskColor(riskLevel) {
    return ICAO_COLORS[normalizeRiskLevel(riskLevel)] || '#5f6368';
}

function getRiskBadgeClass(riskLevel) {
    const map = { Low: 'badge-low', High: 'badge-high', 'Very High': 'badge-critical' };
    return map[normalizeRiskLevel(riskLevel)] || 'badge-default';
}

function aggregateRiskDistribution(reports) {
    const dist = { Low: 0, High: 0, 'Very High': 0 };
    for (const r of reports) {
        const level = classifyRisk(r.risk_index ?? r.riskIndex);
        if (dist.hasOwnProperty(level)) dist[level]++;
    }
    return dist;
}

function aggregateTopRisks(reports, limit = 10) {
    const counts = {};
    for (const r of reports) {
        const cat = r.occurrence_category || r.occurrenceType || 'Unknown';
        counts[cat] = (counts[cat] || 0) + 1;
    }
    return Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, limit)
        .map(([category, count]) => ({ category, count }));
}

function aggregateHeatMap(reports) {
    const hm = {};
    for (let s = 1; s <= 5; s++)
        for (let p = 1; p <= 5; p++)
            hm[`${s}x${p}`] = 0;
    for (const r of reports) {
        const s = r.severity_level ?? r.severity;
        const p = r.probability_level ?? r.probability;
        if (s >= 1 && s <= 5 && p >= 1 && p <= 5)
            hm[`${s}x${p}`] = (hm[`${s}x${p}`] || 0) + 1;
    }
    return hm;
}
