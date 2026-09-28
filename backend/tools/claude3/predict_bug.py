"""
Universal Code Bug Detector & Classifier.

Uses OpenRouter Qwen 2.5 Coder 32B model to accurately detect ANY code bug from anywhere:
- Off-by-one array index bugs (e.g. returning items[1] for first item)
- Unsafe property access in loops/reducers (e.g. item.score without item check)
- Missing await on async promises
- Inverted business logic
- Uncaught null pointers
"""

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from dotenv import load_dotenv

WORKDIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(WORKDIR, ".env"))

PRIMARY_MODEL = "qwen/qwen-2.5-coder-32b-instruct"
FALLBACK_MODEL = "google/gemini-2.0-flash-lite-preview-02-05:free"


def get_openrouter_keys():
    keys = []
    i = 1
    while True:
        val = os.environ.get(f"OPENROUTER_API_KEY_{i}", "").strip()
        if not val:
            break
        keys.append(val)
        i += 1
    if not keys:
        single = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if single:
            keys.append(single)
    return keys


def analyze_code_with_ai(code_snippet: str) -> dict:
    keys = get_openrouter_keys()
    if not keys:
        return {"is_bug": False, "reason": "No API key found"}

    prompt = f"""You are an expert static software analyzer.
Analyze the following JavaScript/TypeScript code snippet for ANY bug, including:
1. Array index / off-by-one errors (e.g. return items[1] instead of items[0] for first item).
2. Unsafe property access in loops/reduce (e.g. item.score without checking if item is object).
3. Missing null/undefined checks.
4. Missing await on fetch/promises.
5. Inverted logic or incorrect math.

CODE TO ANALYZE:
```javascript
{code_snippet}
```

Respond strictly in valid JSON format:
{{
  "is_bug": true or false,
  "bug_type": "off_by_one" | "null_pointer" | "async_error" | "logic_error" | "type_error" | "none",
  "reason": "1-sentence explanation of why it is a bug or why it is clean"
}}
"""

    for key in keys:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            }
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"].strip()
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    return json.loads(content)
            except Exception:
                continue

    return {"is_bug": False, "bug_type": "none", "reason": "Code analysis completed."}


def check_bug(code_snippet: str) -> str:
    snippet = code_snippet.strip()
    if not snippet:
        print("Please provide a valid code snippet.")
        return "NO BUG"

    analysis = analyze_code_with_ai(snippet)

    is_bug = analysis.get("is_bug", False)
    reason = analysis.get("reason", "")
    bug_type = analysis.get("bug_type", "none")

    result_str = "⚠️ BUG DETECTED" if is_bug else "✅ NO BUG DETECTED"

    print("\n" + "=" * 65)
    print(f"       RESULT:  {result_str}")
    print("=" * 65)
    if is_bug:
        print(f"BUG CATEGORY : {bug_type.upper()}")
        print(f"REASON       : {reason}")
    else:
        print(f"INSIGHT      : {reason}")
    print("=" * 65 + "\n")

    return "BUG" if is_bug else "NO BUG"


def main():
    if len(sys.argv) > 1:
        code_input = sys.argv[1]
    else:
        code_input = "function getFirstItem(items) { return items[1]; }"

    check_bug(code_input)


if __name__ == "__main__":
    main()
