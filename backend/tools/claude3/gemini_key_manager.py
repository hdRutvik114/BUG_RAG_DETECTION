"""
Rotates across multiple Gemini API keys.

Behavior (per spec section 11):
  - Use the CURRENT key until it is rate-limited/unavailable, then move to
    the next one. Never rotate randomly per-request.
  - If every key is rate-limited/failing, wait a configurable cooldown and
    then start again from key 1 for the NEXT candidate (we do not busy-loop
    retrying the same candidate forever).
"""

import logging
import time
from typing import List, Optional, Tuple

from llm_providers import (
    GeminiProvider,
    OpenRouterProvider,
    LLMClassificationResult,
    LLMProviderError,
    classify_with_retry,
)

logger = logging.getLogger("gemini_key_manager")


class GeminiKeyManager:
    def __init__(self, api_keys: List[Tuple[str, str]], model: str, timeout: int = 30):
        """api_keys: list of (slot_name, key) pairs, e.g. [("key_1", "AIza..."), ...]"""
        if not api_keys:
            raise ValueError("GeminiKeyManager requires at least one API key")
        self.api_keys = api_keys
        self.model = model
        self.timeout = timeout
        self._idx = 0
        self._providers = {}
        for slot, key in api_keys:
            if key.startswith("sk-or-") or "nemotron" in model.lower() or "openrouter" in model.lower():
                self._providers[slot] = OpenRouterProvider(api_key=key, model=model, timeout=timeout)
            else:
                self._providers[slot] = GeminiProvider(api_key=key, model=model, timeout=timeout)

    def _current(self) -> Tuple[str, GeminiProvider]:
        slot, _ = self.api_keys[self._idx]
        return slot, self._providers[slot]

    def _advance(self) -> bool:
        self._idx += 1
        return self._idx < len(self.api_keys)

    def reset(self) -> None:
        self._idx = 0

    def classify(
        self,
        buggy_code: str,
        fixed_code: str,
        diff: str,
        commit_message: str,
        candidates: List[str],
        max_retries: int,
        retry_delay_seconds: float,
        all_keys_cooldown_seconds: float,
        request_delay_seconds: float = 10.0,
    ) -> Tuple[Optional[LLMClassificationResult], Optional[str], int]:
        """Returns (result_or_None, key_slot_used_or_None, attempts_made).
        result is None if every key was exhausted or if the response was malformed/invalid."""
        attempts = 0
        keys_tried = 0
        n_keys = len(self.api_keys)

        while keys_tried < n_keys:
            slot, provider = self._current()
            logger.info("[LLM]\nSending semantic validation request...\nModel: %s\nKey: %s",
                        self.model, slot)
            attempts += 1
            try:
                result = classify_with_retry(
                    provider, buggy_code, fixed_code, diff, commit_message, candidates,
                    max_retries, retry_delay_seconds,
                )
            except LLMProviderError as exc:
                logger.warning("[LLM]\n%s failed (non-rate-limit error): %s", slot, exc)
                # Safely reject candidate and enforce 10s delay before next request
                time.sleep(request_delay_seconds)
                return None, slot, attempts

            time.sleep(request_delay_seconds)

            if result is not None:
                logger.info("[LLM]\nResponse received.\nDecision: %s\nCategory: %s\nConfidence: %s",
                            result.decision, result.bug_type, result.confidence)
                return result, slot, attempts

            logger.info("[Rate Limit]\n%s exhausted or failed. Switching to next key.", slot)
            keys_tried += 1
            if not self._advance():
                break

        logger.warning(
            "[Rate Limit]\nAll %d Gemini keys exhausted/rate-limited. Cooling down for %.0fs.",
            n_keys, all_keys_cooldown_seconds,
        )
        time.sleep(all_keys_cooldown_seconds)
        self.reset()
        return None, None, attempts
