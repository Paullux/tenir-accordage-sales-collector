from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m/%d/%y",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%B %d, %Y",
)


class ReportFormatError(ValueError):
    """Raised when a report file cannot be parsed or is missing required columns."""


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV/TSV/XLSX report into a list of dicts keyed by the file's
    own header row. Header matching against expected fields is left to each
    collector via `resolve_column`, so this stays format-agnostic.
    """
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv", ".txt"):
        return _read_delimited(path)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    raise ReportFormatError(f"Unsupported report format: {path.suffix} ({path.name})")


def _read_delimited(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    reader = csv.DictReader(raw.splitlines(), dialect=dialect)
    return [dict(row) for row in reader]


def _read_xlsx(path: Path) -> list[dict[str, str]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    except StopIteration:
        return []
    rows = []
    for values in rows_iter:
        if values is None or all(v is None for v in values):
            continue
        row = {
            header[i]: ("" if v is None else v)
            for i, v in enumerate(values)
            if i < len(header) and header[i]
        }
        rows.append(row)
    return rows


def resolve_column(row: dict[str, Any], *aliases: str) -> str | None:
    """Case/whitespace-insensitive lookup of the first alias present in `row`."""
    normalized = {_norm(k): k for k in row.keys()}
    for alias in aliases:
        key = normalized.get(_norm(alias))
        if key is not None:
            return key
    return None


def _norm(value: str) -> str:
    return "".join(value.split()).lower()


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace(" ", "").replace(" ", "")
    for symbol in ("EUR", "USD", "GBP", "CAD", "AUD", "JPY", "€", "$", "£"):
        text = text.replace(symbol, "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError as exc:
        raise ReportFormatError(f"Could not parse numeric value: {value!r}") from exc
    return -result if negative else result


def parse_int(value: Any) -> int:
    return int(round(parse_number(value)))


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ReportFormatError("Empty date value")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ReportFormatError(f"Could not parse date value: {value!r}")
