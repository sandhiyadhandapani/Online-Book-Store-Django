import json
import logging
import os
import random
import re
import time
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class AISummaryError(Exception):
    """Custom exception for Gemini AI summary generation errors with safe user message."""
    def __init__(self, message, status_code=503, is_config_error=False, is_network_error=False, is_transient=True):
        super().__init__(message)
        self.status_code = status_code
        self.is_config_error = is_config_error
        self.is_network_error = is_network_error
        self.is_transient = is_transient


def shorten_to_sentences(text: str, max_sentences: int = 2) -> str:
    """Shorten text to at most max_sentences, cut at a sentence end."""
    if not text or not text.strip():
        return ""
    text = text.strip()
    matches = list(re.finditer(r'([A-Za-z0-9"\'\)\]]+[.!?]+)(?:\s+|$)', text))
    if not matches:
        return text

    abbrevs = {"mr.", "mrs.", "ms.", "dr.", "prof.", "jr.", "sr.", "vs.", "etc.", "e.g.", "i.e."}
    valid_ends = []
    for m in matches:
        word = m.group(1).lower().rstrip()
        if word in abbrevs or (len(word) == 2 and word[0].isalpha() and word[1] == "."):
            continue
        valid_ends.append(m.end())
        if len(valid_ends) >= max_sentences:
            break

    if not valid_ends:
        return text
    return text[:valid_ends[-1]].strip()


