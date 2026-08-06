"""
BiteRig Backend — FastAPI Application
Serves the /api/cook endpoint that accepts a food image + preferences
and returns an AI-generated recipe.
chlooo
"""

import asyncio
import base64
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Import after dotenv so env vars are available
from services.llm import generate_recipe
from services.image_search import get_dish_image

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("biterig")

app = FastAPI(
    title="BiteRig API",
    description="Upload a food ingredient photo and get an AI-generated recipe.",
    version="1.0.0",
)

# CORS — allow all origins during development.
# In production set ALLOWED_ORIGINS env var to your Azure Static Web App URL.
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Max image size: 10 MB
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

# ---------------------------------------------------------------------------
# Recipe storage (local JSON file)
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
RECIPES_FILE = DATA_DIR / "recipes.json"
_recipes_lock = threading.Lock()


def _load_recipes() -> list:
    """Load all saved recipes from disk."""
    if not RECIPES_FILE.exists():
        return []
    try:
        with open(RECIPES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_recipe(entry: dict) -> None:
    """Prepend a new recipe entry and persist to disk (thread-safe)."""
    with _recipes_lock:
        recipes = _load_recipes()
        recipes.insert(0, entry)
        recipes = recipes[:200]          # keep last 200 max
        with open(RECIPES_FILE, "w", encoding="utf-8") as f:
            json.dump(recipes, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "BiteRig API is running"}


@app.get("/api/health")
def health_check():
    """Health check endpoint used by Azure container health probes."""
    return {"status": "ok", "service": "BiteRig API", "version": "1.0.0"}


@app.get("/api/recipes", response_model=List[dict])
def list_recipes():
    """
    Return all previously generated recipes, newest first.
    Each entry has: id, created_at, filters, nationality, and the full recipe.
    """
    return _load_recipes()


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str):
    """Fetch a single saved recipe by its UUID."""
    for entry in _load_recipes():
        if entry.get("id") == recipe_id:
            return entry
    raise HTTPException(status_code=404, detail="Recipe not found.")


@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: str):
    """Delete a single saved recipe by its UUID."""
    with _recipes_lock:
        recipes = _load_recipes()
        updated = [r for r in recipes if r.get("id") != recipe_id]
        if len(updated) == len(recipes):
            raise HTTPException(status_code=404, detail="Recipe not found.")
        with open(RECIPES_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
    return {"deleted": recipe_id}


@app.post("/api/cook")
async def cook(
    image: UploadFile = File(..., description="Photo of your food ingredients"),
    filters: str = Form(
        default="[]",
        description='JSON array of filter strings, e.g. ["Vegan","Under 20m"]',
    ),
    nationality: Optional[str] = Form(
        default=None,
        description="Optional cuisine nationality, e.g. 'Indian'",
    ),
):
    """
    Main endpoint: analyse an ingredient image and return a recipe.

    - **image**: multipart image file (JPEG, PNG, WebP supported)
    - **filters**: JSON-encoded list of dietary/style filters
    - **nationality**: optional cuisine nationality
    """
    # --- Validate image ---
    content_type = image.content_type or "image/jpeg"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {content_type}. Use JPEG, PNG or WebP.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image too large. Maximum size is 10 MB.",
        )
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image file.")

    # --- Parse filters ---
    try:
        filters_list: list[str] = json.loads(filters)
        if not isinstance(filters_list, list):
            filters_list = []
    except (json.JSONDecodeError, ValueError):
        filters_list = []

    # Clean nationality
    clean_nationality = nationality.strip() if nationality and nationality.strip() else None

    logger.info(
        "cook() called | filters=%s | nationality=%s | image_size=%d bytes",
        filters_list,
        clean_nationality,
        len(image_bytes),
    )

    # --- Call LLM ---
    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        # Run sync LLM call in a thread pool so it doesn't block the event loop
        recipe = await asyncio.to_thread(
            generate_recipe,
            image_base64=image_b64,
            image_mime=content_type,
            filters=filters_list,
            nationality=clean_nationality,
        )
    except ValueError as exc:
        logger.error("LLM error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI model error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during recipe generation")
        raise HTTPException(
            status_code=500,
            detail="Something went wrong on our end. Please try again.",
        ) from exc

    # --- Stamp with ID + timestamp and persist ---
    recipe_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    recipe["id"]         = recipe_id
    recipe["created_at"] = created_at

    # --- Dish image (disabled for fast response time) ---
    recipe["image_url"] = None


    entry = {
        "id":          recipe_id,
        "created_at":  created_at,
        "filters":     filters_list,
        "nationality": clean_nationality,
        "recipe":      recipe,
    }
    try:
        _save_recipe(entry)
        logger.info("Recipe saved: %s (%s)", recipe.get("recipe_name"), recipe_id)
    except OSError as exc:
        logger.warning("Could not persist recipe to disk: %s", exc)

    return JSONResponse(content=recipe)
