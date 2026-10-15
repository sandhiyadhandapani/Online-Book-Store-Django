import os
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Diagnostic command to check Gemini API key and model availability without exposing secrets."

    def handle(self, *args, **options):
        api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        api_key = api_key.strip() if api_key else ""

        if api_key:
            self.stdout.write(f"key set, length {len(api_key)}")
        else:
            self.stdout.write("key not set")

        main_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
        fallback_setting = getattr(
            settings,
            "GEMINI_FALLBACK_MODELS",
            "gemini-2.5-flash,gemini-flash-latest,gemini-2.5-flash-lite"
        )
        if isinstance(fallback_setting, str):
            fallback_models = [m.strip() for m in fallback_setting.split(",") if m.strip()]
        else:
            fallback_models = [str(m).strip() for m in fallback_setting if str(m).strip()]

        models = [main_model]
        for m in fallback_models:
            if m not in models:
                models.append(m)

        for model in models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers = {
                "x-goog-api-key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "contents": [{"parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5}
            }

            if not api_key:
                self.stdout.write(f"{model}: HTTP N/A - AI service is not configured.")
                continue

            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
                status_code = response.status_code
                if status_code == 200:
                    status_text = "OK"
                else:
                    try:
                        data = response.json()
                        status_text = data.get("error", {}).get("message") or response.text[:200]
                    except Exception:
                        status_text = response.text[:200]
            except requests.exceptions.RequestException as e:
                status_code = "N/A"
                status_text = f"{type(e).__name__}: {str(e)}"

            # Redact key strictly from output
            if api_key:
                status_text = str(status_text).replace(api_key, "[REDACTED]")

            # Single line per model
            status_text = " ".join(str(status_text).split())
            self.stdout.write(f"{model}: HTTP {status_code} - {status_text}")
