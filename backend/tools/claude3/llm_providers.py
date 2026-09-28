"""
LLM provider abstraction for semantic bug classification.

Design intent (see miner.py for how this is used):
  - Regex/AST in miner.py only generates CANDIDATE categories.
  - This module makes the actual semantic decision by reading the real
    buggy/fixed code, not just matching keywords.
  - GeminiProvider is implemented now. To add another provider later
    (OpenAI, Anthropic, a local model, etc.), subclass LLMProvider and
    implement .classify() with the same return type - nothing else in
    the miner needs to change.
"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("llm_providers")

APPROVED_BUG_TYPES: List[str] = [
    "async_error", "null_pointer", "logic_error", "type_error", "api_misuse",
    "security_vulnerability", "off_by_one", "exception_handling", "resource_leak",
    "performance_issue", "input_validation", "state_management",
]

VALID_SEVERITIES = {"low", "medium", "high", "critical"}

MAX_CODE_CHARS = 2000
MAX_DIFF_CHARS = 2500


class LLMProviderError(Exception):
    """Non-rate-limit failure: network error, malformed response, schema
    validation failure, server error, etc. Callers should try a fallback
    provider (if configured) rather than retry the same provider."""


class RateLimitError(Exception):
    """Raised specifically for HTTP 429 so callers can apply exponential
    backoff and retry the SAME provider before giving up on it."""


@dataclass
class LLMClassificationResult:
    decision: str                       # "accept" | "reject"
    bug_type: Optional[str]
    confidence: float
    root_cause: str
    bug_description: str
    fix_description: str
    severity: str
    evidence: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    raw_text: str = ""


PROMPT_TEMPLATE = """You are a senior JavaScript/TypeScript software engineer performing
semantic bug classification for a research dataset.

Your task is to determine the ACTUAL ROOT CAUSE of a bug by comparing
the buggy code with the fixed code.

Do NOT classify based only on keywords.

For example:
- Seeing "await" does NOT automatically mean async_error.
- Seeing "req.body" does NOT automatically mean input_validation.
- Seeing a database call does NOT automatically mean resource_leak.
- Seeing "try/catch" does NOT automatically mean exception_handling.

You must determine what behavior was actually incorrect and what the
fix changed.

BUGGY CODE:
```
{buggy_code}
```

FIXED CODE:
```
{fixed_code}
```

DIFF:
```
{diff}
```

COMMIT MESSAGE:
{commit_message}

CANDIDATE BUG TYPES:
{candidate_categories}

Choose exactly ONE candidate if the evidence clearly supports it.

If none of the candidates accurately describes the actual root cause,
return "reject".

Do not invent a new bug category.

Return ONLY valid JSON using exactly this schema:

