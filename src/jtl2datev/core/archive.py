"""Generic export archive helpers.

Stores timestamped copies of exported CSV files under:
  <archive_root>/<kind>/<YYYY-MM>/<YYYY-MM-DD_HH-MM-SS>.csv

Works for DutyPay, Taxually, DATEV — pass `kind` accordingly.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def archive_export(
    source: Path,
    *,
    archive_root: Path,
    kind: str,
    period: str,
    now: datetime | None = None,
) -> Path:
    """Copy *source* into the archive tree; return destination path.

    Args:
        source: The file that was just written.
        archive_root: Base directory for all archives.
        kind: Sub-directory name, e.g. ``"dutypay"`` or ``"datev"``.
        period: ``"YYYY-MM"`` string identifying the export month.
        now: Timestamp override for testing; defaults to local time.

    Returns:
        The path the file was copied to.
    """
    ts = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S-%f")
    dest_dir = archive_root / kind / period
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}.csv"
    suffix = 2
    while dest.exists():
        dest = dest_dir / f"{ts}_{suffix}.csv"
        suffix += 1
    shutil.copy2(source, dest)
    logger.info("Archived %s → %s", source, dest)
    return dest


def latest_archive(
    archive_root: Path,
    *,
    kind: str,
    period: str,
) -> Path | None:
    """Return the lexicographically last archive file for *period*, or None."""
    period_dir = archive_root / kind / period
    if not period_dir.is_dir():
        return None
    candidates = sorted(period_dir.glob("*.csv"))
    if not candidates:
        return None
    return candidates[-1]


def archive_delta(
    source: Path,
    *,
    archive_root: Path,
    kind: str,
    period: str,
    now: datetime | None = None,
) -> Path:
    """Copy *source* into the ``deltas/`` sub-directory; return destination."""
    ts = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S-%f")
    dest_dir = archive_root / kind / period / "deltas"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}.csv"
    suffix = 2
    while dest.exists():
        dest = dest_dir / f"{ts}_{suffix}.csv"
        suffix += 1
    shutil.copy2(source, dest)
    logger.info("Archived delta %s → %s", source, dest)
    return dest
