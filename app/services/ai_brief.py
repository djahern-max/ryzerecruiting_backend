# app/services/ai_brief.py
import logging
import httpx
import anthropic
from bs4 import BeautifulSoup
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8000  # Keep well within Claude's context


def _fetch_website_text(url: str) -> str:
    """Fetch a URL and return cleaned readable text, stripping all HTML."""
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

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header", "meta", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Collapse excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:MAX_CONTENT_CHARS]


def generate_pre_call_brief(website_url: str) -> str:
    """
    Fetch an employer's website and use Claude to generate a structured
    pre-call recruiting brief. Returns plain text. Never raises — on any
    failure an empty string is returned and the error is logged.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI brief generation.")
        return ""

    try:
        website_text = _fetch_website_text(website_url)
    except Exception as e:
        logger.error(f"Failed to fetch website {website_url}: {e}")
        return ""

    if not website_text:
        logger.warning(f"No readable content extracted from {website_url}")
        return ""

    prompt = f"""You are an expert recruiting researcher preparing a pre-call brief for a \
finance and accounting recruiter (CPA background) at RYZE Recruiting.

Based on the website content below, produce a concise, actionable brief with these sections:

**Company Overview** — 2-3 sentences on what they do and who they serve.
**Industry & Sector** — Specific industry classification.
**Estimated Company Size** — Headcount or revenue signals if visible.
**Likely Finance & Accounting Hiring Needs** — Based on company type, size, and stage, \
what roles are they most likely to need? (e.g. Staff Accountant, Controller, CFO, FP&A)
**Key Talking Points** — 3-4 conversation starters tailored to this company.
**Red Flags / Considerations** — Anything the recruiter should be aware of.

Keep the tone professional and direct. If information is not available for a section, say so briefly.

Website content:
{website_text}"""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Claude API call failed for {website_url}: {e}")
        return ""
