"""Explicit opt-in client for the approved OpenAI-compatible hackathon gateway."""

import json

import httpx


class LLMUnavailable(RuntimeError):
    def __init__(self, code="llm_unavailable"):
        super().__init__(code)
        self.code = code


class LLM:
    def __init__(self, settings):
        self.settings = settings
        if settings.llm_mode not in ("offline", "live"):
            raise ValueError("LLM_MODE must be offline or live")
        if settings.llm_mode == "live":
            if not settings.llm_allow_external:
                raise ValueError("Live LLM requires LLM_ALLOW_EXTERNAL=true")
            if not settings.llm_base_url.startswith("https://"):
                raise ValueError("Live LLM requires HTTPS")
            if not settings.llm_api_key.get_secret_value():
                raise ValueError("LLM_API_KEY required")
            if not settings.llm_model or settings.llm_model not in settings.llm_allowed_models:
                raise ValueError("LLM_MODEL must be explicitly included in LLM_ALLOWED_MODELS")

    def json(self, system: str, data: dict) -> dict:
        if self.settings.llm_mode != "live":
            raise LLMUnavailable("llm_disabled")
        try:
            with httpx.Client(
                timeout=self.settings.llm_timeout_seconds,
                verify=True,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value()},
                    json={
                        "model": self.settings.llm_model,
                        "temperature": 0.1,
                        "max_tokens": self.settings.llm_max_tokens,
                        "response_format": {"type": "json_object"},
                        "reasoning": {"effort": self.settings.llm_reasoning_effort},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                        ],
                    },
                )
            if response.status_code >= 400:
                # Classify locally; never return provider text, URL, headers or prompt.
                body = response.content[:4096].lower()
                if response.status_code == 402 or b"budget has been exceeded" in body:
                    raise LLMUnavailable("llm_budget_exceeded")
                if response.status_code in (401, 403):
                    raise LLMUnavailable("llm_auth_failed")
                if response.status_code == 429:
                    raise LLMUnavailable("llm_rate_limited")
                if response.status_code >= 500:
                    raise LLMUnavailable("llm_provider_unavailable")
                raise LLMUnavailable("llm_request_failed")
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise LLMUnavailable("llm_output_truncated")
            content = choice["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise LLMUnavailable("llm_empty_response")
            text = content.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :].rsplit("```", 1)[0].strip()
            result = json.loads(text)
            if not isinstance(result, dict):
                raise LLMUnavailable("llm_invalid_json")
            return result
        except httpx.TimeoutException:
            raise LLMUnavailable("llm_timeout") from None
        except httpx.HTTPError:
            raise LLMUnavailable("llm_transport_error") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMUnavailable("llm_invalid_response") from None
