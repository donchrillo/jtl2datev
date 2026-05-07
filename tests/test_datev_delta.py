"""Tests for core/datev_delta.py."""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from jtl2datev.cli import main
from jtl2datev.core.datev_delta import (
    _match_key,
    compute_delta,
    load_baseline,
    read_extf_csv,
    write_delta_extf,
)

# ── EXTF fixture helpers ───────────────────────────────────────────────────────

_EXTF_HEADER = (
    "EXTF;700;21;Buchungsstapel;12;20260415120000000;;jtl2datev;jtl2datev;;"
    "12345;67890;20260101;4;20260401;20260430;Belege 2026/04;jtl2datev;1;0;0;EUR"
    + ";" * (124 - 22)
)

_COL_HEADER = (
    "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ Umsatz;Kurs;"
    "Basis-Umsatz;WKZ Basis-Umsatz;Konto;Gegenkonto (ohne BU-Schlüssel);"
    "BU-Schlüssel;Belegdatum;Belegfeld 1;Belegfeld 2;Skonto;Buchungstext"
    + ";" * (124 - 14)
)

_FIELDNAMES = _COL_HEADER.split(";")


def _make_extf_row(belegnr: str, konto: str = "8400", gross: str = "119,00") -> dict[str, str]:
    row: dict[str, str] = {col: "" for col in _FIELDNAMES}
    row["Umsatz (ohne Soll/Haben-Kz)"] = gross
    row["Soll/Haben-Kennzeichen"] = "S"
    row["Konto"] = "10001"
    row["Gegenkonto (ohne BU-Schlüssel)"] = konto
    row["Belegdatum"] = "1504"
    row["Buchungstext"] = f"{belegnr} Müller Hans"
    return row


def _write_extf(path: Path, rows: list[dict[str, str]]) -> None:
    """Write minimal EXTF test file (cp1252, CRLF)."""
    fieldnames = _FIELDNAMES
    with path.open("w", encoding="cp1252", newline="") as fh:
        fh.write(_EXTF_HEADER + "\r\n")
        fh.write(_COL_HEADER + "\r\n")
        import csv
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        for row in rows:
            writer.writerow([row.get(col, "") for col in fieldnames])


# ── _match_key ─────────────────────────────────────────────────────────────────

class TestMatchKey:
    def test_extracts_first_token(self) -> None:
        assert _match_key({"Buchungstext": "202630260482 Müller Elias"}) == "202630260482"

    def test_single_token_no_space(self) -> None:
        assert _match_key({"Buchungstext": "R-DE-249030238-2026-322"}) == "R-DE-249030238-2026-322"

    def test_empty_buchungstext(self) -> None:
        assert _match_key({"Buchungstext": ""}) == ""

    def test_missing_buchungstext_key(self) -> None:
        assert _match_key({}) == ""

    def test_strips_trailing_whitespace_on_key(self) -> None:
        assert _match_key({"Buchungstext": "ABC-123 rest"}) == "ABC-123"


# ── read_extf_csv ─────────────────────────────────────────────────────────────

