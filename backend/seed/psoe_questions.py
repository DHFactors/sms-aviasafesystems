# ============================================================================
# FILE: seed/psoe_questions.py
# PATH: backend/seed/psoe_questions.py
# PURPOSE: Seed the CAAN PSOE surveillance question bank (4 components, 21
#          questions) into the PostgreSQL ``psoe_questions`` table.
#
#          Idempotent upsert: rows that already exist for a
#          (component, question_number) key are updated only when the question
#          text changed; new questions are inserted. Safe to re-run.
#
# Invocation:
#   python -m backend.seed.psoe_questions            # from repo root (server)
#   python -m backend.seed.psoe_questions --dry-run
#   python -m backend.seed.psoe_questions            # from backend/ also works
# ============================================================================

from __future__ import annotations

import asyncio
import argparse
import os
import sys
from dataclasses import dataclass

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import select  # noqa: E402

from app.db.db_models import PsoeQuestion  # noqa: E402
from app.db.session import session_scope  # noqa: E402


@dataclass(frozen=True)
class _Question:
    component: str
    number: int
    text: str


# CAA / ICAO Annex 19 (CAAN SMS Procedure Manual Appendix 10) surveillance
# checklist. Question ordering within each component matters for rendering.
QUESTIONS: tuple[_Question, ...] = (
    # ── Component 1: Safety Management ──
    _Question("Safety Management", 1, "Has the organisation established a safety policy endorsed by the Accountable Executive?"),
    _Question("Safety Management", 2, "Are safety accountabilities clearly defined and documented for all personnel?"),
    _Question("Safety Management", 3, "Has a qualified Safety Manager been appointed with appropriate authority?"),
    _Question("Safety Management", 4, "Is there a documented and approved SMS manual?"),
    _Question("Safety Management", 5, "Are safety objectives and targets defined and communicated throughout the organisation?"),
    # ── Component 2: Risk Management ──
    _Question("Risk Management", 6, "Is there a formal hazard identification process in place?"),
    _Question("Risk Management", 7, "Are hazards assessed using a documented risk matrix?"),
    _Question("Risk Management", 8, "Is there a formal SRAM (Safety Risk Assessment & Mitigation) process?"),
    _Question("Risk Management", 9, "Are risk mitigation measures documented and tracked to closure?"),
    _Question("Risk Management", 10, "Is a risk register maintained and regularly reviewed?"),
    # ── Component 3: Safety Assurance ──
    _Question("Safety Assurance", 11, "Are Safety Performance Indicators (SPIs) defined for all key areas?"),
    _Question("Safety Assurance", 12, "Is safety performance monitored and reviewed by management?"),
    _Question("Safety Assurance", 13, "Is there a formal Management of Change (MOC) process?"),
    _Question("Safety Assurance", 14, "Are internal audits conducted regularly and findings tracked?"),
    _Question("Safety Assurance", 15, "Are corrective actions tracked to closure with verification?"),
    _Question("Safety Assurance", 16, "Is there a documented continuous improvement process?"),
    # ── Component 4: Safety Promotion ──
    _Question("Safety Promotion", 17, "Is safety training provided to all employees based on their role?"),
    _Question("Safety Promotion", 18, "Is there a documented safety communication strategy?"),
    _Question("Safety Promotion", 19, "Is safety information shared across all levels of the organisation?"),
    _Question("Safety Promotion", 20, "Is there a Just Culture policy that encourages reporting?"),
    _Question("Safety Promotion", 21, "Are employees actively encouraged to report safety concerns?"),
)


async def _plan() -> dict:
    """Return counts without writing (dry-run) or apply the upsert."""
    async with session_scope() as session:
        existing = (await session.execute(select(PsoeQuestion))).scalars().all()
        existing_map = {(q.component, q.question_number): q for q in existing}

        created: list[tuple[str, int]] = []
        updated: list[tuple[str, int]] = []
        unchanged = 0

        for q in QUESTIONS:
            row = existing_map.get((q.component, q.number))
            if row is None:
                session.add(
                    PsoeQuestion(
                        component=q.component,
                        question_number=q.number,
                        question_text=q.text,
                    )
                )
                created.append((q.component, q.number))
            elif row.question_text != q.text:
                row.question_text = q.text
                updated.append((q.component, q.number))
            else:
                unchanged += 1

        counts = {
            "total": len(QUESTIONS),
            "created": len(created),
            "updated": len(updated),
            "unchanged": unchanged,
        }
        if created or updated:
            changed = created + updated
            counts["summary"] = [
                f"{component} Q{number}" for component, number in changed
            ]
        return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the PSOE question bank (21 questions, 4 components)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the database.",
    )
    args = parser.parse_args()

    counts = asyncio.run(_plan())

    if args.dry_run:
        print("DRY RUN - no rows written.")
    print(f"PSOE questions: total={counts['total']} "
          f"created={counts['created']} updated={counts['updated']} "
          f"unchanged={counts['unchanged']}")
    if counts["created"] or counts["updated"]:
        verb = "would create/update" if args.dry_run else "created/updated"
        print(f"Changes {verb}:")
        for item in counts["summary"]:
            print(f"  {item}")


if __name__ == "__main__":
    main()