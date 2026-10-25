import httpx
import pytest
from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.llm import LLM, LLMUnavailable


@pytest.fixture
def live_settings():
    return Settings(
        _env_file=None,
        llm_mode="live",
        llm_allow_external=True,
        llm_api_key=SecretStr("unit-test-only-key"),
        llm_base_url="https://gateway.example.test/v1",
        llm_model="qwen/qwen3.6-35b-a3b",
        llm_allowed_models=["qwen/qwen3.6-35b-a3b"],
    )


def reply(payload, status=200):
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "https://gateway.example.test/v1/chat/completions"),
    )


def test_json_mode_disables_reasoning_and_preserves_tls(live_settings, monkeypatch):
    def post(client, url, **kwargs):
        assert kwargs["json"]["reasoning"] == {"effort": "none"}
        assert kwargs["json"]["response_format"] == {"type": "json_object"}
        assert kwargs["json"]["max_tokens"] == 3000
        assert url == "https://gateway.example.test/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer unit-test-only-key"
        return reply({"choices": [{"finish_reason": "stop", "message": {"content": '{"status":"ok"}'}}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    assert LLM(live_settings).json("JSON only", {}) == {"status": "ok"}


@pytest.mark.parametrize(
    "status,payload,code",
    [
        (401, {"error": "sensitive-provider-message"}, "llm_auth_failed"),
        (403, {"error": "sensitive-provider-message"}, "llm_auth_failed"),
        (402, {"error": "sensitive-provider-message"}, "llm_budget_exceeded"),
        (429, {"error": "rate limited"}, "llm_rate_limited"),
        (429, {"error": "Budget has been exceeded"}, "llm_budget_exceeded"),
        (500, {"error": "sensitive-provider-message"}, "llm_provider_unavailable"),
        (400, {"error": "sensitive-provider-message"}, "llm_request_failed"),
    ],
)
def test_provider_errors_are_safe_and_actionable(live_settings, monkeypatch, status, payload, code):
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: reply(payload, status))
    with pytest.raises(LLMUnavailable) as exc:
        LLM(live_settings).json("private data", {})
    assert exc.value.code == code
    assert "sensitive-provider-message" not in str(exc.value)
    assert live_settings.llm_api_key.get_secret_value() not in str(exc.value)


@pytest.mark.parametrize(
    "choice,code",
    [
        ({"finish_reason": "length", "message": {"content": '{"partial":true}'}}, "llm_output_truncated"),
        (
            {"finish_reason": "length", "message": {"content": None, "reasoning": "ignored"}},
            "llm_output_truncated",
        ),
        ({"finish_reason": "stop", "message": {"content": None}}, "llm_empty_response"),
        ({"finish_reason": "stop", "message": {"content": "[]"}}, "llm_invalid_json"),
        ({"finish_reason": "stop", "message": {"content": "not json"}}, "llm_invalid_response"),
    ],
)
def test_truncated_empty_and_invalid_outputs(live_settings, monkeypatch, choice, code):
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: reply({"choices": [choice]}))
    with pytest.raises(LLMUnavailable) as exc:
        LLM(live_settings).json("test", {})
    assert exc.value.code == code


def test_provider_timeout_is_sanitized(live_settings, monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("sensitive-provider-message")

    monkeypatch.setattr(httpx.Client, "post", timeout)
    with pytest.raises(LLMUnavailable) as exc:
        LLM(live_settings).json("test", {})
    assert exc.value.code == "llm_timeout"


def test_budget_error_reaches_job_status(authorized, monkeypatch):
    from backend.app.analytics import AnalysisFailure
    from backend.worker import Worker

    client, db, settings, headers = authorized
    job = client.post("/api/v1/analyses", json={"max_events": 1}, headers=headers).json()["id"]

    def fail(*args, **kwargs):
        raise AnalysisFailure([{"tool": "plan", "result": {}}], "llm_budget_exceeded")

    monkeypatch.setattr("backend.worker.analyze_material", fail)
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert result["status"] == "failed" and result["error_code"] == "llm_budget_exceeded"
    assert (
        db.one("SELECT error_message FROM analysis_runs WHERE job_id=%s", (job,))["error_message"]
        == "llm_budget_exceeded"
    )


@pytest.mark.parametrize("kind", ["timeout", "transport", "rate", "provider", "auth", "budget", "invalid"])
def test_only_transient_errors_retry_once(live_settings, monkeypatch, kind):
    sleeps = []
    calls = []
    attempts = []
    monkeypatch.setattr("backend.app.llm.time.sleep", sleeps.append)

    def post(client, url, **kwargs):
        assert client.timeout.connect == 10 and client.timeout.read == 180
        calls.append(kwargs["json"])
        if kind == "timeout":
            raise httpx.ReadTimeout("private provider response")
        if kind == "transport":
            raise httpx.ConnectError("private provider response")
        if kind == "invalid":
            return reply({"choices": [{"message": {"content": "bad json"}}]})
        return reply(
            {"error": "private provider response"},
            {"rate": 429, "provider": 503, "auth": 401, "budget": 402}[kind],
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    llm = LLM(live_settings)
    llm.on_attempt = attempts.append
    with pytest.raises(LLMUnavailable) as exc:
        llm.json("private prompt", {"private": "data"})
    transient = kind in ("timeout", "transport", "rate", "provider")
    assert len(calls) == (2 if transient else 1)
    assert attempts == ([1, 2] if transient else [1])
    assert sleeps == ([2] if transient else [])
    assert "private" not in str(exc.value)
    if transient:
        assert calls[0] == calls[1]


def test_timeout_then_success_retries_only_failed_request(live_settings, monkeypatch):
    calls = []
    monkeypatch.setattr("backend.app.llm.time.sleep", lambda _: None)

    def post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("private")
        return reply({"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    assert LLM(live_settings).json("test", {}) == {"ok": True}
    assert len(calls) == 2
