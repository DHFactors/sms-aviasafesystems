function dashboardDaysParam(days) {
    let n = Number(days);
    if (!isFinite(n) || n < 0) n = 0;
    return `days=${Math.floor(n)}`;
}

const DashboardAPI = {
    getOverview: (days = 90) => ApiClient.get(`/api/dashboard/overview?${dashboardDaysParam(days)}`),

    getRecentReports: (days = 90, page = 1, pageSize = 10) =>
        ApiClient.get(`/api/dashboard/recent?${dashboardDaysParam(days)}&page=${page}&page_size=${pageSize}`),

    getRiskDistribution: (days = 90) =>
        ApiClient.get(`/api/dashboard/risk?${dashboardDaysParam(days)}`),

    getMonthlyTrends: (days = 180) =>
        ApiClient.get(`/api/dashboard/trends?${dashboardDaysParam(days)}`),

    getSSPRiskTrends: (days = 730) => {
        const n = Number(days) > 0 ? Number(days) : 1825;
        return ApiClient.get(`/api/dashboard/risk-trends?days=${n}`);
    },

    getHazardFrequency: (days = 90) =>
        ApiClient.get(`/api/dashboard/hazards?${dashboardDaysParam(days)}`),

    getActionsSummary: (days = 90) =>
        ApiClient.get(`/api/dashboard/actions?${dashboardDaysParam(days)}`),
};
