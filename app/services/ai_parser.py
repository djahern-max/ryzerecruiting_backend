# app/services/ai_parser.py
import json
import logging
import anthropic
from app.core.config import settings

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _call_claude(prompt: str, text: str) -> dict:
    """
    Core Claude parsing call. Returns parsed dict or empty dict on failure.
    """
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": f"{prompt}\n\n---\n\n{text}"}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Claude parsing failed: {e}")
        return {}


def parse_candidate_profile(text: str) -> dict:
    prompt = """You are an expert recruiter reviewing a candidate profile or resume.
Extract the following information and return ONLY valid JSON with no preamble or markdown.

Required JSON keys:
- name (string or null)
- current_title (string or null)
- current_company (string or null)
- location (string or null)
- email (string or null)
- phone (string or null)
- linkedin_url (string or null)
- ai_summary (string — 2-3 sentences from a recruiter's perspective describing this candidate's background, experience level, and strongest attributes. Be specific.)
- ai_career_level (string — one of: "junior", "mid", "senior", "executive" based on years and title)
- ai_experience (string — narrative summary of work history: companies, titles, tenure, progression. Include dates if present.)
- ai_education (string — degrees, schools, graduation years, fields of study)
- ai_certifications (string or null — professional certifications like CPA, CFA, CMA, PMP, etc. Comma separated.)
- ai_skills (array of strings — technical and professional skills mentioned)
- ai_years_experience (integer or null — estimated total years of professional experience)

Rules:
- Return ONLY the JSON object, nothing else
- If a field cannot be determined, return null
- ai_skills must be an array even if empty
- ai_years_experience should be an integer estimate based on career history
- For ai_career_level: junior = 0-3 years, mid = 3-7 years, senior = 7-15 years, executive = 15+ years or C-suite/VP/Director titles
- Be thorough with ai_experience — this is the most valuable field for recruiting purposes"""

    return _call_claude(prompt, text)


def parse_job_description(text: str) -> dict:
    """
    Parse a job description or job posting into structured job order fields.
    """
    prompt = """You are an expert recruiter reviewing a job description or job posting.
    Extract the following information and return ONLY valid JSON with no preamble or markdown.

    Required JSON keys:
    - title (string or null) — the job title
    - location (string or null) — city, state, remote status
    - salary_min (integer or null) — annual minimum salary as integer, no symbols or commas
    - salary_max (integer or null) — annual maximum salary as integer, no symbols or commas
    - requirements (string or null) — key requirements and qualifications as a concise summary
    - company_name (string or null) — hiring company name if present
    - notes (string or null) — any other relevant details worth capturing

    Rules:
    - Return ONLY the JSON object, nothing else
    - salary_min and salary_max must be integers (e.g. 150000 not "$150,000")
    - If salary is not mentioned return null for both salary fields
    - If a field cannot be determined return null"""

    return _call_claude(prompt, text)


def parse_employer_prospect(text: str) -> dict:
    """
    Parse a job posting, LinkedIn company page, or any employer content
    into structured employer profile + prospecting intelligence.
    """
    prompt = """You are an expert recruiter analyzing a company or job posting for prospecting purposes.
Extract the following information and return ONLY valid JSON with no preamble or markdown.

Required JSON keys:
- company_name (string or null)
- industry (string or null)
- location (string or null) — company headquarters or job location
- company_size (string or null) — estimated employee count or size range
- website_url (string or null) — company website if mentioned
- hiring_role (string or null) — the specific role they are hiring for if present
- ai_company_overview (string or null) — 2-3 sentences describing what this company does
- ai_hiring_needs (array of strings) — list of inferred hiring needs based on the content
- ai_talking_points (array of strings) — 3-5 specific talking points a recruiter should use when reaching out to this company
- ai_red_flags (string or null) — any concerns or red flags worth noting

Rules:
- Return ONLY the JSON object, nothing else
- ai_hiring_needs and ai_talking_points must be arrays even if empty
- Be specific in talking points — reference actual details from the text
- If a field cannot be determined return null"""

    return _call_claude(prompt, text)
