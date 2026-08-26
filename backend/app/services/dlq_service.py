from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from app.firebase import get_db

COLLECTION_PATH = "dead_letter_queue"
SLACK_WEBHOOK_KEY = "DLQ_SLACK_WEBHOOK_URL"
TEAMS_WEBHOOK_KEY = "DLQ_TEAMS_WEBHOOK_URL"


def _collection():
    return get_db().collection(COLLECTION_PATH)


class DlqService:
    """Persist dead-letter records to Firestore and dispatch webhook alerts."""

    def __init__(self, slack_webhook: Optional[str] = None, teams_webhook: Optional[str] = None):
        self.slack_webhook = slack_webhook
        self.teams_webhook = teams_webhook

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def quarantine(
        self,
        original_operation: str,
        payload: Dict[str, Any],
        error_message: str,
        error_traceback: Optional[str] = None,
        max_attempts: int = 3,
    ) -> str:
        dlq_id = f"dlq-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        record = {
            "dlq_id": dlq_id,
            "original_operation": original_operation,
            "payload": payload,
            "error_message": error_message,
            "error_traceback": error_traceback,
            "attempt_count": 0,
            "max_attempts": max_attempts,
            "resolution_status": "unresolved",
            "resolution_note": None,
            "resolved_by": None,
            "resolved_at": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            _collection().document(dlq_id).set(record)
            logger.warning(f"Dead letter quarantined: {dlq_id} op={original_operation}")
        except Exception as e:
            logger.error(f"Failed to write DLQ record {dlq_id}: {e}")
            raise

        self._alert_webhooks(dlq_id, original_operation, error_message)
        return dlq_id

    def mark_investigating(self, dlq_id: str, user: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        _collection().document(dlq_id).update({
            "resolution_status": "investigating",
            "updated_at": now,
        })

    def mark_replayed(self, dlq_id: str, user: Optional[str] = None, note: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        _collection().document(dlq_id).update({
            "resolution_status": "replayed",
            "resolved_by": user,
            "resolved_at": now,
            "resolution_note": note,
            "updated_at": now,
        })
        logger.info(f"DLQ record {dlq_id} marked as replayed by {user}")

    def mark_discarded(self, dlq_id: str, user: Optional[str] = None, note: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        _collection().document(dlq_id).update({
            "resolution_status": "discarded",
            "resolved_by": user,
            "resolved_at": now,
            "resolution_note": note,
            "updated_at": now,
        })
        logger.info(f"DLQ record {dlq_id} marked as discarded by {user}")

    def get_record(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = _collection().document(dlq_id).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            data["id"] = doc.id
            return data
        except Exception as e:
            logger.error(f"Failed to get DLQ record {dlq_id}: {e}")
            return None

    def list_unresolved(self, limit: int = 50) -> list:
        try:
            docs = (
                _collection()
                .where("resolution_status", "==", "unresolved")
                .order_by("created_at", direction="DESCENDING")
                .limit(limit)
                .get()
            )
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Failed to list unresolved DLQ records: {e}")
            return []

    # ------------------------------------------------------------------
    # Webhook alerting
    # ------------------------------------------------------------------

    def _alert_webhooks(self, dlq_id: str, operation: str, error: str) -> None:
        if self.slack_webhook:
            self._send_slack(dlq_id, operation, error)
        if self.teams_webhook:
            self._send_teams(dlq_id, operation, error)

    def _send_slack(self, dlq_id: str, operation: str, error: str) -> None:
        payload = {
            "text": f":rotating_light: *DLQ Alert* `{dlq_id}`\n"
                    f"Operation: `{operation}`\nError: {error[:300]}",
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self.slack_webhook, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Slack DLQ alert failed for {dlq_id}: {e}")

    def _send_teams(self, dlq_id: str, operation: str, error: str) -> None:
        payload = {
            "@type": "MessageCard",
            "summary": f"DLQ Alert: {dlq_id}",
            "sections": [{
                "activityTitle": f"Dead Letter Queue Alert — {dlq_id}",
                "facts": [
                    {"name": "Operation", "value": operation},
                    {"name": "Error", "value": error[:300]},
                ],
                "markdown": True,
            }],
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(self.teams_webhook, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Teams DLQ alert failed for {dlq_id}: {e}")
