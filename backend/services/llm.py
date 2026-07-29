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

ENDPOINT = "https://models.github.ai/inference"
MODEL_NAME = "openai/o4-mini"


def _get_client() -> OpenAI:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")
    return OpenAI(base_url=ENDPOINT, api_key=token)


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
    client = _get_client()
    constraints = _build_constraints(filters, nationality)

    system_prompt = """You are an award-winning chef and culinary AI. Your job is to look at a photo of food ingredients and generate a stunning, creative, restaurant-quality recipe that anyone can cook at home.

Return ONLY a valid JSON object — no markdown, no explanation, no code blocks. Just raw JSON.

Use this exact schema:
{
  "recipe_name": "Creative and evocative dish name",
  "description": "2-3 sentence appetizing description that makes the reader hungry",
  "detected_ingredients": ["list of ingredients you can see in the image"],
  "additional_ingredients": ["extra pantry ingredients needed that aren't in the image"],
  "prep_time": "X minutes",
  "cook_time": "X minutes",
  "total_time": "X minutes",
  "difficulty": "Easy",
  "servings": "2-4 people",
  "tags": ["Vegetarian", "Quick", "etc — based on actual recipe properties"],
  "tips": "One brilliant pro chef tip for this dish",
  "steps": [
    {"step": 1, "title": "Short step title", "instruction": "Detailed, clear instruction with temperatures, timings, and technique tips"},
    {"step": 2, "title": "Short step title", "instruction": "..."}
  ]
}

Rules:
- difficulty must be exactly one of: Easy, Medium, Hard
- Include 5 to 8 steps. Each step must have a clear title and a detailed instruction.
- detected_ingredients should list only what you can actually see in the image.
- Make the recipe name creative and memorable.
- The steps should be written in a confident, chef-like voice."""

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
        model=MODEL_NAME,
        max_completion_tokens=2000,
    )

    raw = response.choices[0].message.content
    return _extract_json(raw)