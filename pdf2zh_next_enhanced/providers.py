from __future__ import annotations

from typing import Any

import boto3
import openai

from .schemas import ProviderType
from .schemas import ProviderValidationResponse


def resolve_openai_model(config: dict[str, Any]) -> str:
    if config.get("use_snapshot") and config.get("snapshot_model"):
        return str(config["snapshot_model"])
    return str(config.get("model") or "gpt-5.4")


def build_bedrock_session(config: dict[str, Any], secrets: dict[str, Any]):
    session_kwargs: dict[str, Any] = {
        "region_name": config["region"],
    }
    if config.get("auth_mode") == "mounted_aws_profile":
        if config.get("profile_name"):
            session_kwargs["profile_name"] = config["profile_name"]
    else:
        session_kwargs["aws_access_key_id"] = secrets.get("access_key_id")
        session_kwargs["aws_secret_access_key"] = secrets.get("secret_access_key")
        if secrets.get("session_token"):
            session_kwargs["aws_session_token"] = secrets["session_token"]
    return boto3.session.Session(**session_kwargs)


def validate_profile(profile: dict[str, Any]) -> ProviderValidationResponse:
    provider_type = ProviderType(profile["provider_type"])
    config = profile["config"]
    secrets = profile["secrets"]

    if provider_type == ProviderType.OPENAI:
        client_kwargs: dict[str, Any] = {
            "api_key": secrets.get("api_key"),
        }
        if config.get("base_url"):
            client_kwargs["base_url"] = config["base_url"]
        client = openai.OpenAI(**client_kwargs)
        models = [model.id for model in client.models.list().data]
        selected_model = resolve_openai_model(config)
        if selected_model not in models:
            return ProviderValidationResponse(
                ok=True,
                provider_type=provider_type,
                message=f"Credentials are valid. Model `{selected_model}` was not listed by the API, but manual override is allowed.",
                validated_models=models[:100],
            )
        return ProviderValidationResponse(
            ok=True,
            provider_type=provider_type,
            message=f"Credentials are valid for model `{selected_model}`.",
            validated_models=models[:100],
        )

    if provider_type == ProviderType.BEDROCK:
        if config.get("auth_mode") == "stored_keys":
            if not secrets.get("access_key_id"):
                raise ValueError("Access key ID is required for stored key authentication")
            if not secrets.get("secret_access_key"):
                raise ValueError("Secret access key is required for stored key authentication")
        session = build_bedrock_session(config, secrets)
        client = session.client("bedrock", region_name=config["region"])
        response = client.list_foundation_models(byOutputModality="TEXT")
        summaries = response.get("modelSummaries", [])
        models = sorted({item["modelId"] for item in summaries if "modelId" in item})
        selected_model = config["model_id"]
        message = f"Bedrock credentials are valid for region `{config['region']}`."
        if selected_model not in models:
            message += f" Model `{selected_model}` was not returned by ListFoundationModels, but manual model ids are allowed."
        return ProviderValidationResponse(
            ok=True,
            provider_type=provider_type,
            message=message,
            validated_models=models[:200],
        )

    raise ValueError(f"Unsupported provider: {provider_type}")
