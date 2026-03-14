import logging

import httpx
import openai
from babeldoc.utils.atomic_integer import AtomicInteger
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.translator.base_rate_limiter import BaseRateLimiter
from pdf2zh_next.translator.base_translator import BaseTranslator
from tenacity import before_sleep_log
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential

logger = logging.getLogger(__name__)


class OpenAITranslator(BaseTranslator):
    # https://github.com/openai/openai-python
    name = "openai"

    def __init__(
        self,
        settings: SettingsModel,
        rate_limiter: BaseRateLimiter,
    ):
        super().__init__(settings, rate_limiter)
        self.timeout = settings.translate_engine_settings.openai_timeout
        self.base_url = settings.translate_engine_settings.openai_base_url
        self.client = openai.OpenAI(
            base_url=self.base_url,
            api_key=settings.translate_engine_settings.openai_api_key,
            timeout=float(self.timeout) if self.timeout else openai.NOT_GIVEN,
            http_client=httpx.Client(
                limits=httpx.Limits(
                    max_connections=None, max_keepalive_connections=None
                )
            ),
        )
        self.options = {}
        self.temperature = settings.translate_engine_settings.openai_temperature
        self.reasoning_effort = (
            settings.translate_engine_settings.openai_reasoning_effort
        )
        self.send_temperature = (
            settings.translate_engine_settings.openai_send_temprature
        )
        self.send_reasoning_effort = (
            settings.translate_engine_settings.openai_send_reasoning_effort
        )

        if self.send_temperature and self.temperature:
            self.add_cache_impact_parameters("temperature", self.temperature)
            self.options["temperature"] = float(self.temperature)
        if self.send_reasoning_effort and self.reasoning_effort:
            self.add_cache_impact_parameters("reasoning_effort", self.reasoning_effort)
            self.options["reasoning_effort"] = self.reasoning_effort

        self.model = settings.translate_engine_settings.openai_model
        self.add_cache_impact_parameters("model", self.model)
        self.add_cache_impact_parameters("prompt", self.prompt(""))
        self.token_count = AtomicInteger()
        self.prompt_token_count = AtomicInteger()
        self.completion_token_count = AtomicInteger()
        self.cache_hit_prompt_token_count = AtomicInteger()

        self.enable_json_mode = (
            settings.translate_engine_settings.openai_enable_json_mode
        )
        if self.enable_json_mode:
            self.add_cache_impact_parameters("enable_json_mode", self.enable_json_mode)
        self.use_responses_api = (
            self.model.startswith("gpt-5")
            and (not self.base_url or "api.openai.com" in self.base_url)
        )

    def _record_chat_usage(self, response) -> None:
        try:
            if hasattr(response, "usage") and response.usage:
                if hasattr(response.usage, "total_tokens"):
                    self.token_count.inc(response.usage.total_tokens)
                if hasattr(response.usage, "prompt_tokens"):
                    self.prompt_token_count.inc(response.usage.prompt_tokens)
                if hasattr(response.usage, "completion_tokens"):
                    self.completion_token_count.inc(response.usage.completion_tokens)
                if hasattr(response.usage, "prompt_cache_hit_tokens"):
                    self.cache_hit_prompt_token_count.inc(
                        response.usage.prompt_cache_hit_tokens
                    )
                elif hasattr(response.usage, "prompt_tokens_details") and hasattr(
                    response.usage.prompt_tokens_details, "cached_tokens"
                ):
                    self.cache_hit_prompt_token_count.inc(
                        response.usage.prompt_tokens_details.cached_tokens
                    )
        except Exception as e:
            logger.error(f"Error getting token usage: {e}")

    def _record_responses_usage(self, response) -> None:
        try:
            if hasattr(response, "usage") and response.usage:
                if hasattr(response.usage, "total_tokens"):
                    self.token_count.inc(response.usage.total_tokens)
                if hasattr(response.usage, "input_tokens"):
                    self.prompt_token_count.inc(response.usage.input_tokens)
                if hasattr(response.usage, "output_tokens"):
                    self.completion_token_count.inc(response.usage.output_tokens)
                if hasattr(response.usage, "input_tokens_details") and hasattr(
                    response.usage.input_tokens_details, "cached_tokens"
                ):
                    self.cache_hit_prompt_token_count.inc(
                        response.usage.input_tokens_details.cached_tokens
                    )
        except Exception as e:
            logger.error(f"Error getting token usage: {e}")

    def _extract_responses_text(self, response) -> str:
        if getattr(response, "output_text", None):
            return response.output_text.strip()
        output = getattr(response, "output", []) or []
        parts = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    def _responses_create(self, input_text: str):
        options = {}
        if self.send_temperature and self.temperature:
            options["temperature"] = float(self.temperature)
        if self.send_reasoning_effort and self.reasoning_effort:
            options["reasoning"] = {"effort": self.reasoning_effort}
        return self.client.responses.create(
            model=self.model,
            input=input_text,
            **options,
        )

    @retry(
        retry=retry_if_exception_type(openai.RateLimitError),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def do_translate(self, text, rate_limit_params: dict = None) -> str:
        options = self.options.copy()
        if (
            self.enable_json_mode
            and rate_limit_params
            and rate_limit_params.get("request_json_mode", False)
        ):
            options["response_format"] = {"type": "json_object"}

        prompt_text = self.prompt(text)[0]["content"]
        if self.use_responses_api:
            try:
                response = self._responses_create(prompt_text)
                self._record_responses_usage(response)
                message = self._extract_responses_text(response)
                message = self._remove_cot_content(message)
                if message:
                    return message
            except Exception as e:
                logger.warning(
                    "Responses API failed for %s, falling back to chat completions: %s",
                    self.model,
                    e,
                )

        response = self.client.chat.completions.create(
            model=self.model,
            **options,
            messages=self.prompt(text),
        )
        self._record_chat_usage(response)
        message = response.choices[0].message.content.strip()
        message = self._remove_cot_content(message)
        return message

    @retry(
        retry=retry_if_exception_type(openai.RateLimitError),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def do_llm_translate(self, text, rate_limit_params: dict = None):
        if text is None:
            return None
        options = self.options.copy()
        if (
            self.enable_json_mode
            and rate_limit_params
            and rate_limit_params.get("request_json_mode", False)
        ):
            options["response_format"] = {"type": "json_object"}

        if self.use_responses_api:
            try:
                response = self._responses_create(text)
                self._record_responses_usage(response)
                message = self._extract_responses_text(response)
                message = self._remove_cot_content(message)
                if message:
                    return message
            except Exception as e:
                logger.warning(
                    "Responses API failed for %s, falling back to chat completions: %s",
                    self.model,
                    e,
                )

        response = self.client.chat.completions.create(
            model=self.model,
            **options,
            messages=[
                {
                    "role": "user",
                    "content": text,
                },
            ],
        )
        self._record_chat_usage(response)
        message = response.choices[0].message.content.strip()
        message = self._remove_cot_content(message)
        return message
