"""Pick the default LLM client for the process.

Preference order:
  1. `OpenAIClient` when `OPENAI_API_KEY` or `AZURE_API_KEY` is set in the environment.
  2. `GeminiClient` otherwise (preserving legacy behavior and tests).
"""

from __future__ import annotations

import os
from typing import Union

from engine.llm.gemini import GeminiClient
from engine.llm.openai_client import OpenAIClient


def build_llm_client() -> Union[OpenAIClient, GeminiClient]:
    if (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("AZURE_API_KEY", "").strip()
        or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    ):
        return OpenAIClient()
    return GeminiClient()
