const DashboardAPI = {
    getOverview: (days = 90) => ApiClient.get(`/api/dashboard/overview?days=${days}`),

    getRecentReports: (days = 90, page = 1, pageSize = 10) =>
        ApiClient.get(`/api/dashboard/recent?days=${days}&page=${page}&page_size=${pageSize}`),

    getRiskDistribution: (days = 90) =>
        ApiClient.get(`/api/dashboard/risk?days=${days}`),

    getMonthlyTrends: (days = 180) =>
        ApiClient.get(`/api/dashboard/trends?days=${days}`),

    getSSPRiskTrends: (days = 730) =>
        ApiClient.get(`/api/dashboard/risk-trends?days=${days}`),

    getHazardFrequency: (days = 90) =>
        ApiClient.get(`/api/dashboard/hazards?days=${days}`),

    getActionsSummary: (days = 90) =>
        ApiClient.get(`/api/dashboard/actions?days=${days}`),
};
