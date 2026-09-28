import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(".env")

api_key = os.environ.get("OPENROUTER_API_KEY_1", "")
model = os.environ.get("GEMINI_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

print(f"Testing LLM Bug Analyzer with model: {model}")

snippets_to_test = [
    ("function getFirstItem(items) { return items[1]; }", "off_by_one"),
    ("const calculateTotalScore = (items = []) => { if (!Array.isArray(items) || items.length === 0) return 0; return items.reduce((sum, item) => sum + item.score, 0); };", "null_pointer / type_error"),
    ("function add(a, b) { return a + b; }", "clean")
]

prompt_template = """You are a world-class static code analysis AI engine.
Analyze the following JavaScript/TypeScript code snippet for real software bugs, runtime crashes, off-by-one errors, missing null/undefined checks, unhandled promises, or logical flaws.

CODE TO ANALYZE:
```javascript
{code}
```

Respond strictly in valid JSON format:
{{
  "is_bug": true or false,
  "bug_type": "off_by_one" | "null_pointer" | "async_error" | "logic_error" | "type_error" | "none",
  "reason": "Clear 1-sentence explanation of why it is a bug or clean"
}}
"""

for code, expected in snippets_to_test:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_template.format(code=code)}],
        "temperature": 0.0
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"\n--- Testing Snippet: {code[:40]}... ---")
        print(f"Status Code: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            raw_content = data["choices"][0]["message"]["content"].strip()
            print(f"Raw Output: {raw_content}")
        else:
            print("Error response:", res.text[:200])
    except Exception as e:
        print("Exception:", e)
