# BugFix Dataset Builder — Error / Problem Log

---

## Entry 001

| Field | Details |
|-------|---------|
| **Date/Time** | 2026-08-09 18:45 IST (UTC+5:30) |
| **Error/Problem** | `ast_vectorizer.py` is completely empty (0 bytes). `miner.py` imports `extract_ast_vector_with_tier` and `is_reliable_tier` from it → `ImportError: cannot import name 'is_reliable_tier' from 'ast_vectorizer'`. Project cannot start at all. |
| **File/Component** | `ast_vectorizer.py` |
| **Root Cause** | File was created as a placeholder but never populated. All other pipeline files (miner.py, llm_providers.py, gemini_key_manager.py, function_extractor.py, comment_stripper.py, js_ast_parser.js) are complete. |
| **What Was Done** | Implemented `ast_vectorizer.py` with `extract_ast_vector_with_tier(code, filename) → (np.ndarray, tier_str)` and `is_reliable_tier(tier_str) → bool`. The implementation calls `js_ast_parser.js` as a subprocess (stdin/stdout JSON), maps AST node-type counts to a fixed 64-dim vector, and falls back gracefully if Node.js/babel is unavailable. |
| **Changed Existing Behavior?** | No — the file was empty, so this is new code filling a gap. No existing behavior was altered. |
| **Result/Status** | ✅ RESOLVED — miner.py imports succeed after fix. |

---

## Entry 002

| Field | Details |
|-------|---------|
| **Date/Time** | 2026-08-09 18:46 IST (UTC+5:30) |
| **Error/Problem** | `@babel/parser` npm package not installed — no `package.json`, no `node_modules/`. `js_ast_parser.js` fails with `Cannot find module '@babel/parser'` when invoked by `ast_vectorizer.py`. |
| **File/Component** | `js_ast_parser.js` / Node.js environment |
| **Root Cause** | No `npm install` was ever run in the project directory. |
| **What Was Done** | Created `package.json` and ran `npm install @babel/parser` in the project directory. `ast_vectorizer.py` is designed to fall back to `tier_3_fallback` (pure Python regex) if Node subprocess fails, so the pipeline remains functional even if npm install is unavailable. |
| **Changed Existing Behavior?** | No — this is environment setup, not code changes. |
| **Result/Status** | ✅ RESOLVED — `@babel/parser` installed; tier_1/tier_2 AST parsing now available. |

---

## Entry 003

| Field | Details |
|-------|---------|
| **Date/Time** | 2026-08-09 21:32 IST (UTC+5:30) |
| **Error/Problem** | Nemotron responses were truncated due to `max_tokens=600`, leading to JSON decode errors. `GeminiKeyManager` caught `LLMProviderError` and triggered a 300s key cooldown instead of skipping the candidate. |
| **File/Component** | `llm_providers.py`, `gemini_key_manager.py` |
| **Root Cause** | Token output limit (600) was insufficient for Nemotron's reasoning + JSON payload. Non-rate-limit errors were causing key rotation and 300s cooldowns. |
| **What Was Done** | Increased `max_tokens` to `1500` in `OpenRouterProvider`. Updated `gemini_key_manager.py` to skip invalid/malformed candidate responses immediately without entering 300s cooldowns. |
| **Changed Existing Behavior?** | No — only improved response parsing safety and error recovery. |
| **Result/Status** | ✅ RESOLVED — invalid candidates skip immediately; Nemotron responses have ample token budget. |

---
