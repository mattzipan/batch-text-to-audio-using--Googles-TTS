"""Tests for app.importer (task A3): txt parsing and csv delimiter handling."""

from __future__ import annotations

import csv

import pytest

from app.importer import parse_csv, parse_txt


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

COMMA_CSV = "Guten Morgen,Selamat pagi\nDanke,Terima kasih\nTschüss,Dadah\n"

# Danish/German Excel: semicolon-separated with a UTF-8 BOM.
SEMI_CSV_BODY = "Guten Morgen;Selamat pagi\nDanke;Terima kasih\nTschüss;Dadah\n"

TAB_CSV = "Guten Morgen\tSelamat pagi\nDanke\tTerima kasih\nTschüss\tDadah\n"

QUOTED_COMMA_CSV = '"Guten, Morgen","Selamat, pagi"\nDanke,Terima kasih\n'

HEADER_CSV = "source,translation\nGuten Morgen,Selamat pagi\nDanke,Terima kasih\n"

MALFORMED_CSV = "Guten Morgen,Selamat pagi\nDanke,Terima kasih,EXTRA\nTschüss,Dadah\n"

EXPECTED_PAIRS = [
    ("Guten Morgen", "Selamat pagi"),
    ("Danke", "Terima kasih"),
    ("Tschüss", "Dadah"),
]


# ---------------------------------------------------------------------------
# parse_txt
# ---------------------------------------------------------------------------

def test_txt_strips_and_skips_blank_lines() -> None:
    content = "  Guten Morgen  \n\n   \nDanke\n\t\nTschüss\n"
    assert parse_txt(content) == ["Guten Morgen", "Danke", "Tschüss"]


def test_txt_strips_leading_bom() -> None:
    assert parse_txt("\ufeffGuten Morgen\nDanke\n") == ["Guten Morgen", "Danke"]


def test_txt_handles_crlf_and_empty_input() -> None:
    assert parse_txt("Guten Morgen\r\nDanke\r\n") == ["Guten Morgen", "Danke"]
    assert parse_txt("") == []
    assert parse_txt("  \n \t \n") == []


def test_txt_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        parse_txt(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parse_txt(b"Guten Morgen\n")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_csv: delimiters
# ---------------------------------------------------------------------------

def test_csv_comma_no_header() -> None:
    assert parse_csv(COMMA_CSV, has_header=False) == EXPECTED_PAIRS


def test_csv_semicolon_with_bom() -> None:
    # Real caller flow: raw Excel bytes decoded as utf-8-sig (BOM removed).
    raw = b"\xef\xbb\xbf" + SEMI_CSV_BODY.encode("utf-8")
    assert parse_csv(raw.decode("utf-8-sig"), has_header=False) == EXPECTED_PAIRS
    # Defensive path: a BOM-prefixed str passed directly also parses.
    assert parse_csv("\ufeff" + SEMI_CSV_BODY, has_header=False) == EXPECTED_PAIRS


def test_csv_tab_separated() -> None:
    assert parse_csv(TAB_CSV, has_header=False) == EXPECTED_PAIRS


def test_csv_quoted_fields_containing_delimiter() -> None:
    assert parse_csv(QUOTED_COMMA_CSV, has_header=False) == [
        ("Guten, Morgen", "Selamat, pagi"),
        ("Danke", "Terima kasih"),
    ]


def test_csv_quoted_semicolons_in_semicolon_file() -> None:
    content = '"Guten; Morgen";"Selamat; pagi"\nDanke;Terima kasih\n'
    assert parse_csv(content, has_header=False) == [
        ("Guten; Morgen", "Selamat; pagi"),
        ("Danke", "Terima kasih"),
    ]


# ---------------------------------------------------------------------------
# parse_csv: header, whitespace, blank lines
# ---------------------------------------------------------------------------

def test_csv_header_dropped_when_flag_set() -> None:
    assert parse_csv(HEADER_CSV, has_header=True) == [
        ("Guten Morgen", "Selamat pagi"),
        ("Danke", "Terima kasih"),
    ]


def test_csv_header_kept_as_data_when_flag_unset() -> None:
    rows = parse_csv(HEADER_CSV, has_header=False)
    assert rows[0] == ("source", "translation")
    assert len(rows) == 3


def test_csv_skips_blank_lines_and_strips_fields() -> None:
    content = "\n  Guten Morgen , Selamat pagi  \n\nDanke,Terima kasih\n   \n"
    assert parse_csv(content, has_header=False) == [
        ("Guten Morgen", "Selamat pagi"),
        ("Danke", "Terima kasih"),
    ]


def test_csv_header_only_returns_empty_list() -> None:
    assert parse_csv("source,translation\n", has_header=True) == []


# ---------------------------------------------------------------------------
# parse_csv: malformed input
# ---------------------------------------------------------------------------

def test_csv_three_column_row_raises_with_line_number() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_csv(MALFORMED_CSV, has_header=False)
    assert "2" in str(excinfo.value)  # offending 1-based line number


def test_csv_single_column_raises() -> None:
    with pytest.raises(ValueError):
        parse_csv("just one column\nanother line\n", has_header=False)


def test_csv_empty_content_raises() -> None:
    with pytest.raises(ValueError):
        parse_csv("", has_header=False)
    with pytest.raises(ValueError):
        parse_csv("  \n \n", has_header=True)


def test_csv_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        parse_csv(None, has_header=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parse_csv(b"a,b\n", has_header=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_csv: sniffer fallback (Sniffer forced to fail -> explicit ; , \t)
# ---------------------------------------------------------------------------

def test_csv_fallback_when_sniffer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(self, sample, delimiters=None):  # noqa: ANN001, ANN202
        raise csv.Error("nope")

    monkeypatch.setattr(csv.Sniffer, "sniff", _boom)
    assert parse_csv(COMMA_CSV, has_header=False) == EXPECTED_PAIRS
    assert parse_csv(SEMI_CSV_BODY, has_header=False) == EXPECTED_PAIRS
    assert parse_csv(TAB_CSV, has_header=False) == EXPECTED_PAIRS
    with pytest.raises(ValueError):
        parse_csv(MALFORMED_CSV, has_header=False)
