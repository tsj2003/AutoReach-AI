"""
CsvIngestService — bulk prospect ingestion from a CSV upload.

Input contract (the operator's CSV):
    Required column:  email
    Optional columns: name, full_name, first_name, last_name, company, title

The service:
    * normalizes header names (case/whitespace-insensitive)
    * validates emails (very permissive — full RFC validation is the
      adapter's job)
    * deduplicates within the upload
    * skips emails that already exist in the engagement
    * stores the original row in `prospect.raw` so we keep all data

Returns a small report so the cockpit can show "loaded 187, skipped 13."
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import IO, Iterable

from engine.services.operations import OperationsService

EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def _is_email(s: str) -> bool:
    return bool(s) and bool(EMAIL_RE.match(s.strip()))


@dataclass
class CsvIngestResult:
    total_rows: int = 0
    loaded: int = 0
    skipped_invalid_email: int = 0
    skipped_duplicates: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)


class CsvIngestService:
    def __init__(self, ops: OperationsService) -> None:
        self._ops = ops

    def ingest(self, *, engagement_id: str, file_obj: IO[str]) -> CsvIngestResult:
        """
        Stream-parse a CSV from `file_obj` and add prospects to the engagement.

        `file_obj` is a text file-like object (FastAPI gives us bytes; the
        caller decodes). We don't bind to FastAPI here so the same service
        works from the CLI.
        """
        result = CsvIngestResult()
        reader = csv.DictReader(file_obj)
        if reader.fieldnames is None:
            result.errors.append("empty CSV (no header row)")
            return result

        # Build a case-insensitive header map.
        normalized = {f.strip().lower(): f for f in reader.fieldnames if f}
        email_col = normalized.get("email")
        if email_col is None:
            result.errors.append('CSV must have an "email" column')
            return result

        name_col = (
            normalized.get("full_name")
            or normalized.get("name")
            or normalized.get("first_name")
        )
        last_name_col = normalized.get("last_name")
        company_col = normalized.get("company")
        title_col = normalized.get("title")

        seen_in_upload: set[str] = set()
        existing_emails: set[str] = {
            (p.email or "").strip().lower()
            for p in self._ops.list_prospects(engagement_id, limit=10_000)
            if p.email
        }

        for row in reader:
            result.total_rows += 1
            email_raw = (row.get(email_col) or "").strip()
            email = email_raw.lower()
            if not _is_email(email):
                result.skipped_invalid_email += 1
                continue
            if email in seen_in_upload:
                result.skipped_duplicates += 1
                continue
            seen_in_upload.add(email)
            if email in existing_emails:
                result.skipped_existing += 1
                continue

            full_name = (row.get(name_col) if name_col else None) or None
            if full_name and last_name_col:
                last = row.get(last_name_col) or ""
                if last:
                    full_name = f"{full_name} {last}".strip()
            company = (row.get(company_col) if company_col else None) or None
            title = (row.get(title_col) if title_col else None) or None

            self._ops.add_prospect(
                engagement_id=engagement_id,
                email=email,
                full_name=full_name,
                company=company,
                title=title,
                raw={k: v for k, v in row.items() if v is not None},
            )
            result.loaded += 1

        return result

    def ingest_text(self, *, engagement_id: str, text: str) -> CsvIngestResult:
        """Convenience for tests: ingest a CSV string directly."""
        return self.ingest(engagement_id=engagement_id, file_obj=io.StringIO(text))
