/* ============================================================================
   FILE: preferences.js
   PATH: public/js/views/preferences.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS System Preferences view controller — manages tenant
            configurations, risk matrix calibrations, alert triggers, and connects
            to /api/v1/admin/preferences endpoints.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSPreferences = (function () {
  'use strict';

  /**
   * Fetches saved tenant preferences from backend.
   */
  async function loadPreferences() {
    try {
      const prefs = await window.AviaSDCPSApi.get('/admin/preferences');

      if (prefs.org_name) {
        document.getElementById('prefOrgName').value = prefs.org_name;
      }
      if (prefs.aoc_number) {
        document.getElementById('prefAocNumber').value = prefs.aoc_number;
      }
      if (prefs.matrix_scheme) {
        document.getElementById('prefMatrixScheme').value = prefs.matrix_scheme;
      }
    } catch (err) {
      console.warn('[AviaSDCPSPreferences] Could not load backend preferences, using active defaults:', err);
    }
  }

  /**
   * Persists updated configuration payload.
   */
  async function savePreferences() {
    const payload = {
      org_name: document.getElementById('prefOrgName')?.value,
      aoc_number: document.getElementById('prefAocNumber')?.value,
      primary_regulator: document.getElementById('prefPrimaryRegulator')?.value,
      matrix_scheme: document.getElementById('prefMatrixScheme')?.value,
      intolerable_action: document.getElementById('prefIntolerableAction')?.value,
      notifications: {
        mor_immediate: document.getElementById('prefAlertMorImmediate')?.checked ?? true,
        spi_breach: document.getElementById('prefAlertSpiBreach')?.checked ?? true,
        overdue_cap: document.getElementById('prefAlertOverdueCap')?.checked ?? true
      }
    };

    try {
      await window.AviaSDCPSApi.put('/admin/preferences', payload);
      alert('System preferences saved successfully.');
    } catch (err) {
      console.error('[AviaSDCPSPreferences] Save failed:', err);
      alert(`Preferences save error: ${err.message}`);
    }
  }

  /**
   * Switches visible setting tabs.
   */
  function handleTabSwitch(tabName) {
    document.querySelectorAll('#preferencesViewContainer .pref-pane').forEach(p => {
      p.style.display = 'none';
      p.classList.remove('active');
    });

    const targetPaneId = {
      'organization': 'panePrefOrganization',
      'risk-matrix': 'panePrefRiskMatrix',
      'notifications': 'panePrefNotifications',
      'security': 'panePrefSecurity'
    }[tabName];

    const target = document.getElementById(targetPaneId);
    if (target) {
      target.style.display = 'block';
      target.classList.add('active');
    }
  }

  /**
   * Attaches event listeners for preferences UI.
   */
  function bindEvents() {
    const toggleBtns = document.querySelectorAll('#preferencesViewContainer .toggle-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        const tab = e.currentTarget.getAttribute('data-pref-tab');
        handleTabSwitch(tab);
      });
    });

    document.getElementById('btnSavePreferences')?.addEventListener('click', savePreferences);

    document.getElementById('btnToggleApiKey')?.addEventListener('click', (e) => {
      const input = document.getElementById('prefApiKey');
      if (!input) return;
      if (input.type === 'password') {
        input.type = 'text';
        e.currentTarget.textContent = 'Hide';
      } else {
        input.type = 'password';
        e.currentTarget.textContent = 'Reveal';
      }
    });
  }

  return {
    init() {
      bindEvents();
      loadPreferences();
    }
  };
})();

window.AviaSDCPSPreferences = AviaSDCPSPreferences;