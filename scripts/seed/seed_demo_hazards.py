# ==============================================================================
# File: scripts/seed/seed_demo_hazards.py
# Description: Populates baseline operational hazards and linked HFACS 7.0
#              RCA factors into the beta database (sms-db-beta).
# ==============================================================================

import os
import sys
from datetime import datetime, timezone

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "backend")))

from app.core.config import settings
from app.firebase import initialize_firebase, get_firestore_db
from app.services.hazard_service import HazardService

async def seed_hazards():
    if settings.FIRESTORE_DATABASE_ID != "sms-db-beta":
        print(f"❌ Safety block: Script must target 'sms-db-beta', got '{settings.FIRESTORE_DATABASE_ID}'.")
        sys.exit(1)

    initialize_firebase()
    db = get_firestore_db()
    service = HazardService(db=db)

    print("🌱 Seeding demo hazards and RCA factors onto sms-db-beta...")

    # Sample Hazard 1: Fishtail Air
    h1 = {
        "title": "Unstabilized Approach during Monsoonal Windshear at Lukla",
        "description": "Tailwind component exceeded company SOP limits on final approach.",
        "source_type": "occurrence",
        "source_reference_id": "OCC-2026-0819",
        "functional_area": "flight_operations",
        "assigned_owner_email": "safety@fishtailair.com.np",
        "target_completion_date": None
    }
    user_info = {"email": "ops@fishtailair.com.np", "name": "Flight Operations"}
    h1_id = await service.create_hazard("fishtail-air", h1, user_info)
    print(f"  ✓ Created Hazard: {h1_id}")

    # Tag HFACS RCA Nanocode
    rca1 = {
        "tier": 2,
        "category": "PRECOND",
        "subcategory": "Physical Environment",
        "nanocode": "PE101",
        "definition": "Environmental Conditions Affecting Vision",
        "contributing_narrative": "Heavy rain showers reduced runway visual reference prior to decision point.",
        "order_sequence": 1
    }
    await service.add_rca_factor("fishtail-air", h1_id, rca1)
    print(f"    ✓ Linked RCA Factor: PE101")

    # Initial Assessment
    asm1 = {
        "assessment_type": "initial",
        "severity_score": 4,
        "severity_justification": "Hazardous flight conditions in high terrain.",
        "probability_score": "D",
        "probability_justification": "Occurs only during specific monsoon wind shifts."
    }
    await service.record_assessment("fishtail-air", h1_id, asm1, "safety@fishtailair.com.np")
    print(f"    ✓ Attached 4D Tolerability Assessment")

    print("✓ Hazard seed completed successfully.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(seed_hazards())