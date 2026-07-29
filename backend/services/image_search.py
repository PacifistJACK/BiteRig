"""
BiteRig Image Search Service
============================
Finds a representative dish image via (in priority order):

  1. Disk cache       — instant, permanent, keyed by dish name
  2. Pexels API       — primary search (PEXELS_API_KEY env var, free at pexels.com/api)
                        Great coverage including Indian, Asian, and all world cuisines.
                        Nationality hint is included in the query for relevance.
  3. TheMealDB        — no key required; quick wins for common Western dishes
  4. Unsplash API     — fallback (UNSPLASH_ACCESS_KEY env var, free at unsplash.com/developers)

With disk caching the same dish always returns the same image and API rate limits
are essentially never hit in practice.
"""

import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("biterig.image_search")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR   = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = DATA_DIR / "image_cache.json"

_cache_lock = threading.Lock()
HTTP_TIMEOUT = 6  # seconds per request


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _normalize_key(dish_name: str) -> str:
    """Lowercase, collapse whitespace — cache key that ignores minor variations."""
    return re.sub(r"\s+", " ", dish_name.lower().strip())


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, headers: dict | None = None) -> dict | None:
    req_headers = {"User-Agent": "BiteRig/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("HTTP GET failed — %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Search providers (in priority order)
# ---------------------------------------------------------------------------

def _search_pexels(dish_name: str, nationality: str | None = None) -> str | None:
    """
    Primary source. Pexels has excellent coverage of ALL world cuisines including
    Indian, Asian, Middle Eastern, etc. Nationality is included in the query
    to get the most relevant result (e.g. 'biryani indian food dish').

    Requires: PEXELS_API_KEY env var (free at https://www.pexels.com/api/)
    Rate limit: 200 req/hr, 20,000 req/month — cache keeps us well under this.
    """
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        return None

    # Build a descriptive query: dish + cuisine origin + food context
    parts = [dish_name]
    if nationality:
        parts.append(nationality)
    parts.append("food dish")
    query = urllib.parse.quote(" ".join(parts))

    url  = f"https://api.pexels.com/v1/search?query={query}&per_page=3&orientation=landscape&size=large"
    data = _get_json(url, headers={"Authorization": api_key})

    if data and data.get("photos"):
        src = data["photos"][0].get("src", {})
        img_url = src.get("large2x") or src.get("large") or src.get("medium")
        if img_url:
            logger.info("Pexels image found for '%s' (nationality=%s)", dish_name, nationality)
            return img_url
    return None


def _search_themealdb(dish_name: str) -> str | None:
    """
    Secondary source. No API key needed. Only covers ~350 mostly Western dishes,
    but useful as a no-config fallback when Pexels key isn't set yet.
    Tries progressively shorter queries to maximise match rate.
    """
    words  = dish_name.split()
    probes = [dish_name]
    if len(words) > 2:
        probes.append(" ".join(words[:2]))
    if len(words) > 1:
        probes.append(words[0])

    for q in probes:
        url  = f"https://www.themealdb.com/api/json/v1/1/search.php?s={urllib.parse.quote(q)}"
        data = _get_json(url)
        if data and data.get("meals"):
            thumb = data["meals"][0].get("strMealThumb")
            if thumb:
                logger.info("TheMealDB image found for '%s' (probe='%s')", dish_name, q)
                return thumb
    return None


def _search_unsplash(dish_name: str, nationality: str | None = None) -> str | None:
    """
    Tertiary fallback. Beautiful images, good world cuisine coverage.
    Requires: UNSPLASH_ACCESS_KEY env var (free at https://unsplash.com/developers)
    Rate limit: 50 req/hr — cache keeps us well under this.
    """
    api_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not api_key:
        return None

    parts = [dish_name]
    if nationality:
        parts.append(nationality)
    parts.append("food")
    query = urllib.parse.quote(" ".join(parts))

    url  = (
        f"https://api.unsplash.com/search/photos"
        f"?query={query}&per_page=1&orientation=landscape&client_id={api_key}"
    )
    data = _get_json(url)
    if data and data.get("results"):
        urls    = data["results"][0].get("urls", {})
        img_url = urls.get("regular") or urls.get("full")
        if img_url:
            logger.info("Unsplash image found for '%s'", dish_name)
            return img_url
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_dish_image(dish_name: str, nationality: str | None = None) -> str | None:
    """
    Return an image URL for *dish_name*, or None if nothing was found.

    Pass *nationality* (e.g. "Indian", "Italian") to improve search relevance —
    especially important for Pexels which uses it in the query.

    Results are cached permanently on disk so the same dish always returns the
    same image and we never burn API quota on repeats.
    """
    if not dish_name or not dish_name.strip():
        return None

    key = _normalize_key(dish_name)

    # 1. Cache hit
    with _cache_lock:
        cache = _load_cache()
        if key in cache:
            cached_url = cache[key].get("url")
            logger.debug("Image cache %s for '%s'", "HIT" if cached_url else "MISS(prev)", key)
            return cached_url  # None means a previous search found nothing

    # 2. Search — Pexels → TheMealDB → Unsplash
    image_url = (
        _search_pexels(dish_name, nationality)
        or _search_themealdb(dish_name)
        or _search_unsplash(dish_name, nationality)
    )

    # 3. Write back (hit or miss — prevents repeated API calls for the same dish)
    with _cache_lock:
        cache = _load_cache()
        cache[key] = {
            "url":       image_url,
            "dish":      dish_name,
            "nationality": nationality,
            "source":    "pexels" if image_url else "none",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _write_cache(cache)
        except OSError as exc:
            logger.warning("Could not write image cache: %s", exc)

    return image_url
