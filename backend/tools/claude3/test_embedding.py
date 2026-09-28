import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(".env")

api_key = os.environ.get("OPENROUTER_API_KEY_1", "")
print("Using Key:", api_key[:12] + "...")

# Test OpenRouter embedding models
models_to_test = [
    "openai/text-embedding-3-small",
    "text-embedding-3-small",
    "nomic-ai/nomic-embed-text-v1.5",
]

for model in models_to_test:
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": "function add(a, b) { return a + b; }"
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Model: {model} -> Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            vec = data["data"][0]["embedding"]
            print(f"SUCCESS! Vector dimension: {len(vec)}")
            break
        else:
            print("Response:", res.text[:200])
    except Exception as e:
        print("Error:", e)
