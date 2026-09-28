import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")
api_key = os.environ.get("OPENROUTER_API_KEY_1", "")

url = "https://openrouter.ai/api/v1/embeddings"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
codes = [
    "function add(a, b) { return a + b; }",
    "const fetchUser = async (id) => { return await api.get('/user/' + id); }",
    "if (!user) { throw new Error('User not found'); }"
]
payload = {
    "model": "openai/text-embedding-3-small",
    "input": codes
}

res = requests.post(url, headers=headers, json=payload, timeout=10)
print("Status:", res.status_code)
if res.status_code == 200:
    data = res.json()
    embeddings = [item["embedding"] for item in data["data"]]
    print(f"Successfully received {len(embeddings)} embeddings! Vector dim: {len(embeddings[0])}")
else:
    print("Error:", res.text)
