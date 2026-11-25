"""Champion model loader — bridges the ML registry into the live trade path."""

from __future__ import annotations

import logging

from sqlalchemy import select

from trading.ml.train import LogitModel, deserialize

log = logging.getLogger(__name__)


def champion_timeframe(session) -> str | None:
    """Parse the champion's timeframe from ModelVersion.name (gate-<SYM>-<TF>)."""
    from trading.models import ModelVersion

    row = (
        session.execute(
            select(ModelVersion.name)
            .where(ModelVersion.is_champion.is_(True), ModelVersion.weights_blob.is_not(None))
            .order_by(ModelVersion.trained_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if not row:
        return None
    try:
        return str(row).rsplit("-", 1)[-1] or None
    except Exception:
        return None


def load_champion(session) -> LogitModel | None:
    """Return the deserialized champion model, or None when unavailable.

    Champion rows without a weights_blob (trained before persistence was
    added) are skipped — they cannot be reconstructed without retraining.
    """
    from trading.models import ModelVersion

    row = (
        session.execute(
            select(ModelVersion)
            .where(ModelVersion.is_champion.is_(True), ModelVersion.weights_blob.is_not(None))
            .order_by(ModelVersion.trained_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    try:
        return deserialize(row.weights_blob)
    except (ValueError, KeyError, TypeError):
        log.exception(
            "champion weights_blob corrupt (model %s v%d) — gate disabled", row.name, row.version
        )
        return None
