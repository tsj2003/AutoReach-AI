"""Session-scoped debug NDJSON writer. Do not log secrets."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEBUG_LOG_PATH = "/Users/tarandeepsinghjuneja/reverse/.cursor/debug-6c4129.log"


def agent_debug(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # #region agent log
    payload = {
        "sessionId": "6c4129",
        "runId": "post-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    logger.info("DEBUG6c4129 %s %s %s", hypothesis_id, message, data)
    # #endregion
