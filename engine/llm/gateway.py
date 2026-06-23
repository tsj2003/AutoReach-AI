"""Provider-agnostic structured LLM gateway via LiteLLM."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from engine.runtime.context import TenantContext

try:
    from litellm import acompletion
except ImportError:  # pragma: no cover - exercised only without optional dep
    async def acompletion(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("litellm is not installed")


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AgnosticLLMGateway:
    """Route tenant LLM calls to the requested provider with strict schemas."""

    def __init__(self, *, default_model: str = "gpt-4o") -> None:
        self.default_model = default_model

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[SchemaT],
        tenant_context: TenantContext,
    ) -> SchemaT:
        model = tenant_context.variables.get("preferred_llm") or self.default_model
        api_key = self._api_key_for_model(model=model, tenant_context=tenant_context)

        response = await acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            api_key=api_key,
            response_format=response_schema,
        )
        content = response.choices[0].message.content
        return self._parse_schema(response_schema, content)

    @staticmethod
    def _api_key_for_model(*, model: str, tenant_context: TenantContext) -> str | None:
        key_name = AgnosticLLMGateway._key_name_for_model(model)
        return tenant_context.encrypted_secrets.get(key_name)

    @staticmethod
    def _key_name_for_model(model: str) -> str:
        normalized = model.strip().lower()
        if normalized.startswith("anthropic/") or "claude" in normalized:
            return "anthropic_api_key"
        if normalized.startswith("gemini/") or normalized.startswith("google/"):
            return "gemini_api_key"
        if normalized.startswith("azure/"):
            return "azure_api_key"
        if normalized.startswith("openai/") or normalized.startswith("gpt-") or normalized.startswith("o"):
            return "openai_api_key"
        provider = normalized.split("/", 1)[0]
        return f"{provider}_api_key"

    @staticmethod
    def _parse_schema(response_schema: type[SchemaT], content: Any) -> SchemaT:
        if isinstance(content, response_schema):
            return content
        if isinstance(content, dict):
            if hasattr(response_schema, "model_validate"):
                return response_schema.model_validate(content)
            return response_schema.parse_obj(content)  # pragma: no cover - pydantic v1
        if hasattr(response_schema, "model_validate_json"):
            return response_schema.model_validate_json(str(content))
        return response_schema.parse_raw(str(content))  # pragma: no cover - pydantic v1
