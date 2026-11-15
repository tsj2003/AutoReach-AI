import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel
# Cursor will implement this Gateway
from engine.llm.gateway import AgnosticLLMGateway
from engine.core.types import TenantContext

# Dummy schema to test structured enforcement
class MockEmailDraft(BaseModel):
    subject: str
    body: str


@pytest.fixture
def sample_tenant():
    return TenantContext(
        tenant_id="t-llm-99",
        campaign_id="cmp-99",
        # Tenant explicitly requests Claude
        variables={"preferred_llm": "anthropic/claude-3-5-sonnet-20240620"},
        encrypted_secrets={
            "anthropic_api_key": "sk-ant-mock-key",
            "openai_api_key": "sk-oai-mock-key"
        }
    )


@pytest.mark.asyncio
@patch("engine.llm.gateway.acompletion")
async def test_gateway_enforces_structured_output_and_routing(mock_acompletion, sample_tenant):
    """
    Forces the gateway to use LiteLLM to route to the correct model,
    inject the correct tenant API key, and return a validated Pydantic model.
    """
    # Simulate a successful LiteLLM structured response
    mock_message = MagicMock()
    mock_message.content = '{"subject": "Quick chat?", "body": "Hey, saw the funding."}'
    mock_choice = MagicMock(message=mock_message)
    mock_response = MagicMock(choices=[mock_choice])
    mock_acompletion.return_value = mock_response

    gateway = AgnosticLLMGateway()

    # Act: Request a drafted email from the LLM
    result = await gateway.generate_structured(
        system_prompt="You are an outbound expert.",
        user_prompt="Draft an email.",
        response_schema=MockEmailDraft,
        tenant_context=sample_tenant
    )

    # Assert 1: The response was automatically parsed into the strict Pydantic schema
    assert isinstance(result, MockEmailDraft)
    assert result.subject == "Quick chat?"

    # Assert 2: LiteLLM was called with the tenant's exact configurations
    mock_acompletion.assert_called_once()
    call_kwargs = mock_acompletion.call_args.kwargs

    assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20240620"
    assert call_kwargs["api_key"] == "sk-ant-mock-key" # Safely extracted the correct key
    assert call_kwargs["response_format"] == MockEmailDraft # Instructed LiteLLM to enforce the schema


@pytest.mark.asyncio
async def test_gateway_falls_back_to_default_model():
    """Ensures the gateway works even if the tenant doesn't specify a model."""
    ctx_no_pref = TenantContext(
        tenant_id="t-llm-88", campaign_id="c-88",
        variables={}, encrypted_secrets={"openai_api_key": "sk-oai-default"}
    )
    gateway = AgnosticLLMGateway(default_model="gpt-4o")

    with patch("engine.llm.gateway.acompletion") as mock_acompletion:
        mock_acompletion.return_value.choices = [
            MagicMock(message=MagicMock(content='{"subject": "Hi", "body": "Hello"}'))
        ]

        await gateway.generate_structured("sys", "user", MockEmailDraft, ctx_no_pref)

        # Assert the default was respected
        assert mock_acompletion.call_args.kwargs["model"] == "gpt-4o"
        assert mock_acompletion.call_args.kwargs["api_key"] == "sk-oai-default"
