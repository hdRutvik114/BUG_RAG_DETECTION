import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")
api_key = os.environ.get("OPENROUTER_API_KEY_1", "")

models = [
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "mistralai/mistral-7b-instruct:free",
]

prompt = """Analyze this code for bugs in JSON format: {"is_bug": true, "reason": "explain"}:
function getFirstItem(items) { return items[1]; }
"""

for model in models:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=8)
        print(f"Model: {model:50s} -> Status: {res.status_code}")
        if res.status_code == 200:
            print("  Response:", res.json()["choices"][0]["message"]["content"][:150])
            print("  SUCCESS!")
            break
    except Exception as e:
        print("  Error:", e)
