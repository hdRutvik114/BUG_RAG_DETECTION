import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")
api_key = os.environ.get("OPENROUTER_API_KEY_1", "")

models = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "openchat/openchat-7b:free",
    "nousresearch/hermes-3-llama-3.1-8b:free",
    "qwen/qwen-2.5-coder-32b-instruct",
    "google/gemini-flash-1.5",
]

prompt = """Analyze this JS code for bugs: function getFirstItem(items) { return items[1]; }"""

for model in models:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=8)
        print(f"Model: {model:50s} -> Status: {res.status_code}")
        if res.status_code == 200:
            print("  Response:", res.json()["choices"][0]["message"]["content"][:150])
            print("  SUCCESS!")
            break
        else:
            print("  Error:", res.text[:120])
    except Exception as e:
        print("  Error:", e)
