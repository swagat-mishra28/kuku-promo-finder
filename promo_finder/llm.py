"""One tiny interface for every model: complete_json(system, user) -> dict.

Swap models by editing config.yaml (provider + model) or env vars. No SDKs, only
HTTP, so any OpenAI-compatible endpoint (Groq, OpenRouter, Together, Ollama,
vLLM, or an API Kuku provides) works with zero code changes.
Responses are cached on disk by prompt hash: re-runs are free and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class LLM:
    def __init__(self, cfg: dict):
        # from_env=False (the web app) uses only cfg: environment variables are shared by every
        # visitor of a Streamlit server, so one visitor's key must never be read from there.
        from_env = cfg.get("from_env", True)
        if from_env:
            load_dotenv()
        env = (lambda k, d: os.getenv(k, d)) if from_env else (lambda k, d: d)
        self.provider = env("PROMO_LLM_PROVIDER", cfg.get("provider", "none"))
        self.model = env("PROMO_LLM_MODEL", cfg.get("model", ""))
        self.base_url = env("PROMO_LLM_BASE_URL", cfg.get("base_url", ""))
        self.api_key = cfg.get("api_key", "") or (
            os.getenv(cfg.get("api_key_env", "PROMO_LLM_API_KEY"), "") or os.getenv("PROMO_LLM_API_KEY", "")
            if from_env else "")
        self.temperature = cfg.get("temperature", 0.2)
        # Optional: low/medium/high for reasoning models (e.g. gpt-oss). Sent only to groq/openai_compatible.
        self.reasoning_effort = env("PROMO_LLM_REASONING_EFFORT", cfg.get("reasoning_effort") or "")
        # cache=False (the web app) keeps uploaded transcripts off disk.
        self.use_cache = cfg.get("cache", True)
        self.cache_dir = Path(cfg.get("cache_dir", ".cache/llm"))
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = cfg.get("min_seconds_between_calls", 0.0)  # free-tier rate limits
        self.max_run_tokens = cfg.get("max_run_tokens", 0)  # stop a run before a daily token cap
        self._last = 0.0
        self.calls = 0
        self.cache_hits = 0
        self.tokens_in = 0
        self.tokens_out = 0

    @property
    def enabled(self) -> bool:
        return self.provider not in ("", "none", None)

    def name(self) -> str:
        return f"{self.provider}:{self.model}" if self.enabled else "rules-only"

    @property
    def sent_effort(self) -> str:
        """reasoning_effort actually sent to the API ("" when unset or the provider ignores it)."""
        return self.reasoning_effort if self.provider in ("groq", "openai_compatible") else ""

    def complete_json(self, system: str, user: str, retries: int = 3) -> dict:
        # Effort changes the answer, so it is part of the key. Unset effort keeps the old key format.
        effort = f"|effort={self.sent_effort}" if self.sent_effort else ""
        key = hashlib.sha256(f"{self.provider}|{self.model}{effort}|{system}|{user}".encode()).hexdigest()[:24]
        path = self.cache_dir / f"{key}.json"
        if self.use_cache and path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        err = None
        for attempt in range(retries):
            try:
                wait = self.min_interval - (time.time() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.time()
                text = self._call(system, user)
                self.calls += 1
                out = _extract_json(text)
                if self.use_cache:
                    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
                return out
            except Exception as e:  # noqa: BLE001
                err = e
                if " 429" in str(e) or "quota" in str(e).lower():
                    break   # rate limit or daily cap: retrying only burns more quota
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"{self.name()} failed: {err}")

    # ---------------- providers ----------------
    def _call(self, system: str, user: str) -> str:
        p = self.provider
        if p == "gemini":
            return self._gemini(system, user)
        if p == "anthropic":
            return self._anthropic(system, user)
        if p in ("openai", "openai_compatible", "groq", "openrouter", "ollama"):
            return self._openai_compat(system, user)
        raise LLMError(f"unknown provider {p}")

    def _gemini(self, system, user):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
               f"?key={self.api_key}")
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": self.temperature, "responseMimeType": "application/json"}}
        r = requests.post(url, json=body, timeout=120)
        if r.status_code != 200:
            raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
        um = data.get("usageMetadata", {})
        self.tokens_in += um.get("promptTokenCount", 0)
        self.tokens_out += um.get("candidatesTokenCount", 0)
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _openai_compat(self, system, user):
        defaults = {"groq": "https://api.groq.com/openai/v1", "openai": "https://api.openai.com/v1",
                    "openrouter": "https://openrouter.ai/api/v1", "ollama": "http://localhost:11434/v1"}
        base = self.base_url or defaults.get(self.provider, "")
        body = {"model": self.model, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}}
        if self.sent_effort:
            body["reasoning_effort"] = self.sent_effort
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = requests.post(f"{base.rstrip('/')}/chat/completions", json=body, headers=headers, timeout=120)
        if r.status_code != 200:
            raise LLMError(f"{self.provider} {r.status_code}: {r.text[:300]}")
        data = r.json()
        u = data.get("usage", {})
        self.tokens_in += u.get("prompt_tokens", 0)
        self.tokens_out += u.get("completion_tokens", 0)
        return data["choices"][0]["message"]["content"]

    def _anthropic(self, system, user):
        body = {"model": self.model, "max_tokens": 1200, "temperature": self.temperature,
                "system": system + "\nReturn only a JSON object.",
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=headers, timeout=120)
        if r.status_code != 200:
            raise LLMError(f"anthropic {r.status_code}: {r.text[:300]}")
        data = r.json()
        u = data.get("usage", {})
        self.tokens_in += u.get("input_tokens", 0)
        self.tokens_out += u.get("output_tokens", 0)
        return "".join(b.get("text", "") for b in data["content"])
