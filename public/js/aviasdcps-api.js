/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/aviasdcps-api.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db-beta / feat/betasms-self-service
 */

const AviaSDCPSApi = (function () {
  'use strict';

  // Base API configuration
  const API_CONFIG = {
    baseUrl: window.location.origin.includes('localhost') 
      ? 'http://localhost:8000/api/v1' 
      : 'https://aviasafe-unified-platform.onrender.com/api/v1',
    defaultTenant: 'fishtail-air'
  };

  /**
   * Retrieves the active authentication token from session storage or cookies.
   * @returns {string|null} The Bearer token or null if unauthenticated.
   */
  function getAuthToken() {
    return (
      sessionStorage.getItem('aviasafe_token') ||
      localStorage.getItem('aviasafe_token') ||
      null
    );
  }

  /**
   * Retrieves the active tenant context.
   * @returns {string} The active tenant ID.
   */
  function getActiveTenantId() {
    return (
      sessionStorage.getItem('aviasafe_tenant_id') ||
      localStorage.getItem('aviasafe_tenant_id') ||
      API_CONFIG.defaultTenant
    );
  }

  /**
   * Constructs standardized request headers including Authorization and Tenant scope.
   * @param {Object} customHeaders - Optional override or additional headers.
   * @returns {Headers} The initialized Headers object.
   */
  function buildHeaders(customHeaders = {}) {
    const headers = new Headers({
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'X-Tenant-Id': getActiveTenantId(),
      ...customHeaders
    });

    const token = getAuthToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    return headers;
  }

  /**
   * Core execution wrapper for handling HTTP requests, standardizing error shapes,
   * and intercepting session expiration (401/403).
   * @param {string} endpoint - API route path (e.g., '/hazards/stats').
   * @param {Object} options - Fetch options.
   * @returns {Promise<any>} The parsed JSON response body.
   */
  async function executeRequest(endpoint, options = {}) {
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${API_CONFIG.baseUrl}${cleanEndpoint}`;

    const config = {
      ...options,
      headers: buildHeaders(options.headers || {})
    };

    try {
      const response = await fetch(url, config);

      // Handle unauthenticated state
      if (response.status === 401) {
        console.warn('[AviaSDCPSApi] 401 Unauthorized: Redirecting to login.');
        sessionStorage.removeItem('aviasafe_token');
        if (!window.location.pathname.includes('login.html')) {
          window.location.href = '/login.html';
        }
        throw new Error('Session expired. Please log in again.');
      }

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errorJson = await response.json();
          errorDetail = errorJson.detail || errorJson.message || errorDetail;
        } catch (_) {
          // Response body was not JSON
        }
        throw new Error(errorDetail);
      }

      // Return null for 204 No Content
      if (response.status === 204) {
        return null;
      }

      return await response.json();
    } catch (error) {
      console.error(`[AviaSDCPSApi Error] ${options.method || 'GET'} ${cleanEndpoint}:`, error.message);
      throw error;
    }
  }

  // Public API methods
  return {
    /**
     * Executes an authenticated GET request.
     * @param {string} endpoint - The target endpoint.
     * @param {Object} [params] - Query parameters as key-value pairs.
     * @returns {Promise<any>}
     */
    get(endpoint, params = null) {
      let finalEndpoint = endpoint;
      if (params && typeof params === 'object') {
        const searchParams = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            searchParams.append(key, value);
          }
        });
        const queryString = searchParams.toString();
        if (queryString) {
          finalEndpoint += (finalEndpoint.includes('?') ? '&' : '?') + queryString;
        }
      }
      return executeRequest(finalEndpoint, { method: 'GET' });
    },

    /**
     * Executes an authenticated POST request.
     * @param {string} endpoint - The target endpoint.
     * @param {Object} [data] - JSON payload object.
     * @returns {Promise<any>}
     */
    post(endpoint, data = {}) {
      return executeRequest(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    /**
     * Executes an authenticated PUT request.
     * @param {string} endpoint - The target endpoint.
     * @param {Object} [data] - JSON payload object.
     * @returns {Promise<any>}
     */
    put(endpoint, data = {}) {
      return executeRequest(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
      });
    },

    /**
     * Executes an authenticated DELETE request.
     * @param {string} endpoint - The target endpoint.
     * @returns {Promise<any>}
     */
    delete(endpoint) {
      return executeRequest(endpoint, { method: 'DELETE' });
    },

    /**
     * Mutator to switch tenant context dynamically.
     * @param {string} tenantId - e.g. 'fishtail-air'
     */
    setTenant(tenantId) {
      sessionStorage.setItem('aviasafe_tenant_id', tenantId);
    },

    /**
     * Accessor for active tenant ID.
     * @returns {string}
     */
    getTenant() {
      return getActiveTenantId();
    }
  };
})();

// Attach globally for dynamic view access
window.AviaSDCPSApi = AviaSDCPSApi;