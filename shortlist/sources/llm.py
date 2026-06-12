from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

import requests


def _detect_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER")
    if explicit:
        return explicit.lower()
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "ollama"  


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _retry_delay_seconds(resp) -> float | None:
    try:
        details = resp.json().get("error", {}).get("details", [])
        for d in details:
            if "RetryInfo" in d.get("@type", "") and d.get("retryDelay"):
                return float(str(d["retryDelay"]).rstrip("s"))
    except Exception:
        print("Failed to parse retry delay from response:", resp.text[:200], file=sys.stderr)
    return None


def _raise_clean(resp, provider: str) -> None:
    status = resp.status_code
    if status == 429:
        raise RuntimeError(
            f"{provider} rate limit hit (HTTP 429) and retries were exhausted. "
            f"You've likely used today's free quota. Options: wait for the daily reset, "
            f"or switch provider (set GROQ_API_KEY and LLM_PROVIDER=groq, or "
            f"LLM_PROVIDER=ollama for fully offline)."
        )
    body = ""
    try:
        body = str(resp.json().get("error", ""))[:200]
    except Exception:
        body = resp.text[:200]
    raise RuntimeError(f"{provider} request failed (HTTP {status}): {body}")


class LLM:
    _DEFAULT_MODEL = {
        "gemini": "gemini-2.5-flash-lite",
        "groq": "llama-3.3-70b-versatile",
        "ollama": "llama3.1:8b",
    }

    def __init__(self) -> None:
        self.provider = _detect_provider()
        self.model = os.environ.get(
            "LLM_MODEL", self._DEFAULT_MODEL.get(self.provider, "llama3.1:8b")
        )
        self._min_interval = float(os.environ.get("LLM_MIN_INTERVAL", "4.0"))
        self._last_call = 0.0

    def _throttle(self) -> None:
        if self.provider != "gemini" or self._min_interval <= 0:
            return
        wait = self._min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def batch_size(self, default: int) -> int:
        override = os.environ.get("GATE_BATCH_SIZE")
        if override:
            return max(1, int(override))
        if self.provider == "groq":
            return min(default, 8)
        return default

    def complete_json(self, system: str, user: str) -> Any:
        raw = self._raw(system, user)
        try:
            return json.loads(_strip_fences(raw))
        except (json.JSONDecodeError, TypeError):
            return None


    def _raw(self, system: str, user: str) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user)
        if self.provider == "groq":
            return self._groq(system, user)
        return self._ollama(system, user)

    def _gemini(self, system: str, user: str) -> str:
        key = os.environ["GEMINI_API_KEY"]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        headers = {"x-goog-api-key": key}
        body = {
            "contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        max_attempts = 6
        for attempt in range(max_attempts):
            self._throttle()
            r = requests.post(url, headers=headers, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == max_attempts - 1:
                    _raise_clean(r, "Gemini")
                delay = _retry_delay_seconds(r) or min(2 ** attempt * 5, 60)
                time.sleep(delay)
                continue
            if not r.ok:
                _raise_clean(r, "Gemini")
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        raise RuntimeError("unreachable")

    def _groq(self, system: str, user: str) -> str:
        key = os.environ["GROQ_API_KEY"]
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},  
        }
        max_attempts = 5
        for attempt in range(max_attempts):
            r = requests.post(url, headers=headers, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == max_attempts - 1:
                    _raise_clean(r, "Groq")
                delay = min(float(r.headers.get("retry-after", 0)) or 2 ** attempt * 2, 15)
                print(f"  [groq] rate limited, waiting {delay:.0f}s "
                      f"(attempt {attempt + 1}/{max_attempts})...", file=sys.stderr)
                time.sleep(delay)
                continue
            if not r.ok:
                _raise_clean(r, "Groq")
            return r.json()["choices"][0]["message"]["content"]
        raise RuntimeError("unreachable")

    def _ollama(self, system: str, user: str) -> str:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        r = requests.post(
            f"{host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",    
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=600,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