{{
"decision": "accept | reject",
"bug_type": "one approved category or null",
"confidence": 0.0,
"root_cause": "short explanation",
"bug_description": "short explanation",
"fix_description": "short explanation",
"severity": "low | medium | high | critical",
"evidence": [
"concrete evidence from the code",
"concrete evidence from the change"
]
}}"""


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def build_prompt(buggy_code: str, fixed_code: str, diff: str,
                  commit_message: str, candidates: List[str]) -> str:
    return PROMPT_TEMPLATE.format(
        buggy_code=_truncate(buggy_code, MAX_CODE_CHARS),
        fixed_code=_truncate(fixed_code, MAX_CODE_CHARS),
        diff=_truncate(diff, MAX_DIFF_CHARS),
        commit_message=(commit_message or "").strip()[:300],
        candidate_categories=", ".join(candidates),
    )


def validate_llm_result(parsed: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed, dict):
        return None

    decision = parsed.get("decision")
    if decision not in ("accept", "reject"):
        return None

    bug_type = parsed.get("bug_type")
    if decision == "accept":
        if bug_type not in APPROVED_BUG_TYPES:
            return None
    else:
        bug_type = None

    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= confidence <= 1.0):
        return None

    severity = parsed.get("severity", "medium")
    if severity not in VALID_SEVERITIES:
        severity = "medium"

    evidence = parsed.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)] if evidence else []
    evidence = [str(e) for e in evidence][:10]

    return {
        "decision": decision,
        "bug_type": bug_type,
        "confidence": confidence,
        "root_cause": str(parsed.get("root_cause", "") or "")[:500],
        "bug_description": str(parsed.get("bug_description", "") or "")[:500],
        "fix_description": str(parsed.get("fix_description", "") or "")[:500],
        "severity": severity,
        "evidence": evidence,
    }


class LLMProvider(ABC):
    name: str = "base"
    model: str = "unknown"

    @abstractmethod
    def classify(
        self,
        buggy_code: str,
        fixed_code: str,
        diff: str,
        commit_message: str,
        candidates: List[str],
    ) -> LLMClassificationResult:
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    name = "google"

    def __init__(self, api_key: str, model: str, timeout: int = 30):
        if not api_key:
            raise ValueError("GeminiProvider requires a non-empty api_key")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

    def classify(
        self,
        buggy_code: str,
        fixed_code: str,
        diff: str,
        commit_message: str,
        candidates: List[str],
    ) -> LLMClassificationResult:
        prompt = build_prompt(buggy_code, fixed_code, diff, commit_message, candidates)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 500},
        }

        try:
            res = requests.post(self._url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMProviderError(f"request failed: {exc}") from exc

        if res.status_code == 429:
            raise RateLimitError("rate limited (HTTP 429)")
        if res.status_code >= 500:
            raise LLMProviderError(f"server error (HTTP {res.status_code})")
        if res.status_code != 200:
            raise LLMProviderError(f"unexpected status {res.status_code}: {res.text[:200]}")

        try:
            data = res.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"could not extract text from response: {exc}") from exc

        cleaned = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"response was not valid JSON: {exc}") from exc

        validated = validate_llm_result(parsed)
        if validated is None:
            raise LLMProviderError("response failed schema validation")

        return LLMClassificationResult(
            provider=self.name,
            model=self.model,
            raw_text=cleaned,
            **validated,
        )


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "nvidia/nemotron-3-super-120b-a12b:free", timeout: int = 30):
        if not api_key:
            raise ValueError("OpenRouterProvider requires a non-empty api_key")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._url = "https://openrouter.ai/api/v1/chat/completions"

    def classify(
        self,
        buggy_code: str,
        fixed_code: str,
        diff: str,
        commit_message: str,
        candidates: List[str],
    ) -> LLMClassificationResult:
        prompt = build_prompt(buggy_code, fixed_code, diff, commit_message, candidates)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/bugfix-dataset-builder",
            "X-Title": "BugFix Dataset Builder",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 1500,
        }

        try:
            res = requests.post(self._url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMProviderError(f"request failed: {exc}") from exc

        if res.status_code == 429:
            raise RateLimitError("rate limited (HTTP 429)")
        if res.status_code in (402, 403):
            raise RateLimitError(f"quota/authorization limit (HTTP {res.status_code})")
        if res.status_code >= 500:
            raise LLMProviderError(f"server error (HTTP {res.status_code})")
        if res.status_code != 200:
            raise LLMProviderError(f"unexpected status {res.status_code}: {res.text[:200]}")

        try:
            data = res.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMProviderError("empty choices array in OpenRouter response")
            message = choices[0].get("message", {})
            text = message.get("content", "")
            if not text:
                text = choices[0].get("text", "")
            if not text:
                raise LLMProviderError("could not extract text content from choice")
            text = text.strip()
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"could not extract text from response: {exc}") from exc

        # Robust JSON extraction: strip code fences, find outermost braces { ... }
        raw = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = raw[start:end + 1].strip()
        else:
            cleaned = raw

        # Strip any JS single-line comments inside JSON if present
        cleaned_no_comments = re.sub(r"^\s*//.*$", "", cleaned, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(cleaned_no_comments)
            except json.JSONDecodeError as exc:
                raise LLMProviderError(f"response was not valid JSON: {exc}") from exc

        validated = validate_llm_result(parsed)
        if validated is None:
            raise LLMProviderError("response failed schema validation")

        return LLMClassificationResult(
            provider=self.name,
            model=self.model,
            raw_text=cleaned,
            **validated,
        )


def classify_with_retry(
    provider: LLMProvider,
    buggy_code: str,
    fixed_code: str,
    diff: str,
    commit_message: str,
    candidates: List[str],
    max_retries: int,
    base_backoff_seconds: float,
) -> Optional[LLMClassificationResult]:
    attempt = 0
    while True:
        try:
            return provider.classify(buggy_code, fixed_code, diff, commit_message, candidates)
        except RateLimitError:
            attempt += 1
            if attempt > max_retries:
                logger.warning(
                    "[RATE LIMIT]\n%s exhausted %d retries. Giving up on this provider for this sample.",
                    provider.name, max_retries,
                )
                return None
            wait = base_backoff_seconds * (2 ** (attempt - 1))
            logger.info(
                "[RATE LIMIT]\n%s returned 429. Waiting %.0fs before retry %d/%d.",
                provider.name, wait, attempt, max_retries,
            )
            time.sleep(wait)


def classify_bug_with_providers(
    primary: LLMProvider,
    fallback: Optional[LLMProvider],
    buggy_code: str,
    fixed_code: str,
    diff: str,
    commit_message: str,
    candidates: List[str],
    max_retries: int,
    base_backoff_seconds: float,
) -> Optional[LLMClassificationResult]:
    try:
        result = classify_with_retry(
            primary, buggy_code, fixed_code, diff, commit_message, candidates,
            max_retries, base_backoff_seconds,
        )
        if result is not None:
            return result
    except LLMProviderError as exc:
        logger.warning("[PRIMARY FAILED]\nProvider: %s\nReason: %s", primary.name, exc)

    if fallback is None:
        return None

    logger.info("[FALLBACK]\n%s unavailable. Using fallback provider %s.", primary.name, fallback.name)
    try:
        return classify_with_retry(
            fallback, buggy_code, fixed_code, diff, commit_message, candidates,
            max_retries, base_backoff_seconds,
        )
    except LLMProviderError as exc:
        logger.warning("[FALLBACK FAILED]\nProvider: %s\nReason: %s", fallback.name, exc)
        return None
