"""One small paid connectivity check; never logs credentials or provider response bodies.
Run from the project root: python -m scripts.check_llm
"""

from backend.app.config import get_settings
from backend.app.llm import LLM, LLMUnavailable


def main():
    settings = get_settings()
    if settings.llm_mode != "live":
        raise SystemExit("LLM_MODE is not live; no external request was made.")
    try:
        result = LLM(settings).json(
            'Верни только JSON {"status":"ok"}. Без дополнительных полей.', {"test": "connectivity"}
        )
    except LLMUnavailable as exc:
        raise SystemExit("LLM check failed: " + exc.code) from None
    if result.get("status") != "ok":
        raise SystemExit("LLM returned an unexpected JSON structure.")
    print("Live LLM JSON check passed. Model: " + settings.llm_model)


if __name__ == "__main__":
    main()
