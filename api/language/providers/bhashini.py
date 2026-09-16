"""Bhashini / ULCA -- free for non-commercial use, 22 scheduled languages.

Two-step protocol, and both steps matter:

1. Pipeline config: POST userID + ulcaApiKey to the config endpoint for a
   given task and language pair. Returns serviceIds and a compute callback
   URL with its own inference key.
2. Compute: POST the actual payload to that callback URL.

Step 1's answer is stable per language pair, so it is cached in-process
here. Doing config lookup per request doubles latency and burns quota for
an answer that didn't change.

Credentials come from the environment and are read lazily, per call --
importing this module never fails for want of a key, exactly like
api/agents/llm.py. Set ULCA_USER_ID, ULCA_API_KEY, and
BHASHINI_INFERENCE_KEY; without them every method raises LanguageError,
which the service layer treats as "drop a rung", not "crash".
"""

from __future__ import annotations

import base64
import os

import requests

from api.language.providers.base import LanguageError

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
PIPELINE_ID = "64392f96daac500b55c543cd"  # MeitY's public pipeline id


class BhashiniProvider:
    """Implements TranslationProvider, TTSProvider and ASRProvider."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._config_cache: dict[tuple[str, str, str], dict] = {}

    # -- credentials -----------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        user_id = os.environ.get("ULCA_USER_ID")
        api_key = os.environ.get("ULCA_API_KEY")
        if not user_id or not api_key:
            raise LanguageError(
                "ULCA_USER_ID / ULCA_API_KEY are not set. Register free at "
                "https://bhashini.gov.in -- without them the service falls "
                "back to browser speech and untranslated English."
            )
        return user_id, api_key

    # -- step 1: pipeline config ------------------------------------------

    def _config(self, task: str, source: str, target: str = "") -> dict:
        key = (task, source, target)
        if key in self._config_cache:
            return self._config_cache[key]

        user_id, api_key = self._credentials()
        language = {"sourceLanguage": source}
        if target:
            language["targetLanguage"] = target

        try:
            response = requests.post(
                CONFIG_URL,
                headers={"userID": user_id, "ulcaApiKey": api_key},
                json={
                    "pipelineTasks": [{"taskType": task, "config": {"language": language}}],
                    "pipelineRequestConfig": {"pipelineId": PIPELINE_ID},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LanguageError(f"Bhashini config failed: {exc}") from exc

        config = response.json()
        self._config_cache[key] = config
        return config

    def _compute_endpoint(self, config: dict) -> tuple[str, dict]:
        try:
            endpoint = config["pipelineInferenceAPIEndPoint"]
            url = endpoint["callbackUrl"]
            scheme = endpoint["inferenceApiKey"]
            return url, {scheme["name"]: scheme["value"]}
        except (KeyError, TypeError) as exc:
            raise LanguageError(f"unexpected Bhashini config shape: {config}") from exc

    def _service_id(self, config: dict) -> str:
        try:
            return config["pipelineResponseConfig"][0]["config"][0]["serviceId"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LanguageError(f"no serviceId in Bhashini config: {config}") from exc

    # -- step 2: compute ---------------------------------------------------

    def _compute(self, task: str, task_config: dict, payload: dict,
                 config: dict) -> dict:
        url, headers = self._compute_endpoint(config)
        try:
            response = requests.post(
                url, headers=headers,
                json={
                    "pipelineTasks": [{"taskType": task, "config": task_config}],
                    "inputData": payload,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LanguageError(f"Bhashini compute failed: {exc}") from exc
        return response.json()

    # -- public surface ----------------------------------------------------

    def translate(self, text: str, source: str, target: str) -> str:
        if source == target:
            return text
        config = self._config("translation", source, target)
        result = self._compute(
            "translation",
            {"language": {"sourceLanguage": source, "targetLanguage": target},
             "serviceId": self._service_id(config)},
            {"input": [{"source": text}]},
            config,
        )
        try:
            return result["pipelineResponse"][0]["output"][0]["target"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LanguageError(f"unexpected translation response: {result}") from exc

    def synthesize(self, text: str, locale: str) -> bytes:
        config = self._config("tts", locale)
        result = self._compute(
            "tts",
            {"language": {"sourceLanguage": locale},
             "serviceId": self._service_id(config), "gender": "female"},
            {"input": [{"source": text}]},
            config,
        )
        try:
            encoded = result["pipelineResponse"][0]["audio"][0]["audioContent"]
            return base64.b64decode(encoded)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LanguageError(f"unexpected tts response: {result}") from exc

    def transcribe(self, audio: bytes, locale: str) -> str:
        config = self._config("asr", locale)
        result = self._compute(
            "asr",
            {"language": {"sourceLanguage": locale},
             "serviceId": self._service_id(config)},
            {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]},
            config,
        )
        try:
            return result["pipelineResponse"][0]["output"][0]["source"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LanguageError(f"unexpected asr response: {result}") from exc
