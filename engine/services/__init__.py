"""
Service layer: business operations that combine multiple primitives.

The cockpit, CLI, and (future) public API all go through these. Keeping
the orchestration here means UI code stays thin and we don't accidentally
duplicate business rules across surfaces.

Public surface:
    OperationsService — engagement / agent / prospect / reply / meeting ops
    PnLService        — per-engagement revenue + cost reporting (OaaS billing)
    CsvIngestService  — bulk prospect ingestion from CSV uploads
"""

from engine.services.operations import OperationsService  # noqa: F401
from engine.services.pnl import PnLReport, PnLService  # noqa: F401
from engine.services.csv_ingest import CsvIngestResult, CsvIngestService  # noqa: F401
from engine.services.reply_detector import GmailReplyDetector, ReplyDetectionResult  # noqa: F401
from engine.services.reply_actions import ReplyActionExecutor, ReplyActionResult  # noqa: F401

__all__ = [
    "OperationsService",
    "PnLService",
    "PnLReport",
    "CsvIngestService",
    "CsvIngestResult",
    "GmailReplyDetector",
    "ReplyDetectionResult",
    "ReplyActionExecutor",
    "ReplyActionResult",
]
