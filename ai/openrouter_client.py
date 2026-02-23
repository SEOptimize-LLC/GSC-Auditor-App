"""OpenRouter API client for multi-model AI analysis."""

import json
import logging
from typing import Any, Optional

import requests
import streamlit as st

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "gemini_flash": "google/gemini-2.0-flash-001",
    "claude_sonnet": "anthropic/claude-sonnet-4",
}


class OpenRouterClient:
    """Client for the OpenRouter API."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or st.secrets.get("openrouter", {}).get("api_key", "")

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "gemini_flash",
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> str:
        """Send a chat completion request to OpenRouter."""
        model_id = MODELS.get(model, model)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gsc-auditor.streamlit.app",
            "X-Title": "GSC Audit Agent",
        }

        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            logger.error(f"OpenRouter API error: {e} — {response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenRouter request failed: {e}")
            raise

    def analyze_group(
        self,
        system_prompt: str,
        findings_text: str,
    ) -> str:
        """Run group-level analysis using Gemini Flash."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": findings_text},
        ]
        return self.chat(messages, model="gemini_flash", max_tokens=3000)

    def generate_executive_summary(
        self,
        system_prompt: str,
        all_analyses_text: str,
    ) -> str:
        """Generate executive summary using Claude Sonnet."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": all_analyses_text},
        ]
        return self.chat(messages, model="claude_sonnet", max_tokens=5000)
