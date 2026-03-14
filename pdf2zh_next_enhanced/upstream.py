from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf2zh_next.config.model import BasicSettings
from pdf2zh_next.config.model import GUISettings
from pdf2zh_next.config.model import PDFSettings
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.config.model import TranslationSettings
from pdf2zh_next.config.translate_engine_model import OpenAISettings

from .crypto import decrypt_text
from .providers import resolve_openai_model
from .schemas import ProviderType


def _build_openai_settings(config: dict[str, Any], secrets: dict[str, Any]) -> OpenAISettings:
    return OpenAISettings(
        openai_model=resolve_openai_model(config),
        openai_base_url=config.get("base_url"),
        openai_api_key=secrets.get("api_key"),
        openai_timeout=str(config["timeout_seconds"]) if config.get("timeout_seconds") else None,
        openai_temperature=str(config["temperature"]) if config.get("temperature") is not None else None,
        openai_reasoning_effort=config.get("reasoning_effort"),
        openai_send_temprature=config.get("send_temperature"),
        openai_send_reasoning_effort=config.get("send_reasoning_effort"),
    )


def _build_bedrock_settings(config: dict[str, Any], secrets: dict[str, Any]):
    from pdf2zh_next.config.translate_engine_model import BedrockSettings

    auth_mode = config["auth_mode"]
    if auth_mode == "stored_keys":
        upstream_auth_mode = "access_key"
    elif config.get("profile_name"):
        upstream_auth_mode = "profile"
    else:
        upstream_auth_mode = "default"

    return BedrockSettings(
        bedrock_model_id=config["model_id"],
        bedrock_region=config["region"],
        bedrock_auth_mode=upstream_auth_mode,
        bedrock_profile_name=config.get("profile_name"),
        bedrock_access_key_id=secrets.get("access_key_id"),
        bedrock_secret_access_key=secrets.get("secret_access_key"),
        bedrock_session_token=secrets.get("session_token"),
        bedrock_timeout=str(config["timeout_seconds"]) if config.get("timeout_seconds") else None,
        bedrock_temperature=str(config["temperature"]) if config.get("temperature") is not None else None,
    )


def build_settings_model(
    profile_snapshot: dict[str, Any],
    options: dict[str, Any],
    *,
    output_dir: Path,
) -> SettingsModel:
    provider_type = ProviderType(profile_snapshot["provider_type"])
    config = profile_snapshot["config"]
    secrets = {
        key: decrypt_text(value) if value else None
        for key, value in profile_snapshot.get("secrets", {}).items()
    }

    translation = TranslationSettings(
        lang_in=options.get("lang_in", "en"),
        lang_out=options.get("lang_out", "ko"),
        output=str(output_dir),
        qps=options.get("qps", 4),
        ignore_cache=options.get("ignore_cache", False),
        custom_system_prompt=options.get("custom_system_prompt"),
        no_auto_extract_glossary=options.get("no_auto_extract_glossary", True),
        save_auto_extracted_glossary=options.get("save_auto_extracted_glossary", False),
    )
    pdf = PDFSettings(
        pages=options.get("pages"),
        no_mono=options.get("no_mono", False),
        no_dual=options.get("no_dual", False),
        dual_translate_first=options.get("dual_translate_first", False),
        use_alternating_pages_dual=options.get("use_alternating_pages_dual", False),
        translate_table_text=options.get("translate_table_text", True),
        skip_scanned_detection=options.get("skip_scanned_detection", False),
        auto_enable_ocr_workaround=options.get("auto_enable_ocr_workaround", False),
        enhance_compatibility=options.get("enhance_compatibility", False),
    )

    if provider_type == ProviderType.OPENAI:
        translate_engine_settings = _build_openai_settings(config, secrets)
    elif provider_type == ProviderType.BEDROCK:
        translate_engine_settings = _build_bedrock_settings(config, secrets)
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    settings = SettingsModel(
        basic=BasicSettings(),
        translation=translation,
        pdf=pdf,
        gui_settings=GUISettings(),
        translate_engine_settings=translate_engine_settings,
    )
    settings.validate_settings()
    return settings
