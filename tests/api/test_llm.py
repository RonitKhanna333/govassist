"""api/agents/llm.py -- the Groq client's own mechanics, with requests.post
mocked. No network call, no key needed; this is not an integration test
against the real Groq API (nothing in this repo can honestly claim to be
one without a real GROQ_API_KEY -- see docs/phase2-design.md).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from api.agents.llm import GroqLLM, LLMError, Tier


def test_missing_api_key_raises_a_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    llm = GroqLLM()
    with pytest.raises(LLMError, match="GROQ_API_KEY is not set"):
        llm.complete("system", "user", Tier.FAST)


def test_fast_and_reasoning_tiers_use_different_models():
    llm = GroqLLM(api_key="test-key")
    with patch("api.agents.llm.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {"choices": [{"message": {"content": "ok"}}]},
        )
        mock_post.return_value.raise_for_status = lambda: None

        llm.complete("sys", "usr", Tier.FAST)
        fast_model = mock_post.call_args.kwargs["json"]["model"]

        llm.complete("sys", "usr", Tier.REASONING)
        reasoning_model = mock_post.call_args.kwargs["json"]["model"]

    assert fast_model != reasoning_model
    assert fast_model == "llama-3.1-8b-instant"
    assert reasoning_model == "llama-3.3-70b-versatile"


def test_temperature_is_always_zero():
    llm = GroqLLM(api_key="test-key")
    with patch("api.agents.llm.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            json=lambda: {"choices": [{"message": {"content": "ok"}}]},
        )
        mock_post.return_value.raise_for_status = lambda: None
        llm.complete("sys", "usr", Tier.FAST)

    assert mock_post.call_args.kwargs["json"]["temperature"] == 0


def test_network_failure_raises_llmerror_not_a_raw_requests_exception():
    llm = GroqLLM(api_key="test-key")
    with patch("api.agents.llm.requests.post",
               side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(LLMError, match="Groq request failed"):
            llm.complete("sys", "usr", Tier.FAST)


def test_unexpected_response_shape_raises_llmerror():
    llm = GroqLLM(api_key="test-key")
    with patch("api.agents.llm.requests.post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"unexpected": "shape"})
        mock_post.return_value.raise_for_status = lambda: None
        with pytest.raises(LLMError, match="unexpected Groq response shape"):
            llm.complete("sys", "usr", Tier.FAST)
