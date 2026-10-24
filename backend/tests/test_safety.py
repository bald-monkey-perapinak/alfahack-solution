import pytest
from pydantic import SecretStr

from backend.app.analytics import extract_shocks
from backend.app.config import Settings
from backend.app.llm import LLM, LLMUnavailable
from backend.app.security import password_hash, verify_password


def test_password_hashing():
    first = password_hash("password-for-test")
    second = password_hash("password-for-test")
    assert first != second
    assert verify_password("password-for-test", first)
    assert not verify_password("different", first)


def test_rate_hold_is_not_rise():
    assert extract_shocks("ЦБ сохранил ключевую ставку на уровне 14%.") == []
    assert extract_shocks("Ключевая ставка не изменилась.") == []
    assert extract_shocks("Инфляция снизилась.")[0]["direction"] == -1


def test_deep_paths_explain_totals_and_do_not_revisit_vertices():
    from ml.src.shock_propagation.propagator import Shock, ShockPropagator

    graph = {
        "key_rate": {"lending": {"sign": 1.0, "strength": 1.0}},
        "lending": {"gdp": {"sign": 1.0, "strength": 1.0}},
        "gdp": {"key_rate": {"sign": 1.0, "strength": 1.0}},
    }
    model = ShockPropagator(factor_graph=graph, max_depth=3, decay=0.5, min_impact=0.01)
    shock = Shock("key_rate", 1.0, 1.0)
    total = model.propagate_shock(shock)
    assert total["key_rate"] == 1.0
    assert total["gdp"] == 0.25
    paths = model._top_paths([shock], {"gdp": 1.0})
    assert paths[0].path == ["key_rate", "lending", "gdp"]
    assert paths[0].impact == total["gdp"]


def test_no_external_calls_by_default():
    llm = LLM(Settings(_env_file=None))
    with pytest.raises(LLMUnavailable):
        llm.json("test", {})


def test_live_requires_explicit_opt_in_and_allowlist():
    with pytest.raises(ValueError):
        LLM(Settings(_env_file=None, llm_mode="live"))
    with pytest.raises(ValueError):
        LLM(
            Settings(
                _env_file=None,
                llm_mode="live",
                llm_allow_external=True,
                llm_base_url="https://example.test/v1",
                llm_api_key=SecretStr("test"),
                llm_model="unapproved",
            )
        )


def test_provider_failure_does_not_leak_secret(monkeypatch):
    import httpx

    settings = Settings(
        _env_file=None,
        llm_mode="live",
        llm_allow_external=True,
        llm_base_url="https://example.test/v1",
        llm_api_key=SecretStr("secret-for-test"),
        llm_model="approved-fixture",
        llm_allowed_models=["approved-fixture"],
    )

    def fail(*args, **kwargs):
        raise httpx.ConnectError("secret-for-test")

    monkeypatch.setattr(httpx.Client, "post", fail)
    with pytest.raises(LLMUnavailable) as error:
        LLM(settings).json("private prompt", {})
    assert "secret-for-test" not in str(error.value)
