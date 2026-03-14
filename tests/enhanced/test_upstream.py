from __future__ import annotations

from pdf2zh_next_enhanced.upstream import _build_bedrock_settings


def test_bedrock_auth_mode_mapping_for_upstream_settings():
    default_settings = _build_bedrock_settings(
        {
            "region": "us-east-1",
            "model_id": "amazon.nova-lite-v1:0",
            "auth_mode": "mounted_aws_profile",
            "profile_name": None,
            "timeout_seconds": None,
            "temperature": None,
        },
        {},
    )
    assert default_settings.bedrock_auth_mode == "default"

    profile_settings = _build_bedrock_settings(
        {
            "region": "us-east-1",
            "model_id": "amazon.nova-lite-v1:0",
            "auth_mode": "mounted_aws_profile",
            "profile_name": "default",
            "timeout_seconds": None,
            "temperature": None,
        },
        {},
    )
    assert profile_settings.bedrock_auth_mode == "profile"

    access_key_settings = _build_bedrock_settings(
        {
            "region": "us-east-1",
            "model_id": "amazon.nova-lite-v1:0",
            "auth_mode": "stored_keys",
            "profile_name": None,
            "timeout_seconds": None,
            "temperature": None,
        },
        {
            "access_key_id": "AKIA123",
            "secret_access_key": "secret",
            "session_token": None,
        },
    )
    assert access_key_settings.bedrock_auth_mode == "access_key"
