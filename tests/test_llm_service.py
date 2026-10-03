import json

import httpx
import pytest

from app.schemas.analysis import LLMIncidentAnalysis
from app.services.llm_service import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    LLMService,
)

pytestmark = pytest.mark.anyio


def service(client: httpx.AsyncClient, api_key: str | None = "test-key") -> LLMService:
    return LLMService(client, "https://provider.example/v1/", api_key, "test-model", 7)


def completion(content: str) -> dict[str, object]:
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


async def test_request_and_parsing(analysis_result: LLMIncidentAnalysis) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://provider.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.extensions["timeout"]["read"] == 7
        assert json.loads(request.content) == {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "Return JSON"},
                {"role": "user", "content": "Incident"},
            ],
            "response_format": {"type": "json_object"},
        }
        return httpx.Response(200, json=completion(analysis_result.model_dump_json()))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await service(client).generate_analysis("Return JSON", "Incident")

    assert result == analysis_result
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failure(
    error: type[httpx.RequestError], caplog: pytest.LogCaptureFixture
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise error("SECRET raw provider diagnostic", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMProviderError) as exc:
            await service(client).generate_analysis("system", "SENSITIVE incident")
    assert "SECRET" not in str(exc.value) + caplog.text
    assert "SENSITIVE" not in caplog.text


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_non_success_status(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, text="SECRET provider body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMProviderError) as exc:
            await service(client).generate_analysis("system", "incident")
    assert "SECRET" not in str(exc.value) + caplog.text
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "null",
        "{}",
        '{"choices":[]}',
        '{"choices":[{"finish_reason":"stop","message":{"content":null}}]}',
        '{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}',
    ],
)
async def test_malformed_provider_response(body: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    ) as client:
        with pytest.raises(LLMResponseError):
            await service(client).generate_analysis("system", "incident")


@pytest.mark.parametrize("content", ["not-json", "```json\n{}\n```", "{}", "[]"])
async def test_invalid_generated_json(content: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(content))
        )
    ) as client:
        with pytest.raises(LLMResponseError):
            await service(client).generate_analysis("system", "incident")


@pytest.mark.parametrize(
    "change",
    [
        {"summary": "   "},
        {"severity": "unknown"},
        {"likely_attack_type": ""},
        {"recommended_actions": []},
        {"recommended_actions": [" "]},
        {"recommended_actions": [1]},
        {"sources": [{"document_id": 999}]},
    ],
)
async def test_invalid_analysis_schema(
    analysis_result: LLMIncidentAnalysis, change: dict[str, object]
) -> None:
    content = json.dumps(analysis_result.model_dump() | change)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(content))
        )
    ) as client:
        with pytest.raises(LLMResponseError):
            await service(client).generate_analysis("system", "incident")


@pytest.mark.parametrize("api_key", [None, "", "   "])
async def test_missing_key_never_sends_request(api_key: str | None) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unconfigured LLM must not make HTTP requests")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMConfigurationError):
            await service(client, api_key).generate_analysis("system", "incident")
