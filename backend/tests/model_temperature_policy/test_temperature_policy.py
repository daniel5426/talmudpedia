from app.services.model_temperature_policy import (
    model_requires_temperature_one,
    normalize_temperature_for_model,
)


def test_openai_gpt5_models_force_temperature_to_one():
    assert model_requires_temperature_one(provider="openai", model_name="gpt-5") is True
    assert normalize_temperature_for_model(
        provider="openai",
        model_name="gpt-5-mini",
        temperature=0.2,
    ) == 1.0


def test_openai_reasoning_models_force_temperature_to_one_even_when_omitted():
    assert model_requires_temperature_one(provider="openai", model_name="o1") is True
    assert normalize_temperature_for_model(
        provider="openai",
        model_name="o3-mini",
        temperature=None,
    ) == 1.0


def test_azure_openai_reasoning_models_force_temperature_to_one():
    assert normalize_temperature_for_model(
        provider="azure",
        model_name="o4-mini",
        temperature=0,
    ) == 1.0


def test_other_openai_models_preserve_requested_temperature():
    assert model_requires_temperature_one(provider="openai", model_name="gpt-4o") is False
    assert normalize_temperature_for_model(
        provider="openai",
        model_name="gpt-4o",
        temperature=0.3,
    ) == 0.3


def test_non_openai_providers_preserve_requested_temperature():
    assert model_requires_temperature_one(provider="anthropic", model_name="claude-sonnet-4") is False
    assert normalize_temperature_for_model(
        provider="anthropic",
        model_name="claude-sonnet-4",
        temperature=0.4,
    ) == 0.4
