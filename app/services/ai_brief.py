# app/services/ai_brief.py
"""
AI Pre-Call Brief Service.

Fetches an employer's website, sends the content to Claude, and returns a
structured dict with intelligence fields. The dict is both persisted to the
employer_profiles table and formatted into the recruiter confirmation email.

Return contract:
    {
        "company_overview": str,
        "industry": str,
        "estimated_size": str,
        "hiring_needs": [str, ...],
        "talking_points": [str, ...],
        "red_flags": str | None
    }

Never raises — returns {} on any failure so booking confirmation is never blocked.
"""
import json
import logging

import httpx
import anthropic
from bs4 import BeautifulSoup

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8_000  # Safely within Claude's context window


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_website_text(url: str) -> str:
    """Fetch a URL and return cleaned readable text with all HTML stripped."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; RYZEBot/1.0; +https://ryzerecruiting.com)"
        )
    }

    response = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Strip noise elements
    for tag in soup(["script", "style", "nav", "footer", "header", "meta", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:MAX_CONTENT_CHARS]


def _build_prompt(website_text: str) -> str:
    return f"""You are an expert recruiting researcher preparing a pre-call brief \
for a finance and accounting recruiter (CPA background) at RYZE Recruiting.

Based on the website content below, return ONLY a valid JSON object.
No preamble, no explanation, no markdown fences. Just the JSON.

Required format:
{{
  "company_overview": "2-3 sentence description of what the company does and who they serve",
  "industry": "specific industry classification",
  "estimated_size": "headcount or revenue signals, e.g. 50-100 employees",
  "hiring_needs": ["role 1", "role 2", "role 3"],
  "talking_points": ["point 1", "point 2", "point 3"],
  "red_flags": "any concerns or considerations, or null if none"
}}

Website content:
{website_text}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pre_call_brief(website_url: str) -> dict:
    """
    Fetch an employer's website and use Claude to generate a structured
    pre-call recruiting brief.

    Returns a dict with keys: company_overview, industry, estimated_size,
    hiring_needs, talking_points, red_flags.

    Returns {} on any failure — never raises.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI brief generation.")
        return {}

    # 1. Fetch website content
    try:
        website_text = _fetch_website_text(website_url)
    except Exception as e:
        logger.error(f"Failed to fetch website {website_url}: {e}")
        return {}

    if not website_text:
        logger.warning(f"No readable content extracted from {website_url}")
        return {}

    # 2. Call Claude
    raw = ""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": _build_prompt(website_text)}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown fences Claude sometimes wraps JSON in
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]  # remove ```json line
            raw = raw.rsplit("```", 1)[0]  # remove closing ```
            raw = raw.strip()
    except Exception as e:
        logger.error(f"Claude API call failed for {website_url}: {e}")
        return {}

    # 3. Parse JSON response
    try:
        result = json.loads(raw)
        logger.info(f"AI brief parsed successfully for {website_url}")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI brief JSON for {website_url}: {e}")
        # Graceful fallback: store the raw text so nothing is lost
        return {"ai_brief_raw": raw}
