"""Tests for core/archive.py and core/dutypay_delta.py."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from jtl2datev.core.archive import archive_delta, archive_export, latest_archive
from jtl2datev.core.dutypay import DUTYPAY_COLUMNS
from jtl2datev.core.dutypay_delta import (
    compute_delta,
    load_baseline,
    write_delta_csv,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_FIELDNAMES = list(DUTYPAY_COLUMNS)


def _make_row(doc_id: str, pos_nr: int = 1, gross: str = "100,00") -> dict[str, str]:
    row: dict[str, str] = {col: "" for col in _FIELDNAMES}
    row["DocumentID"] = doc_id
    row["Positions-Nr."] = str(pos_nr)
    row["MarketZoneGross"] = gross
    row["ReportingPeriod"] = "2026-FEB"
    row["DepartureDate"] = "01.02.2026"
    row["ArrivalDate"] = "01.02.2026"
    row["DocumentDate"] = "01.02.2026"
    row["PostingDateInvoice"] = "01.02.2026"
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES, delimiter=";",
                                quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ── archive.py tests ──────────────────────────────────────────────────────────

class TestArchiveExport:
    def test_file_lands_at_expected_path(self, tmp_path: Path) -> None:
        src = tmp_path / "source.csv"
        src.write_text("data", encoding="utf-8")
        now = datetime(2026, 2, 15, 10, 30, 5)

        dest = archive_export(src, archive_root=tmp_path / "arch", kind="dutypay",
                              period="2026-02", now=now)

        assert dest == tmp_path / "arch" / "dutypay" / "2026-02" / "2026-02-15_10-30-05.csv"
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "data"

    def test_directory_created_automatically(self, tmp_path: Path) -> None:
        src = tmp_path / "x.csv"
        src.write_text("y", encoding="utf-8")
        archive_export(src, archive_root=tmp_path / "new_root", kind="dutypay", period="2026-01")
        assert (tmp_path / "new_root" / "dutypay" / "2026-01").is_dir()


class TestLatestArchive:
    def test_returns_none_when_no_archive(self, tmp_path: Path) -> None:
        assert latest_archive(tmp_path, kind="dutypay", period="2026-01") is None

    def test_returns_last_file_lexicographically(self, tmp_path: Path) -> None:
        d = tmp_path / "dutypay" / "2026-02"
        d.mkdir(parents=True)
        (d / "2026-02-01_08-00-00.csv").write_text("a")
        (d / "2026-02-06_14-30-00.csv").write_text("b")

        result = latest_archive(tmp_path, kind="dutypay", period="2026-02")
        assert result is not None
        assert result.name == "2026-02-06_14-30-00.csv"

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "dutypay" / "2026-03"
        d.mkdir(parents=True)
        assert latest_archive(tmp_path, kind="dutypay", period="2026-03") is None


class TestArchiveDelta:
    def test_delta_lands_in_deltas_subdir(self, tmp_path: Path) -> None:
        src = tmp_path / "delta.csv"
        src.write_text("delta", encoding="utf-8")
        now = datetime(2026, 3, 10, 9, 0, 0)

        dest = archive_delta(src, archive_root=tmp_path / "arch", kind="dutypay",
                             period="2026-02", now=now)

        assert dest == tmp_path / "arch" / "dutypay" / "2026-02" / "deltas" / "2026-03-10_09-00-00.csv"
        assert dest.exists()


# ── dutypay_delta.py tests ────────────────────────────────────────────────────

class TestComputeDelta:
    def test_new_document_is_included(self) -> None:
        baseline = [_make_row("DOC-1")]
        current = [_make_row("DOC-1"), _make_row("DOC-2")]

        delta, new_ids, changed_ids = compute_delta(
            current_rows=current, baseline_rows=baseline
        )
        assert new_ids == ["DOC-2"]
        assert changed_ids == []
        assert len(delta) == 1
        assert delta[0]["DocumentID"] == "DOC-2"

    def test_unchanged_document_excluded(self) -> None:
        baseline = [_make_row("DOC-1")]
        current = [_make_row("DOC-1")]

        delta, new_ids, changed_ids = compute_delta(
            current_rows=current, baseline_rows=baseline
        )
        assert delta == []
        assert new_ids == []
        assert changed_ids == []

    def test_changed_document_included(self) -> None:
        baseline = [_make_row("DOC-1", gross="100,00")]
        current = [_make_row("DOC-1", gross="99,00")]

        delta, new_ids, changed_ids = compute_delta(
            current_rows=current, baseline_rows=baseline
        )
        assert changed_ids == ["DOC-1"]
        assert new_ids == []
        assert len(delta) == 1

    def test_multi_position_document_change_detected(self) -> None:
        baseline = [_make_row("DOC-3", pos_nr=1), _make_row("DOC-3", pos_nr=2)]
        # Same document but different number of positions
        current = [_make_row("DOC-3", pos_nr=1)]

        delta, new_ids, changed_ids = compute_delta(
            current_rows=current, baseline_rows=baseline
        )
        assert changed_ids == ["DOC-3"]

    def test_empty_baseline_all_new(self) -> None:
        current = [_make_row("A"), _make_row("B")]
        delta, new_ids, changed_ids = compute_delta(
            current_rows=current, baseline_rows=[]
        )
        assert set(new_ids) == {"A", "B"}
        assert len(delta) == 2


class TestWriteDeltaCsv:
    def test_positions_renumbered_from_one(self, tmp_path: Path) -> None:
        rows = [_make_row("D1", pos_nr=5), _make_row("D2", pos_nr=10)]
        out = tmp_path / "delta.csv"
        write_delta_csv(rows, out_path=out, fieldnames=_FIELDNAMES)

        with out.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.DictReader(fh, delimiter=";"))
        assert reader[0]["Positions-Nr."] == "1"
        assert reader[1]["Positions-Nr."] == "2"

    def test_shift_to_period_overwrites_date_fields(self, tmp_path: Path) -> None:
        rows = [_make_row("D1")]
        out = tmp_path / "delta_shifted.csv"
        write_delta_csv(rows, out_path=out, fieldnames=_FIELDNAMES, shift_to_period=(2026, 3))

        with out.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.DictReader(fh, delimiter=";"))
        row = reader[0]
        assert row["ReportingPeriod"] == "2026-MAR"
        assert row["DepartureDate"] == "01.03.2026"
        assert row["ArrivalDate"] == "01.03.2026"
        assert row["DocumentDate"] == "01.03.2026"

    def test_shift_to_period_also_shifts_posting_date(self, tmp_path: Path) -> None:
        rows = [_make_row("D1")]
        out = tmp_path / "delta_shifted2.csv"
        write_delta_csv(rows, out_path=out, fieldnames=_FIELDNAMES, shift_to_period=(2026, 3))

        with out.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.DictReader(fh, delimiter=";"))
        assert reader[0]["PostingDateInvoice"] == "01.03.2026"

    def test_empty_delta_writes_header_only(self, tmp_path: Path) -> None:
        out = tmp_path / "empty_delta.csv"
        write_delta_csv([], out_path=out, fieldnames=_FIELDNAMES)

        with out.open(encoding="utf-8", newline="") as fh:
            content = fh.read()
        assert "DocumentID" in content
        lines = [line for line in content.splitlines() if line.strip()]
        assert len(lines) == 1  # header only


class TestLoadBaseline:
    def test_load_returns_list_of_dicts(self, tmp_path: Path) -> None:
        p = tmp_path / "baseline.csv"
        rows = [_make_row("X1"), _make_row("X2")]
        _write_csv(p, rows)

        loaded = load_baseline(p)
        assert len(loaded) == 2
        assert loaded[0]["DocumentID"] == "X1"


class TestIntegration:
    def test_delta_roundtrip(self, tmp_path: Path) -> None:
        """Full roundtrip: write baseline → add row → compute delta → write delta CSV."""
        baseline_file = tmp_path / "baseline.csv"
        baseline_rows = [_make_row("DOC-A")]
        _write_csv(baseline_file, baseline_rows)

        current_rows = [_make_row("DOC-A"), _make_row("DOC-B")]
        delta_rows, new_ids, _ = compute_delta(
            current_rows=current_rows,
            baseline_rows=load_baseline(baseline_file),
        )
        assert new_ids == ["DOC-B"]

        out = tmp_path / "delta.csv"
        write_delta_csv(delta_rows, out_path=out, fieldnames=_FIELDNAMES)
        assert out.exists()
        with out.open(encoding="utf-8", newline="") as fh:
            result = list(csv.DictReader(fh, delimiter=";"))
        assert len(result) == 1
        assert result[0]["DocumentID"] == "DOC-B"
