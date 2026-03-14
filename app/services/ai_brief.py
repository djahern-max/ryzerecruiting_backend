# app/services/ai_brief.py
"""
AI Pre-Call Brief Service.

Strategy:
  1. Try to scrape the employer's website and send the content to Claude.
  2. If the website blocks the request (403, timeout, etc.), fall back to
     prompting Claude using only the company name and domain — Claude knows
     most well-known companies from training data and produces a solid brief.
  3. Returns {} on total failure so booking confirmation is never blocked.

Return contract:
    {
        "company_overview": str,
        "industry": str,
        "estimated_size": str,
        "hiring_needs": [str, ...],
        "talking_points": [str, ...],
        "red_flags": str | None
    }
"""
import json
import logging
import re

import httpx
import anthropic
from bs4 import BeautifulSoup

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8_000  # Safely within Claude's context window


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_website_text(url: str) -> str | None:
    """
    Fetch a URL and return cleaned readable text with HTML stripped.
    Returns None if the request fails for any reason (caller handles fallback).
    Tries bare domain first, then www. prefix if needed.
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # Build a list of URLs to try: original, then www. variant
    urls_to_try = [url]
    if "://www." not in url:
        urls_to_try.append(url.replace("://", "://www.", 1))

    for attempt_url in urls_to_try:
        try:
            response = httpx.get(
                attempt_url, headers=headers, timeout=10, follow_redirects=True
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(
                ["script", "style", "nav", "footer", "header", "meta", "noscript"]
            ):
                tag.decompose()

            text = soup.get_text(separator="\n")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            content = "\n".join(lines)[:MAX_CONTENT_CHARS]

            if content:
                logger.info(f"Website scraped successfully: {attempt_url}")
                return content

        except Exception as e:
            logger.warning(f"Could not fetch {attempt_url}: {e}")
            continue

    return None


def _build_prompt_from_website(website_text: str) -> str:
    return f"""You are an expert recruiting researcher preparing a pre-call brief \
for a finance and accounting recruiter (CPA background) at RYZE.ai.

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


def _build_prompt_from_knowledge(company_name: str, domain: str) -> str:
    return f"""You are an expert recruiting researcher preparing a pre-call brief \
for a finance and accounting recruiter (CPA background) at RYZE.ai.

The employer's website could not be scraped. Use your training knowledge about \
"{company_name}" (website: {domain}) to generate the brief.

If you are confident you know this company, return a thorough brief based on what \
you know. If the company is too small or obscure to know reliably, still return \
your best estimate based on the domain and name — make it useful.

Return ONLY a valid JSON object. No preamble, no explanation, no markdown fences.

Required format:
{{
  "company_overview": "2-3 sentence description of what the company does and who they serve",
  "industry": "specific industry classification",
  "estimated_size": "headcount or revenue signals, e.g. 50-100 employees",
  "hiring_needs": ["role 1", "role 2", "role 3"],
  "talking_points": ["point 1", "point 2", "point 3"],
  "red_flags": "any concerns or considerations, or null if none"
}}"""


def _call_claude(prompt: str, website_url: str) -> dict:
    """Send a prompt to Claude and parse the JSON response. Returns {} on failure."""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown fences Claude occasionally wraps JSON in
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"^```\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        result = json.loads(raw)
        logger.info(f"AI brief parsed successfully for {website_url}")
        return result

    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse AI brief JSON for {website_url}: {e}\nRaw: {raw[:200]}"
        )
        return {"ai_brief_raw": raw}
    except Exception as e:
        logger.error(f"Claude API call failed for {website_url}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pre_call_brief(website_url: str) -> dict:
    """
    Generate a structured pre-call brief for an employer.

    Attempt 1: Scrape the website → send content to Claude.
    Attempt 2: If scraping fails → ask Claude using company name + domain from training knowledge.

    Returns {} on total failure — never raises.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI brief generation.")
        return {}

    # Normalize URL for display
    raw_url = website_url.strip()
    domain = (
        raw_url.replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
    )

    # Attempt 1: scrape the website
    website_text = _fetch_website_text(raw_url)

    if website_text:
        logger.info(f"Generating brief from scraped content: {raw_url}")
        prompt = _build_prompt_from_website(website_text)
        result = _call_claude(prompt, raw_url)
        if result:
            return result

    # Attempt 2: fall back to Claude's training knowledge
    logger.info(
        f"Website scrape failed for {raw_url} — falling back to Claude knowledge for domain: {domain}"
    )

    # Try to extract a readable company name from the domain
    company_name = domain.split(".")[0].replace("-", " ").replace("_", " ").title()
    prompt = _build_prompt_from_knowledge(company_name, domain)
    result = _call_claude(prompt, raw_url)

    if result:
        logger.info(f"Brief generated from Claude knowledge fallback for: {domain}")
        return result

    logger.error(f"All brief generation attempts failed for {raw_url}")
    return {}
