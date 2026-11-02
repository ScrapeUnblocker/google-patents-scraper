"""Write results as JSON, JSON Lines, CSV or a terminal table."""

from __future__ import annotations

import csv
import io
import json
import sys
import unicodedata
from collections.abc import Sequence
from typing import Any, TextIO

FORMATS = ("json", "jsonl", "csv", "table")


def as_dict(item: Any) -> dict[str, Any]:
    return item.to_dict() if hasattr(item, "to_dict") else dict(item)


def as_rows(item: Any) -> list[dict[str, Any]]:
    """The flat CSV form of one record (a landscape becomes one row per entry)."""
    if hasattr(item, "csv_rows"):
        return item.csv_rows()
    return [item.to_row() if hasattr(item, "to_row") else as_dict(item)]


def _items(items: Any) -> list[Any]:
    return list(items) if isinstance(items, (list, tuple)) else [items]


def _cell(value: Any) -> Any:
    """A CSV-friendly value: lists of plain values joined with ``; ``, the rest as JSON."""
    if isinstance(value, (list, tuple)):
        if all(not isinstance(v, (dict, list)) for v in value):
            return "; ".join(str(v) for v in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def to_json(items: Any) -> str:
    if isinstance(items, (list, tuple)):
        data: Any = [as_dict(i) for i in items]
    else:
        data = as_dict(items)
    return json.dumps(data, ensure_ascii=False, indent=2)


def to_jsonl(items: Any) -> str:
    return "".join(json.dumps(as_dict(i), ensure_ascii=False) + "\n" for i in _items(items))


def to_csv(items: Any) -> str:
    rows = [row for item in _items(items) for row in as_rows(item)]
    if not rows:
        return ""
    columns: list[str] = []
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(row.get(k)) for k in columns})
    return buffer.getvalue()


def _width(text: str) -> int:
    """Terminal width: Chinese, Japanese and Korean characters take two columns."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _short(text: str, limit: int = 80) -> str:
    if _width(text) <= limit:
        return text
    out = ""
    for ch in text:
        if _width(out + ch) > limit - 1:
            break
        out += ch
    return out + "~"


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def to_table(items: Any) -> str:
    """A compact, human-readable table (each model brings its own layout)."""
    rows = _items(items)
    if not rows:
        return "(no results)\n"
    header = getattr(rows[0], "TABLE_HEADER", ())
    if not header:
        raise ValueError(f"no table layout for {type(rows[0]).__name__}; use json or csv")
    body: list[tuple[str, ...]] = []
    for item in rows:
        if hasattr(item, "table_rows"):
            body.extend(item.table_rows())
        else:
            body.append(item.table_row())
    table = [tuple(header)] + [tuple(_short(str(c)) for c in r) for r in body]
    widths = [max(_width(r[i]) for r in table) for i in range(len(header))]
    lines = ["  ".join(_pad(c, w) for c, w in zip(r, widths)).rstrip() for r in table]
    return "\n".join(lines) + "\n"


def render(items: Any, fmt: str = "json") -> str:
    if fmt == "json":
        return to_json(items) + "\n"
    if fmt == "jsonl":
        return to_jsonl(items)
    if fmt == "csv":
        return to_csv(items)
    if fmt == "table":
        return to_table(items)
    raise ValueError(f"unknown format {fmt!r}; choose from: {', '.join(FORMATS)}")


def write(
    items: Any,
    fmt: str = "json",
    path: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Render ``items`` and write them to ``path`` or ``stream``.

    CSV files get a UTF-8 byte order mark so Excel shows Chinese, Japanese and
    Korean assignee names correctly; every other file is plain UTF-8.
    """
    text = render(items, fmt)
    if path:
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        with open(path, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        return
    (stream or sys.stdout).write(text)


def to_csv_file(records: Sequence[Any], path: str) -> None:
    """Write records (search results, patents, citation edges, ...) to a CSV file."""
    write(list(records), "csv", path)