class TestReadExtfCsv:
    def test_returns_three_parts(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001")]
        p = tmp_path / "export.csv"
        _write_extf(p, rows)

        extf_hdr, col_hdr, data_rows = read_extf_csv(p)

        assert extf_hdr.startswith("EXTF;")
        assert "Buchungstext" in col_hdr
        assert len(data_rows) == 1

    def test_data_rows_keyed_by_fieldnames(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001", gross="200,00")]
        p = tmp_path / "export.csv"
        _write_extf(p, rows)

        _, _, data_rows = read_extf_csv(p)

        assert data_rows[0]["Buchungstext"] == "INV-001 Müller Hans"
        assert data_rows[0]["Umsatz (ohne Soll/Haben-Kz)"] == "200,00"

    def test_raises_on_too_short_file(self, tmp_path: Path) -> None:
        p = tmp_path / "short.csv"
        p.write_bytes("EXTF;only-one-line".encode("cp1252"))

        with pytest.raises(ValueError, match="too short"):
            read_extf_csv(p)


# ── compute_delta ──────────────────────────────────────────────────────────────

class TestComputeDelta:
    def test_new_document_included(self) -> None:
        baseline = [_make_extf_row("INV-001")]
        current = [_make_extf_row("INV-001"), _make_extf_row("INV-002")]

        delta, new_keys, changed_keys = compute_delta(
            current_rows=current, baseline_rows=baseline
        )

        assert new_keys == ["INV-002"]
        assert changed_keys == []
        assert len(delta) == 1
        assert _match_key(delta[0]) == "INV-002"

    def test_unchanged_document_excluded(self) -> None:
        row = _make_extf_row("INV-001")
        delta, new_keys, changed_keys = compute_delta(
            current_rows=[row], baseline_rows=[row]
        )
        assert delta == []
        assert new_keys == []
        assert changed_keys == []

    def test_changed_document_included(self) -> None:
        baseline = [_make_extf_row("INV-001", gross="100,00")]
        current = [_make_extf_row("INV-001", gross="99,00")]

        delta, new_keys, changed_keys = compute_delta(
            current_rows=current, baseline_rows=baseline
        )

        assert changed_keys == ["INV-001"]
        assert new_keys == []
        assert len(delta) == 1

    def test_two_new_one_changed(self) -> None:
        """Baseline has 2 docs, current adds 1 new and changes 1 → delta has 2 rows."""
        baseline = [_make_extf_row("INV-001"), _make_extf_row("INV-002")]
        current = [
            _make_extf_row("INV-001", gross="50,00"),  # changed
            _make_extf_row("INV-002"),                  # unchanged
            _make_extf_row("INV-003"),                  # new
        ]

        delta, new_keys, changed_keys = compute_delta(
            current_rows=current, baseline_rows=baseline
        )

        assert set(new_keys) == {"INV-003"}
        assert set(changed_keys) == {"INV-001"}
        assert len(delta) == 2

    def test_empty_baseline_all_new(self) -> None:
        current = [_make_extf_row("A"), _make_extf_row("B")]
        delta, new_keys, _ = compute_delta(current_rows=current, baseline_rows=[])
        assert set(new_keys) == {"A", "B"}
        assert len(delta) == 2

    def test_multi_row_document_change_detected(self) -> None:
        """A document with 2 DATEV rows (two account groups) is detected as changed."""
        baseline = [
            _make_extf_row("INV-001", konto="8400"),
            _make_extf_row("INV-001", konto="8300"),
        ]
        current = [_make_extf_row("INV-001", konto="8400")]  # one row removed

        delta, _, changed_keys = compute_delta(
            current_rows=current, baseline_rows=baseline
        )

        assert "INV-001" in changed_keys


# ── write_delta_extf ───────────────────────────────────────────────────────────

class TestWriteDeltaExtf:
    def test_output_has_two_header_rows(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001")]
        out = tmp_path / "delta.csv"

        write_delta_extf(rows, out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        lines = out.read_bytes().decode("cp1252").splitlines()
        assert lines[0].startswith("EXTF;")
        assert "Buchungstext" in lines[1]

    def test_data_rows_written_correctly(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001"), _make_extf_row("INV-002")]
        out = tmp_path / "delta.csv"

        write_delta_extf(rows, out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        _, _, data_rows = read_extf_csv(out)
        assert len(data_rows) == 2
        assert data_rows[0]["Buchungstext"] == "INV-001 Müller Hans"
        assert data_rows[1]["Buchungstext"] == "INV-002 Müller Hans"

    def test_encoding_is_cp1252(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001")]
        out = tmp_path / "delta.csv"

        write_delta_extf(rows, out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        # File must be readable as cp1252 without errors
        content = out.read_bytes().decode("cp1252")
        assert "EXTF;" in content

    def test_empty_delta_writes_headers_only(self, tmp_path: Path) -> None:
        out = tmp_path / "empty_delta.csv"

        write_delta_extf([], out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        lines = [l for l in out.read_bytes().decode("cp1252").splitlines() if l.strip()]
        assert len(lines) == 2  # EXTF header + column header only

    def test_crlf_line_endings(self, tmp_path: Path) -> None:
        rows = [_make_extf_row("INV-001")]
        out = tmp_path / "delta.csv"

        write_delta_extf(rows, out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        raw = out.read_bytes()
        assert b"\r\n" in raw


# ── load_baseline ──────────────────────────────────────────────────────────────

class TestLoadBaseline:
    def test_returns_tuple_of_three(self, tmp_path: Path) -> None:
        p = tmp_path / "baseline.csv"
        _write_extf(p, [_make_extf_row("INV-001")])

        extf_hdr, col_hdr, rows = load_baseline(p)

        assert extf_hdr.startswith("EXTF;")
        assert isinstance(col_hdr, str)
        assert len(rows) == 1


# ── Integration: full roundtrip ────────────────────────────────────────────────

class TestIntegration:
    def test_delta_roundtrip(self, tmp_path: Path) -> None:
        """Write baseline → add 1 new doc → compute delta → write delta EXTF → re-read."""
        baseline_file = tmp_path / "baseline.csv"
        _write_extf(baseline_file, [_make_extf_row("INV-001")])

        _, _, baseline_rows = load_baseline(baseline_file)

        current_rows = [_make_extf_row("INV-001"), _make_extf_row("INV-002")]
        delta_rows, new_keys, _ = compute_delta(
            current_rows=current_rows, baseline_rows=baseline_rows
        )
        assert new_keys == ["INV-002"]

        out = tmp_path / "delta.csv"
        write_delta_extf(delta_rows, out_path=out,
                         extf_header_line=_EXTF_HEADER,
                         column_header_line=_COL_HEADER)

        _, _, result = read_extf_csv(out)
        assert len(result) == 1
        assert _match_key(result[0]) == "INV-002"


# ── CLI smoke tests ────────────────────────────────────────────────────────────

class TestExportDeltaCli:
    def test_help_renders(self) -> None:
        result = CliRunner().invoke(main, ["export-delta", "--help"])
        assert result.exit_code == 0
        assert "--month" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--baseline" in result.output

    def test_no_date_arg_fails(self) -> None:
        result = CliRunner().invoke(main, ["export-delta"])
        assert result.exit_code != 0

    def test_both_month_and_from_to_fails(self) -> None:
        result = CliRunner().invoke(
            main,
            ["export-delta", "--month", "2026-04",
             "--from", "2026-04-01", "--to", "2026-04-30"],
        )
        assert result.exit_code != 0

    def test_from_without_to_fails(self) -> None:
        result = CliRunner().invoke(main, ["export-delta", "--from", "2026-04-01"])
        assert result.exit_code != 0

    def test_from_to_without_out_fails(self) -> None:
        result = CliRunner().invoke(
            main,
            ["export-delta", "--from", "2026-04-01", "--to", "2026-04-30"],
        )
        assert result.exit_code != 0
        assert "--out" in result.output or "Pflicht" in result.output

    def test_from_to_without_baseline_fails(self, tmp_path: Path) -> None:
        out = tmp_path / "delta.csv"
        result = CliRunner().invoke(
            main,
            ["export-delta", "--from", "2026-04-01", "--to", "2026-04-30",
             "--out", str(out)],
        )
        assert result.exit_code != 0
        assert "--baseline" in result.output or "Pflicht" in result.output