def truncate_at_sentence_boundary(text: str, max_chars: int = 700) -> str:
    """Cut text at the last complete sentence within max_chars limit."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    match = re.search(r'^(.*[.!?]+)(?:\s+|$)', truncated, flags=re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return truncated.strip()


def clean_markdown_text(text: str) -> str:
    """
    Safely clean markdown symbols from the AI response and clamp length
    at the last complete sentence within 700 chars.
    """
    if not text:
        return ""
    # Remove markdown headings (# Heading)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold and italic formatting (**text**, *text*, __text__, _text_)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    # Remove inline backticks (`code`)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove blockquotes (> quote)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    # Remove bullet markers (- or * at start of line)
    text = re.sub(r"^[\*\-\+]\s+", "", text, flags=re.MULTILINE)
    # Normalize excess whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Cut at the last complete sentence within 700 chars
    return truncate_at_sentence_boundary(text, 700)


def generate_book_summary(book, save=True) -> str:
    """
    Generate an AI summary of a book using the Gemini REST API with retry and model fallback.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not api_key.strip():
        logger.error("Gemini API key is not configured in settings or environment.")
        raise AISummaryError("AI service is not configured.", status_code=503, is_config_error=True)

    api_key = api_key.strip()
    main_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
    fallback_setting = getattr(
        settings,
        "GEMINI_FALLBACK_MODELS",
        "gemini-2.5-flash,gemini-flash-latest,gemini-2.5-flash-lite"
    )
    if isinstance(fallback_setting, str):
        raw_fallbacks = [m.strip() for m in fallback_setting.split(",") if m.strip()]
    else:
        raw_fallbacks = [str(m).strip() for m in fallback_setting if str(m).strip()]

    # Collect fallback models distinct from the main model
    fallback_models = []
    for m in raw_fallbacks:
        if m != main_model and m not in fallback_models:
            fallback_models.append(m)

    timeout = getattr(settings, "GEMINI_TIMEOUT", 15)
    base_max_tokens = getattr(settings, "GEMINI_MAX_OUTPUT_TOKENS", 2048)

    prompt = (
        f"Write a neutral summary of the book '{book.title}' by {book.author} in 3 to 4 sentences "
        f"(max 90 words). Plain text only, no markdown, no spoilers of the ending. If you are not "
        f"sure about this book, say you cannot give a reliable summary instead of guessing."
    )

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    start_time = time.time()
    last_error_type = "transient"

    # Plan: (model, max_attempts)
    models_to_try = [(main_model, 3)] + [(m, 2) for m in fallback_models]

    for model, max_attempts in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        for attempt in range(1, max_attempts + 1):
            elapsed = time.time() - start_time
            if elapsed >= 30:
                raise AISummaryError(
                    "The AI is busy right now. Please try again in a few seconds.",
                    status_code=503,
                    is_transient=True
                )

            req_timeout = min(timeout, max(1.0, 30.0 - elapsed))
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": base_max_tokens,
                    "temperature": 0.4
                }
            }

            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=req_timeout)
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                last_error_type = "network"
                logger.warning("Gemini attempt %d/%d failed: %s (model=%s)", attempt, max_attempts, type(e).__name__, model)
                if attempt < max_attempts and (time.time() - start_time < 28):
                    sleep_time = (2 ** (attempt - 1)) + random.uniform(0.01, 0.2)
                    time.sleep(sleep_time)
                continue
            except requests.exceptions.Timeout as e:
                last_error_type = "transient"
                logger.warning("Gemini attempt %d/%d failed: %s (model=%s)", attempt, max_attempts, type(e).__name__, model)
                if attempt < max_attempts and (time.time() - start_time < 28):
                    sleep_time = (2 ** (attempt - 1)) + random.uniform(0.01, 0.2)
                    time.sleep(sleep_time)
                continue
            except requests.exceptions.RequestException as e:
                last_error_type = "network"
                logger.warning("Gemini attempt %d/%d failed: %s (model=%s)", attempt, max_attempts, type(e).__name__, model)
                if attempt < max_attempts and (time.time() - start_time < 28):
                    sleep_time = (2 ** (attempt - 1)) + random.uniform(0.01, 0.2)
                    time.sleep(sleep_time)
                continue

            status_code = response.status_code

            # Immediate non-retry failures: 400, 401, 403, 404
            if status_code in (401, 403):
                logger.warning("Gemini attempt %d/%d failed: HTTP %s (model=%s)", attempt, max_attempts, status_code, model)
                raise AISummaryError("AI service is not configured.", status_code=status_code, is_config_error=True)

            if status_code == 400:
                logger.warning("Gemini attempt %d/%d failed: HTTP %s (model=%s)", attempt, max_attempts, status_code, model)
                raise AISummaryError("Unable to generate summary at this time.", status_code=400)

            if status_code == 404:
                # 404 "no longer available" moves to the fallback without retrying this model
                logger.warning("Gemini attempt %d/%d failed: HTTP 404 (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                break

            # Transient errors: 429, 500, 502, 503, 504
            if status_code in (429, 500, 502, 503, 504):
                last_error_type = "transient"
                logger.warning("Gemini attempt %d/%d failed: HTTP %s (model=%s)", attempt, max_attempts, status_code, model)
                if attempt < max_attempts and (time.time() - start_time < 28):
                    sleep_time = (2 ** (attempt - 1)) + random.uniform(0.01, 0.2)
                    time.sleep(sleep_time)
                continue

            if status_code != 200:
                logger.warning("Gemini attempt %d/%d failed: HTTP %s (model=%s)", attempt, max_attempts, status_code, model)
                last_error_type = "transient"
                break

            # Status 200: Parse response
            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError):
                logger.warning("Gemini attempt %d/%d failed: InvalidJSON (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                continue

            prompt_feedback = data.get("promptFeedback") or {}
            if prompt_feedback.get("blockReason"):
                logger.warning("Gemini prompt blocked: %s", prompt_feedback.get("blockReason"))
                raise AISummaryError("Unable to generate summary due to content restrictions.", status_code=200)

            candidates = data.get("candidates")
            if not candidates or not isinstance(candidates, list) or len(candidates) == 0:
                logger.warning("Gemini attempt %d/%d failed: NoCandidates (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                continue

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason")
            if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
                logger.warning("Gemini candidate blocked with finishReason: %s", finish_reason)
                raise AISummaryError("Unable to generate summary due to content restrictions.", status_code=200)

            # Completeness: if finishReason is not STOP, retry once with double the limit
            if finish_reason != "STOP":
                logger.warning(
                    "Gemini candidate finishReason=%s, retrying once with double token limit (model=%s)",
                    finish_reason, model
                )
                double_payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": base_max_tokens * 2,
                        "temperature": 0.4
                    }
                }
                try:
                    double_resp = requests.post(endpoint, headers=headers, json=double_payload, timeout=req_timeout)
                    if double_resp.status_code == 200:
                        d_data = double_resp.json()
                        d_candidates = d_data.get("candidates") or []
                        if d_candidates and d_candidates[0].get("finishReason") == "STOP":
                            candidate = d_candidates[0]
                            finish_reason = "STOP"
                        else:
                            # Not STOP after retry: treat as failure, do NOT save
                            d_reason = d_candidates[0].get("finishReason") if d_candidates else "Unknown"
                            logger.warning(
                                "Gemini candidate finishReason=%s after double limit, treating as failure (model=%s)",
                                d_reason, model
                            )
                            last_error_type = "transient"
                            continue
                    else:
                        logger.warning(
                            "Gemini attempt %d/%d double limit retry failed: HTTP %s (model=%s)",
                            attempt, max_attempts, double_resp.status_code, model
                        )
                        last_error_type = "transient"
                        continue
                except Exception as e:
                    logger.warning(
                        "Gemini attempt %d/%d double limit retry exception: %s (model=%s)",
                        attempt, max_attempts, type(e).__name__, model
                    )
                    last_error_type = "transient"
                    continue

            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            if not parts or not isinstance(parts, list) or len(parts) == 0:
                logger.warning("Gemini attempt %d/%d failed: EmptyParts (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                continue

            raw_text = parts[0].get("text", "")
            if not raw_text or not raw_text.strip():
                logger.warning("Gemini attempt %d/%d failed: EmptyText (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                continue

            summary = clean_markdown_text(raw_text)
            if not summary:
                logger.warning("Gemini attempt %d/%d failed: CleanedTextEmpty (model=%s)", attempt, max_attempts, model)
                last_error_type = "transient"
                continue

            # Model finally worked! Log which model finally worked without the key.
            logger.info("Gemini summary succeeded using model %s", model)

            if save:
                book.ai_summary = summary
                book.ai_summary_updated = timezone.now()
                book.save(update_fields=["ai_summary", "ai_summary_updated"])

            return summary

    # If all models and retries failed:
    if last_error_type == "network":
        raise AISummaryError(
            "Could not reach the AI service. Check your internet connection and try again.",
            status_code=503,
            is_network_error=True
        )
    else:
        raise AISummaryError(
            "The AI is busy right now. Please try again in a few seconds.",
            status_code=503,
            is_transient=True
        )
