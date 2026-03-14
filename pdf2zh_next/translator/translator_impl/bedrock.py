import logging
from typing import Any

from babeldoc.utils.atomic_integer import AtomicInteger
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
from pdf2zh_next.translator.base_translator import BaseTranslator
from tenacity import before_sleep_log
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    from botocore.exceptions import ConnectTimeoutError
    from botocore.exceptions import EndpointConnectionError
    from botocore.exceptions import ReadTimeoutError
except ImportError:
    boto3 = None
    Config = None

    class ClientError(Exception):
        pass

    class ConnectTimeoutError(Exception):
        pass

    class EndpointConnectionError(Exception):
        pass

    class ReadTimeoutError(Exception):
        pass


logger = logging.getLogger(__name__)

_RETRYABLE_ERROR_CODES = {
    "InternalServerException",
    "ModelNotReadyException",
    "ServiceUnavailableException",
    "ThrottlingException",
}


class RetryableBedrockError(Exception):
    """Retryable Bedrock request failure"""


class BedrockTranslator(BaseTranslator):
    name = "bedrock"

    def __init__(
        self,
        settings: SettingsModel,
        rate_limiter: BaseRateLimiter,
    ):
        super().__init__(settings, rate_limiter)
        if boto3 is None or Config is None:
            raise ImportError(
                "boto3 and botocore are required to use the Bedrock translator"
            )

        engine_settings = settings.translate_engine_settings
        self.model = engine_settings.bedrock_model_id
        self.region = engine_settings.bedrock_region
        self.auth_mode = engine_settings.bedrock_auth_mode
        self.timeout = engine_settings.bedrock_timeout
        self.temperature = engine_settings.bedrock_temperature

        session_kwargs: dict[str, str] = {"region_name": self.region}
        if self.auth_mode == "profile":
            session_kwargs["profile_name"] = engine_settings.bedrock_profile_name
        elif self.auth_mode == "access_key":
            session_kwargs["aws_access_key_id"] = engine_settings.bedrock_access_key_id
            session_kwargs["aws_secret_access_key"] = (
                engine_settings.bedrock_secret_access_key
            )
            if engine_settings.bedrock_session_token:
                session_kwargs["aws_session_token"] = (
                    engine_settings.bedrock_session_token
                )

        session = boto3.session.Session(**session_kwargs)
        client_kwargs: dict[str, Any] = {}
        if self.timeout:
            timeout = float(self.timeout)
            client_kwargs["config"] = Config(
                connect_timeout=timeout,
                read_timeout=timeout,
            )
        self.client = session.client("bedrock-runtime", **client_kwargs)

        self.inference_config: dict[str, float] = {}
        if self.temperature is not None:
            self.inference_config["temperature"] = float(self.temperature)
            self.add_cache_impact_parameters("temperature", self.temperature)

        self.add_cache_impact_parameters("model", self.model)
        self.add_cache_impact_parameters("prompt", self.prompt(""))
        self.token_count = AtomicInteger()
        self.prompt_token_count = AtomicInteger()
        self.completion_token_count = AtomicInteger()

    def _to_bedrock_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": message["role"],
                "content": [{"text": str(message["content"])}],
            }
            for message in messages
        ]

    def _record_usage(self, response: dict[str, Any]) -> None:
        usage = response.get("usage", {})
        if "totalTokens" in usage:
            self.token_count.inc(usage["totalTokens"])
        if "inputTokens" in usage:
            self.prompt_token_count.inc(usage["inputTokens"])
        if "outputTokens" in usage:
            self.completion_token_count.inc(usage["outputTokens"])

    def _extract_message_text(self, response: dict[str, Any]) -> str:
        content = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("text")
        ]
        if not text_parts:
            raise ValueError("No translation text received from Bedrock")
        message = "".join(text_parts).strip()
        return self._remove_cot_content(message).strip()

    def _handle_client_error(self, exc: ClientError) -> None:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in _RETRYABLE_ERROR_CODES:
            raise RetryableBedrockError(str(exc)) from exc
        raise exc

    @retry(
        retry=retry_if_exception_type(
            (
                RetryableBedrockError,
                ConnectTimeoutError,
                EndpointConnectionError,
                ReadTimeoutError,
            )
        ),
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _converse(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        request: dict[str, Any] = {
            "modelId": self.model,
            "messages": messages,
        }
        if self.inference_config:
            request["inferenceConfig"] = self.inference_config
        try:
            return self.client.converse(**request)
        except ClientError as exc:
            self._handle_client_error(exc)
            raise

    def do_translate(self, text, rate_limit_params: dict = None) -> str:
        response = self._converse(self._to_bedrock_messages(self.prompt(text)))
        self._record_usage(response)
        return self._extract_message_text(response)

    def do_llm_translate(self, text, rate_limit_params: dict = None):
        if text is None:
            return None
        response = self._converse(
            self._to_bedrock_messages(
                [
                    {
                        "role": "user",
                        "content": text,
                    },
                ]
            )
        )
        self._record_usage(response)
        return self._extract_message_text(response)
