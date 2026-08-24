from __future__ import annotations

import hashlib
import json
import logging
import os

from app.services.canonical_shadow import ShadowReadReport


logger = logging.getLogger("compatibility_reads")
VALID_READ_SOURCES = {"canonical", "shadow", "legacy"}
_warned_invalid_read_source = False


def library_read_source() -> str:
    global _warned_invalid_read_source
    value = os.getenv("LIBRARY_READ_SOURCE", "canonical").strip().casefold()
    if value in VALID_READ_SOURCES:
        return value
    if not _warned_invalid_read_source:
        logger.warning("Invalid LIBRARY_READ_SOURCE; falling back to legacy")
        _warned_invalid_read_source = True
    return "legacy"


def log_shadow_report(report: ShadowReadReport) -> None:
    differences = [
        {
            "record_hash": difference.record_id,
            "field": difference.field,
            "source_layer": difference.source_layer,
            "legacy_hash": difference.legacy_hash,
            "canonical_hash": difference.canonical_hash,
            "legacy_is_null": difference.legacy_is_null,
            "canonical_is_null": difference.canonical_is_null,
        }
        for difference in report.differences[:100]
    ]
    logger.info(
        "Canonical shadow comparison scope=%s compared=%s matched=%s different=%s "
        "missing=%s emitted=%s differences=%s",
        report.scope,
        report.records_compared,
        report.records_matched,
        report.records_different,
        report.records_missing,
        len(differences),
        json.dumps(differences, ensure_ascii=True, sort_keys=True),
    )


def log_orphan_fallback(scope: str, record_id: str | None = None, count: int = 1) -> None:
    record_hash = (
        hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:16]
        if record_id
        else None
    )
    logger.warning(
        "Canonical orphan fallback scope=%s count=%s record_hash=%s",
        scope,
        count,
        record_hash,
    )
