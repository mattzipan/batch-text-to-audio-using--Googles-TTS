"""WordTape import parsing (task A3): .txt word lists and 2-column .csv files.

Encoding note: the caller decodes uploaded bytes as ``utf-8-sig`` (which strips
a UTF-8 BOM), so both functions accept plain ``str``. A leading ``\\ufeff`` is
still stripped defensively in case a BOM-prefixed string is passed directly.
"""

from __future__ import annotations

import csv
import io

#: Candidate delimiters for the explicit fallback, in the mandated order.
_FALLBACK_DELIMITERS = (";", ",", "\t")

#: How much of the input the csv.Sniffer gets to look at.
_SNIFFER_SAMPLE_SIZE = 8192


def parse_txt(content: str) -> list[str]:
    """Parse a .txt word list: one term per line.

    Lines are stripped; empty/blank lines are skipped. Returns the terms in
    file order. Empty or blank-only input yields ``[]``.
    """
    if not isinstance(content, str):
        raise ValueError(
            f"parse_txt expects str content, got {type(content).__name__}."
        )
    text = content.removeprefix("\ufeff")
    return [line for line in (raw.strip() for raw in text.splitlines()) if line]


def parse_csv(content: str, has_header: bool) -> list[tuple[str, str]]:
    """Parse a 2-column CSV into ``(source, translation)`` pairs.

    The delimiter is detected with ``csv.Sniffer`` over the first 8 KB
    (``delimiters=";,\\t"``). If sniffing fails -- or the sniffed delimiter
    does not split any row into 2 columns (the Sniffer is unreliable on short
    files) -- each of ``;``, ``,``, ``\\t`` is retried explicitly, in that
    order. Every non-empty row must then have exactly 2 columns, otherwise a
    ``ValueError`` naming the offending 1-based line number is raised. Empty
    rows are skipped; when ``has_header`` is true the first non-empty row is
    dropped before validation. Surrounding whitespace is stripped from fields.
    """
    if not isinstance(content, str):
        raise ValueError(
            f"parse_csv expects str content, got {type(content).__name__}."
        )
    text = content.removeprefix("\ufeff")
    if not text.strip():
        raise ValueError("parse_csv got empty content: no rows to parse.")

    rows: list[tuple[int, list[str]]] | None = None
    try:
        dialect = csv.Sniffer().sniff(
            text[:_SNIFFER_SAMPLE_SIZE], delimiters=";,\t"
        )
    except Exception:
        dialect = None
    if dialect is not None:
        sniffed = _read_rows(text, dialect.delimiter)
        if sniffed and any(len(fields) == 2 for _, fields in sniffed):
            rows = sniffed
        # Else: sniffer misfire on a short file -- fall through to retries.
    if rows is None:
        rows = _read_with_fallback(text)

    data = rows[1:] if has_header else rows
    pairs: list[tuple[str, str]] = []
    for lineno, fields in data:
        if len(fields) != 2:
            raise ValueError(
                f"CSV line {lineno}: expected 2 columns, "
                f"found {len(fields)}."
            )
        pairs.append((fields[0].strip(), fields[1].strip()))
    return pairs


def _read_rows(text: str, delimiter: str) -> list[tuple[int, list[str]]]:
    """Read non-empty rows as ``(1-based line number, fields)`` pairs."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[tuple[int, list[str]]] = []
    try:
        for record in reader:
            lineno = reader.line_num
            if not record or all(cell.strip() == "" for cell in record):
                continue
            rows.append((lineno, list(record)))
    except csv.Error as exc:
        raise ValueError(f"CSV parse error: {exc}.") from exc
    return rows


def _read_with_fallback(text: str) -> list[tuple[int, list[str]]]:
    """Parse with each of ``;``, ``,``, ``\\t`` in order; return first clean fit.

    A candidate fits when every non-empty row has exactly 2 columns. A
    candidate that splits at least one row into 2 columns (or any row into
    more than 2) but leaves other rows deviating means the file is genuinely
    malformed, so a ``ValueError`` naming the first bad line is raised instead
    of trying further delimiters. A candidate that splits nothing (all rows
    single-column) is skipped as the wrong delimiter.
    """
    for delimiter in _FALLBACK_DELIMITERS:
        rows = _read_rows(text, delimiter)
        if not rows:
            continue
        counts = {len(fields) for _, fields in rows}
        if counts == {2}:
            return rows
        if 2 in counts or (counts - {1}):
            bad_lineno, bad_fields = next(
                (lineno, fields)
                for lineno, fields in rows
                if len(fields) != 2
            )
            raise ValueError(
                f"CSV line {bad_lineno}: expected 2 columns, "
                f"found {len(bad_fields)}."
            )
        # All rows single-column: delimiter absent from the file; try next.
    raise ValueError(
        "CSV: could not detect a delimiter -- no row has 2 columns. "
        "Expected a 2-column file separated by ';', ',' or tab."
    )
