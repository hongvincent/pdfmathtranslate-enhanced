from types import SimpleNamespace

import pytest
from pdf2zh_next.config.cli_env_model import CLIEnvSettingsModel
from pdf2zh_next.config.translate_engine_model import BedrockSettings
from pdf2zh_next.translator.translator_impl import bedrock as bedrock_module


class DummyRateLimiter:
    def wait(self, rate_limit_params=None):
        return None


class FakeBedrockClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeSession:
    def __init__(self, response, call_log):
        self.response = response
        self.call_log = call_log

    def client(self, service_name, **kwargs):
        self.call_log["service_name"] = service_name
        self.call_log["client_kwargs"] = kwargs
        client = FakeBedrockClient(self.response)
        self.call_log["client"] = client
        return client


def _build_settings(**detail):
    settings = CLIEnvSettingsModel(
        bedrock=True,
        bedrock_detail={
            "bedrock_model_id": "amazon.nova-lite-v1:0",
            "bedrock_region": "us-east-1",
            "bedrock_auth_mode": "access_key",
            "bedrock_access_key_id": "test-access-key",
            "bedrock_secret_access_key": "test-secret-key",
            **detail,
        },
    ).to_settings_model()
    settings.validate_settings()
    return settings


def test_bedrock_settings_validate_and_normalize_access_key_mode():
    secret_key = "test-secret" + "-key"
    session_token = "test-session" + "-token"
    settings = CLIEnvSettingsModel(
        bedrock=True,
        bedrock_detail={
            "bedrock_model_id": " amazon.nova-lite-v1:0 ",
            "bedrock_region": " us-west-2 ",
            "bedrock_auth_mode": "access_key",
            "bedrock_access_key_id": " test-access-key ",
            "bedrock_secret_access_key": f" {secret_key} ",
            "bedrock_session_token": f" {session_token} ",
            "bedrock_timeout": " 45 ",
            "bedrock_temperature": " 0.3 ",
        },
    ).to_settings_model()

    settings.validate_settings()

    engine = settings.translate_engine_settings
    assert isinstance(engine, BedrockSettings)
    assert engine.bedrock_model_id == "amazon.nova-lite-v1:0"
    assert engine.bedrock_region == "us-west-2"
    assert engine.bedrock_access_key_id == "test-access-key"
    assert engine.bedrock_secret_access_key == secret_key
    assert engine.bedrock_session_token == session_token
    assert engine.bedrock_timeout == "45"
    assert engine.bedrock_temperature == "0.3"
    assert settings.term_extraction_engine_settings is engine


@pytest.mark.parametrize(
    ("detail", "message"),
    [
        (
            {
                "bedrock_auth_mode": "default",
                "bedrock_access_key_id": "test-access-key",
                "bedrock_secret_access_key": "test-secret-key",
            },
            "Credential fields must be empty when auth mode is default",
        ),
        (
            {
                "bedrock_auth_mode": "profile",
                "bedrock_access_key_id": None,
                "bedrock_secret_access_key": None,
            },
            "Profile name is required when auth mode is profile",
        ),
        (
            {
                "bedrock_temperature": "1.2",
            },
            "Temperature must be between 0 and 1",
        ),
    ],
)
def test_bedrock_settings_validation_errors(detail, message):
    settings = CLIEnvSettingsModel(
        bedrock=True,
        bedrock_detail={
            "bedrock_model_id": "amazon.nova-lite-v1:0",
            "bedrock_region": "us-east-1",
            "bedrock_auth_mode": "access_key",
            "bedrock_access_key_id": "test-access-key",
            "bedrock_secret_access_key": "test-secret-key",
            **detail,
        },
    ).to_settings_model()

    with pytest.raises(ValueError, match=message):
        settings.validate_settings()


def test_bedrock_translator_initializes_session_and_parses_response(monkeypatch):
    session_token = "temporary-session" + "-token"
    response = {
        "output": {
            "message": {
                "content": [
                    {"text": "<think>hidden</think>\nTranslated text"},
                ]
            }
        },
        "usage": {
            "inputTokens": 3,
            "outputTokens": 5,
            "totalTokens": 8,
        },
    }
    call_log = {}

    def fake_session_factory(**kwargs):
        call_log["session_kwargs"] = kwargs
        return FakeSession(response, call_log)

    def fake_config(**kwargs):
        call_log["config_kwargs"] = kwargs
        return {"config": kwargs}

    monkeypatch.setattr(
        bedrock_module,
        "boto3",
        SimpleNamespace(
            session=SimpleNamespace(
                Session=fake_session_factory,
            )
        ),
    )
    monkeypatch.setattr(bedrock_module, "Config", fake_config)

    translator = bedrock_module.BedrockTranslator(
        _build_settings(
            bedrock_model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
            bedrock_region="us-west-2",
            bedrock_timeout="20",
            bedrock_temperature="0.2",
            bedrock_session_token=session_token,
        ),
        DummyRateLimiter(),
    )

    result = translator.do_translate("Hello, world")

    assert result == "Translated text"
    assert call_log["session_kwargs"] == {
        "region_name": "us-west-2",
        "aws_access_key_id": "test-access-key",
        "aws_secret_access_key": "test-secret-key",
        "aws_session_token": session_token,
    }
    assert call_log["service_name"] == "bedrock-runtime"
    assert call_log["config_kwargs"] == {
        "connect_timeout": 20.0,
        "read_timeout": 20.0,
    }

    request = call_log["client"].calls[0]
    assert request["modelId"] == "anthropic.claude-3-5-haiku-20241022-v1:0"
    assert request["inferenceConfig"] == {"temperature": 0.2}
    assert request["messages"][0]["role"] == "user"
    assert "Hello, world" in request["messages"][0]["content"][0]["text"]
