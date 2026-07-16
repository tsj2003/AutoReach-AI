"""
LLM clients used by the engine.

For now: Gemini (structured JSON output). Future: provider-agnostic
abstraction (OpenAI / Anthropic / local) when we need it. For Phase 3 a
single concrete client is enough — premature abstraction would obscure the
actual prompts.
"""

from engine.llm.gemini import (  # noqa: F401
    DEFAULT_MODEL,
    CostBreakdown,
    GeminiClient,
    GeminiError,
    GeminiResult,
    GeminiUnavailable,
    GeminiUsage,
    cost_breakdown_for_result,
    estimate_cost_cents,
)
from engine.llm.gateway import AgnosticLLMGateway  # noqa: F401
from engine.llm.classifier import (  # noqa: F401
    ClassificationResult,
    classify_and_draft,
)
from engine.llm.personalizer import (  # noqa: F401
    PersonalizationResult,
    personalize_outbound,
)

__all__ = [
    "GeminiClient",
    "GeminiError",
    "GeminiResult",
    "GeminiUnavailable",
    "DEFAULT_MODEL",
    "AgnosticLLMGateway",
    "estimate_cost_cents",
    "cost_breakdown_for_result",
    "CostBreakdown",
    "GeminiUsage",
    "ClassificationResult",
    "classify_and_draft",
    "PersonalizationResult",
    "personalize_outbound",
]
