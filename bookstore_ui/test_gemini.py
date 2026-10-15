import os, requests
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get("GEMINI_API_KEY", "").strip()
model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
print("key length:", len(key), "| model:", model)

h = {"x-goog-api-key": key}
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
r = requests.post(url, headers=h, timeout=20,
                  json={"contents": [{"parts": [{"text": "Say hi"}]}]})
print("status:", r.status_code)
try:
    print(r.json().get("error", {}).get("message", "OK"))
except Exception:
    print(r.text[:200])

if r.status_code in (400, 404):
    m = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers=h, timeout=20).json()
    print([x["name"] for x in m.get("models", [])
           if "generateContent" in x.get("supportedGenerationMethods", [])])
