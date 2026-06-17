"""DOORS CSV export helpers.

Single source of truth for the Turkish-localized DOORS export rows, previously
duplicated verbatim between the live-run export and the public-snapshot export.
Framework-agnostic: callers wrap the returned document in a response.
"""
import csv
import io

CSV_HEADER = ["Senaryo", "Durum", "Açıklama"]


def doors_csv_row(doors_id: str, status: str, jira_key: str, version: str) -> list[str]:
    """Map one scenario result to a DOORS CSV row: (Senaryo, Durum, Açıklama)."""
    normalized = (status or "").upper()
    if normalized == "PASSED":
        result_status = "Yapildi - Hata Yok"
        explanation = f"{version} sürümünde test otomasyon ile doğrulanmıştır."
    elif normalized in {"FAILED", "BROKEN"}:
        result_status = "Yapildi - Hata Var"
        explanation = jira_key or ""
    else:
        result_status = "Yapilmadi"
        explanation = "Test kapsamına alınmadığı için yapılmadı"
    return [doors_id or "", result_status, explanation]


def doors_csv_document(rows: list[list[str]]) -> str:
    """Render rows into a UTF-8 BOM-prefixed CSV document (Excel-friendly)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(row)
    return "﻿" + output.getvalue()
