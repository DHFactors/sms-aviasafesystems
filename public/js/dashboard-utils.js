window.ICAO_THRESHOLDS = window.ICAO_THRESHOLDS || { lowMax: 5, mediumMax: 9, highMax: 15 };

const ICAO_COLORS = {
    Low: '#34a853',
    Medium: '#f9ab00',
    High: '#f57c00',
    'Very High': '#ea4335',
};

const ICAO_RISK_LABELS = ['Low', 'Medium', 'High', 'Very High'];

function classifyRisk(riskIndex) {
    if (riskIndex === null || riskIndex === undefined) return 'Unknown';
    if (riskIndex <= ICAO_THRESHOLDS.lowMax) return 'Low';
    if (riskIndex <= ICAO_THRESHOLDS.mediumMax) return 'Medium';
    if (riskIndex <= ICAO_THRESHOLDS.highMax) return 'High';
    return 'Very High';
}

function getRiskColor(riskLevel) {
    return ICAO_COLORS[riskLevel] || '#5f6368';
}

function getRiskBadgeClass(riskLevel) {
    const map = { Low: 'badge-low', Medium: 'badge-medium', High: 'badge-high', 'Very High': 'badge-critical' };
    return map[riskLevel] || 'badge-default';
}

function aggregateRiskDistribution(reports) {
    const dist = { Low: 0, Medium: 0, High: 0, 'Very High': 0 };
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
