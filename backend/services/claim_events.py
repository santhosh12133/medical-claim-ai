"""Single place to append to a claim's activity timeline."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from models import ClaimEvent


def record_claim_event(
    db: Session,
    claim_id: int,
    event_type: str,
    message: str,
    actor_user_id: int | None = None,
    status_before: str | None = None,
    status_after: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        ClaimEvent(
            claim_id=claim_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            status_before=status_before,
            status_after=status_after,
            message=message,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
        )
    )
