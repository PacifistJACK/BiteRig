"""
BiteRig LLM Service
Uses GitHub AI Inference (openai/o4-mini) to analyze food ingredient images
and generate detailed, creative recipes.
"""

import os
import json
import base64
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Default endpoint & model settings (supports OpenRouter, GitHub Models, or OpenAI)
DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it:free"



def _get_client_and_model() -> tuple[OpenAI, str]:
    # Check for OpenRouter API Key first
    openrouter_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        model = (os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME") or DEFAULT_MODEL).strip()
        endpoint = (os.environ.get("OPENAI_BASE_URL") or DEFAULT_ENDPOINT).strip()
        client = OpenAI(
            base_url=endpoint,
            api_key=openrouter_key,
            default_headers={
                "HTTP-Referer": "https://github.com/PacifistJACK/BiteRig",
                "X-OpenRouter-Title": "BiteRig",
            },
        )
        return client, model

    # Fallback to GitHub Models / Azure Inference
    github_token = (os.environ.get("GITHUB_AI_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if github_token:
        endpoint = (os.environ.get("OPENAI_BASE_URL") or "https://models.inference.ai.azure.com").strip()
        model = (os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME") or "gpt-4o-mini").strip()
        return OpenAI(base_url=endpoint, api_key=github_token), model

    # Fallback to standard OpenAI API Key
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if openai_key:
        endpoint = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        model = (os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME") or "gpt-4o-mini").strip()
        return OpenAI(base_url=endpoint, api_key=openai_key), model

    raise ValueError(
        "No API Key found. Please set OPENROUTER_API_KEY, GITHUB_TOKEN, or OPENAI_API_KEY in backend/.env"
    )




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
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Last resort: find first { ... }
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse JSON from model response: {text[:200]}")


def generate_recipe(
    image_base64: str,
    image_mime: str,
    filters: list[str],
    nationality: str | None,
) -> dict:
    """
    Generate a recipe from a food/ingredient image.

    Args:
        image_base64: Base64-encoded image data (no data URI prefix).
        image_mime:   MIME type of the image (e.g. 'image/jpeg').
        filters:      List of dietary/style filters (e.g. ['Vegan', 'Under 20m']).
        nationality:  Optional cuisine nationality string (e.g. 'Indian').

    Returns:
        A dict matching the recipe JSON schema.
    """
    client, model = _get_client_and_model()
    constraints = _build_constraints(filters, nationality)


    system_prompt = """You are an expert chef AI. Analyze the food ingredients in the image and generate a clear, appetizing, step-by-step recipe.

Return ONLY a raw, valid JSON object without markdown formatting, code fences, or extra commentary.

JSON Schema:
{
  "recipe_name": "Evocative dish name",
  "description": "Short 2-sentence appetizing description",
  "detected_ingredients": ["ingredient visible in image 1", "ingredient 2"],
  "additional_ingredients": ["pantry item 1 needed", "pantry item 2"],
  "prep_time": "15 mins",
  "cook_time": "10 mins",
  "total_time": "25 mins",
  "difficulty": "Easy",
  "servings": "4 people",
  "tags": ["Quick", "High Protein", "Snack"],
  "tips": "One practical pro chef tip",
  "steps": [
    {
      "step": 1,
      "title": "Prep the Ingredients",
      "instruction": "Clear, concise instruction."
    }
  ]
}

Formatting Rules:
1. difficulty MUST be exactly one of: Easy, Medium, Hard.
2. prep_time, cook_time, total_time MUST be short strings like '15 mins', '10 mins'.
3. servings MUST be a short string like '2-4 people' or '4 people'.
4. Include 4 to 7 numbered steps with short titles and actionable instructions.
5. detected_ingredients should list only items visible in the photo.
6. Write instructions clearly in plain, friendly chef language."""


    user_message = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime};base64,{image_base64}",
                "detail": "high",
            },
        },
        {
            "type": "text",
            "text": (
                f"Generate a recipe from the ingredients shown in this image.\n\n"
                f"Constraints: {constraints}\n\n"
                "Return only the JSON object."
            ),
        },
    ]

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        model=model,
        max_tokens=2000,
    )



    raw = response.choices[0].message.content
    return _extract_json(raw)