"""
BiteRig LLM Service
Uses Groq SDK (primary) with OpenRouter as fallback to analyze food ingredient
images and generate detailed, creative recipes.
"""

import logging
import os
import json
import re
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("biterig.llm")

# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

# Groq vision models (all support image input directly)
GROQ_MODELS = [
    "qwen/qwen3.8-27b",                          # primary — deep reasoning
    "meta-llama/llama-4-scout-17b-16e-instruct", # fast fallback
    "llama-3.2-90b-vision-preview",              # complex visual fallback
]

# OpenRouter — last resort (uses OpenAI SDK)
OR_ENDPOINT = "https://openrouter.ai/api/v1"
OR_MODEL    = "openrouter/free"


def _make_groq_client() -> Groq | None:
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    return Groq(api_key=key) if key else None


def _make_or_client() -> OpenAI | None:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    return OpenAI(
        base_url=OR_ENDPOINT,
        api_key=key,
        default_headers={
            "HTTP-Referer": "https://github.com/PacifistJACK/BiteRig",
            "X-Title": "BiteRig",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_constraints(filters: list[str], nationality: str | None) -> str:
    parts = []
    if filters:
        parts.append(f"The recipe MUST follow these dietary/lifestyle constraints: {', '.join(filters)}.")
    if nationality:
        parts.append(
            f"The dish should be inspired by {nationality} cuisine. "
            "If the ingredients don't perfectly match, create a creative fusion that still honours the cuisine's spirit."
        )
    if not parts:
        parts.append("No dietary restrictions. Be creative and make the most delicious dish possible.")
    return " ".join(parts)


def _extract_json(text: str) -> dict:
    """Extract JSON from model response, handles markdown code blocks."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse JSON from model response: {text[:200]}")


def _is_retryable(exc: Exception) -> bool:
    s = str(exc)
    return any(code in s for code in ("429", "404", "503")) or "rate" in s.lower()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_recipe(
    image_base64: str,
    image_mime: str,
    filters: list[str],
    nationality: str | None,
    language: str = "English",
) -> dict:
    """
    Generate a recipe from a food/ingredient image using Groq (primary)
    with OpenRouter as fallback.
    """
    constraints = _build_constraints(filters, nationality)
    lang_instruction = f"IMPORTANT: Write EVERY single piece of text in the JSON (recipe name, description, steps, tips, ingredient names, tags, titles — everything) in {language}. No mixing languages."

    system_prompt = f"""You are Chef Rig — a fun, hype, street-smart AI chef who LOVES food. You roast boring recipes and bring the energy of a food truck chef meets Gordon Ramsay's wild side. You speak casually, use fun expressions, keep things exciting but SUPER clear and easy to follow. No corporate chef speak, no fancy jargon — just real, delicious, let's-get-cooking vibes.

{lang_instruction}

Analyze the food ingredients in the image and generate a fire recipe. Return ONLY a raw, valid JSON object — no markdown, no code fences, no extra text.

JSON Schema:
{{
  "recipe_name": "Catchy, fun dish name with personality",
  "description": "2 sentences — hype it up! Make it sound SO good they wanna eat immediately.",
  "detected_ingredients": ["ingredient visible in image 1", "ingredient 2"],
  "additional_ingredients": ["pantry item 1 needed", "pantry item 2"],
  "prep_time": "15 mins",
  "cook_time": "10 mins",
  "total_time": "25 mins",
  "difficulty": "Easy",
  "servings": "4 people",
  "tags": ["Quick", "High Protein", "Snack"],
  "tips": "One game-changing chef tip — keep it practical and fun.",
  "steps": [
    {{
      "step": 1,
      "title": "Short punchy title",
      "instruction": "Clear, fun, casual instruction. Like your friend is teaching you."
    }}
  ]
}}

Rules Chef Rig ALWAYS follows:
1. difficulty MUST be exactly one of: Easy, Medium, Hard.
2. prep_time, cook_time, total_time MUST be short strings like '15 mins', '10 mins'.
3. servings MUST be a short string like '2-4 people' or '4 people'.
4. Include 4 to 7 steps with short punchy titles and clear easy instructions.
5. detected_ingredients = only stuff actually visible in the photo.
6. Keep step instructions simple — no walls of text. Short punchy sentences.
7. {lang_instruction}
8. Return ONLY the JSON object. Zero extra text outside it."""

    user_content = [
        {
            "type": "text",
            "text": (
                f"Generate a recipe from the ingredients shown in this image.\n\n"
                f"Constraints: {constraints}\n\n"
                f"Language: {language}\n\n"
                "Return only the JSON object."
            ),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime};base64,{image_base64}",
            },
        },
    ]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    last_exc: Exception | None = None
    groq_client = _make_groq_client()

    # ── Groq: try each vision model in order ──────────────────────────────────
    if groq_client:
        for groq_model in GROQ_MODELS:
            try:
                logger.info("Trying Groq model: %s", groq_model)
                resp = groq_client.chat.completions.create(
                    model=groq_model,
                    messages=messages,
                    max_completion_tokens=4096,
                    temperature=1,
                    stream=False,
                )
                raw = (resp.choices[0].message.content or "").strip()
                if not raw or len(raw) < 20 or raw.lower().startswith("user safety"):
                    logger.warning("Model %s non-recipe response: %r", groq_model, raw[:80])
                    last_exc = ValueError(f"Safety/refusal: {raw[:80]}")
                    continue
                return _extract_json(raw)
            except ValueError as exc:
                logger.warning("Model %s bad JSON, trying next... (%s)", groq_model, exc)
                last_exc = exc
            except Exception as exc:
                if _is_retryable(exc):
                    logger.warning("Model %s unavailable (%s), trying next...", groq_model, str(exc)[:80])
                    last_exc = exc
                else:
                    raise

    # ── OpenRouter last resort ────────────────────────────────────────────────
    or_client = _make_or_client()
    if or_client:
        try:
            logger.info("Falling back to OpenRouter (%s)", OR_MODEL)
            resp = or_client.chat.completions.create(
                model=OR_MODEL,
                messages=messages,
                max_tokens=4096,
            )
            raw = (resp.choices[0].message.content or "").strip()
            if raw and len(raw) >= 20 and not raw.lower().startswith("user safety"):
                return _extract_json(raw)
            last_exc = ValueError(f"OpenRouter bad response: {raw[:80]}")
        except Exception as exc:
            last_exc = exc
            logger.warning("OpenRouter also failed: %s", exc)

    raise ValueError(
        f"All providers failed. Last error: {last_exc}\n"
        "Make sure GROQ_API_KEY is set in backend/.env"
    )