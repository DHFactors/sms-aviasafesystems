# ============================================================================
# FILE: backend/seed/prospect_registry.py
# PURPOSE: Backend mirror of public/js/demo-prospects.js PROSPECT_REGISTRY
#          (Virtual Tenant Mirroring, Chunk 3). Keyed by lowercase prospect AE
#          email -> { archetypeId, companyName }. Consumed by
#          seed.archetype_config.resolve_archetype_for_email() when stamping
#          the `archetypeId` custom claim on prospect AE accounts at login.
#
# Keep in sync with public/js/demo-prospects.js — the JS file remains the
# client-side source of truth for display branding (IATA/ICAO codes, fleet,
# base location); this mirror only carries what the claim stamping needs.
# ============================================================================

PROSPECT_REGISTRY = {
    # ── Fixed-Wing Group ───────────────────────────────────────────────────
    "ae@buddha-air.com": {"archetypeId": "demo-fixed-wing", "companyName": "Buddha Air"},
    "ae@yetiairlines.com": {"archetypeId": "demo-fixed-wing", "companyName": "Yeti Airlines"},
    "ae@shreeairlines.com": {"archetypeId": "demo-fixed-wing", "companyName": "Shree Airlines"},
    "ae@simrikair.com": {"archetypeId": "demo-fixed-wing", "companyName": "Simrik Air"},
    "ae@sauryaairlines.com": {"archetypeId": "demo-fixed-wing", "companyName": "Saurya Airlines"},
    "ae@taraair.com": {"archetypeId": "demo-fixed-wing", "companyName": "Tara Air"},
    "ae@summitair.com": {"archetypeId": "demo-fixed-wing", "companyName": "Summit Air"},
    "ae@kailashair.com": {"archetypeId": "demo-fixed-wing", "companyName": "Kailash Air"},
    "ae@mountainair.com": {"archetypeId": "demo-fixed-wing", "companyName": "Mountain Air"},
    "ae@airdynasty.com": {"archetypeId": "demo-fixed-wing", "companyName": "Air Dynasty"},

    # ── Rotary-Wing Group ──────────────────────────────────────────────────
    "ae@fishtailair.com": {"archetypeId": "demo-rotary-wing", "companyName": "Fishtail Air"},
    "ae@manangair.com": {"archetypeId": "demo-rotary-wing", "companyName": "Manang Air"},
    "ae@altitudeair.com": {"archetypeId": "demo-rotary-wing", "companyName": "Altitude Air"},
    "ae@prabhuheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Prabhu Helicopter"},
    "ae@simrikheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Simrik Helicopter"},
    "ae@kailashheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Kailash Helicopter"},
    "ae@mountainheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Mountain Helicopter"},
    "ae@fishtailheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Fishtail Helicopter"},
    "ae@airvip.com": {"archetypeId": "demo-rotary-wing", "companyName": "Air VIP"},
    "ae@eagleheli.com": {"archetypeId": "demo-rotary-wing", "companyName": "Eagle Helicopter"},
}
