// ============================================================================
// FILE: public/js/demo-prospects.js
// PURPOSE: Virtual Tenant Mirroring — prospect configuration registry
//          (Chunk 3). Maps the 20 prospect Accountable Executive accounts to
//          their master archetype dataset ('demo-fixed-wing' |
//          'demo-rotary-wing') and prospect branding used by the client-side
//          reference formatter.
//
//          Every ae@* account carries an `archetypeId` custom claim at login;
//          this registry supplies the display identity (company, executive,
//          fleet, base, IATA/ICAO codes). Neutral seeded references
//          (FW-HZ-0007-26 / RW-CAN-0003-26 …) are swapped to the prospect's
//          own two-letter code via formatReference().
//
// EXPOSED: window.DEMO_PROSPECTS.{ PROSPECT_REGISTRY, getProspectByEmail,
//          getArchetypeId, formatReference }  (+ window.PROSPECT_REGISTRY)
// ============================================================================

(function () {
    'use strict';

    var PROSPECT_REGISTRY = {

        // ── Fixed-Wing Group (demo-fixed-wing) ─────────────────────────────
        'ae@buddha-air.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Buddha Air',
            aeName: 'Mr. Birendra Basnet',
            fleetType: 'ATR 72-500',
            baseLocation: 'Tribhuvan Intl (VNKT)',
            iataCode: 'BA',
            icaoCode: 'BHA'
        },
        'ae@yetiairlines.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Yeti Airlines',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'YT',
            icaoCode: 'YET'
        },
        'ae@shreeairlines.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Shree Airlines',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'SH',
            icaoCode: 'SHA'
        },
        'ae@simrikair.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Simrik Air',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'SM',
            icaoCode: 'SIM'
        },
        'ae@sauryaairlines.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Saurya Airlines',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'SA',
            icaoCode: 'SAU'
        },
        'ae@taraair.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Tara Air',
            aeName: 'Executive Name',
            fleetType: 'Dornier 228 (STOL)',
            baseLocation: 'Kathmandu/Nepalgunj',
            iataCode: 'TA',
            icaoCode: 'TRA'
        },
        'ae@summitair.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Summit Air',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'SU',
            icaoCode: 'SUM'
        },
        'ae@kailashair.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Kailash Air',
            aeName: 'Executive Name',
            fleetType: 'Dornier 228',
            baseLocation: 'Nepalgunj (VNJG)',
            iataCode: 'KA',
            icaoCode: 'KAI'
        },
        'ae@mountainair.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Mountain Air',
            aeName: 'Executive Name',
            fleetType: 'Dornier 228',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'MT',
            icaoCode: 'MTA'
        },
        'ae@airdynasty.com': {
            archetypeId: 'demo-fixed-wing',
            companyName: 'Air Dynasty',
            aeName: 'Executive Name',
            fleetType: 'ATR 72-500',
            baseLocation: 'Kathmandu (VNKT)',
            iataCode: 'AD',
            icaoCode: 'ADY'
        },

        // ── Rotary-Wing Group (demo-rotary-wing) ───────────────────────────
        'ae@fishtailair.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Fishtail Air',
            aeName: 'Executive Name',
            fleetType: 'H125 (AS350 B3e)',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'FA',
            icaoCode: 'FIS'
        },
        'ae@manangair.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Manang Air',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'MA',
            icaoCode: 'MNA'
        },
        'ae@altitudeair.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Altitude Air',
            aeName: 'Executive Name',
            fleetType: 'H125/Bell 206',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'AL',
            icaoCode: 'ALT'
        },
        'ae@prabhuheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Prabhu Helicopter',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'PH',
            icaoCode: 'PRB'
        },
        'ae@simrikheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Simrik Helicopter',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'SH',
            icaoCode: 'SMH'
        },
        'ae@kailashheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Kailash Helicopter',
            aeName: 'Executive Name',
            fleetType: 'Bell 206',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'KH',
            icaoCode: 'KAH'
        },
        'ae@mountainheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Mountain Helicopter',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'MH',
            icaoCode: 'MTH'
        },
        'ae@fishtailheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Fishtail Helicopter',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'FH',
            icaoCode: 'FTH'
        },
        'ae@airvip.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Air VIP',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'AV',
            icaoCode: 'AVP'
        },
        'ae@eagleheli.com': {
            archetypeId: 'demo-rotary-wing',
            companyName: 'Eagle Helicopter',
            aeName: 'Executive Name',
            fleetType: 'H125',
            baseLocation: 'Kathmandu Heliport',
            iataCode: 'EH',
            icaoCode: 'EGL'
        },
    };

    // ── Helpers ────────────────────────────────────────────────────────────

    /**
     * Full prospect config for an AE email (case-insensitive), or null.
     * @param {string} email
     */
    function getProspectByEmail(email) {
        if (!email) return null;
        return PROSPECT_REGISTRY[String(email).toLowerCase()] || null;
    }

    /**
     * Archetype dataset id for an AE email:
     * 'demo-fixed-wing' | 'demo-rotary-wing' | null when unregistered.
     * @param {string} email
     */
    function getArchetypeId(email) {
        var p = getProspectByEmail(email);
        return p ? p.archetypeId : null;
    }

    /**
     * Swap the neutral master prefix ('FW-' / 'RW-') on a seeded reference
     * for the prospect's own two-letter IATA code.
     *   formatReference('FW-HZ-0007-26', 'BA') -> 'BA-HZ-0007-26'
     *   formatReference('RW-CAN-0003-26', 'FA') -> 'FA-CAN-0003-26'
     * Unprefixed references pass through untouched.
     * @param {string} neutralRef
     * @param {string} iataCode
     */
    function formatReference(neutralRef, iataCode) {
        if (!neutralRef) return neutralRef || '';
        var code = (iataCode || '').trim().toUpperCase();
        if (!code) return neutralRef;
        return String(neutralRef).replace(/^(FW|RW)-/, code + '-');
    }

    // ── Export ─────────────────────────────────────────────────────────────
    window.DEMO_PROSPECTS = {
        PROSPECT_REGISTRY: PROSPECT_REGISTRY,
        getProspectByEmail: getProspectByEmail,
        getArchetypeId: getArchetypeId,
        formatReference: formatReference,
    };
    window.PROSPECT_REGISTRY = PROSPECT_REGISTRY;
})();
