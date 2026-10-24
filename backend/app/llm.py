"""Explicit opt-in LLM adapter. No home-directory config, implicit models or fallback."""

import json

import httpx


class LLMUnavailable(RuntimeError):
    pass


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
            raise LLMUnavailable("Live mode is disabled")
        try:
            with httpx.Client(timeout=60, verify=True, follow_redirects=False, trust_env=False) as client:
                response = client.post(
                    self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value()},
                    json={
                        "model": self.settings.llm_model,
                        "temperature": 0.1,
                        "max_tokens": 1800,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                        ],
                    },
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = text[text.index("\n") + 1 :].rsplit("```", 1)[0].strip()
                result = json.loads(text)
                if not isinstance(result, dict):
                    raise ValueError("Expected JSON object")
                return result
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # Never propagate response bodies, provider URLs, prompt or credentials to logs/API.
            raise LLMUnavailable("LLM request failed or returned invalid JSON") from None
