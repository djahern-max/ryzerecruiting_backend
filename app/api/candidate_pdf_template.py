# app/api/candidate_pdf_template.py
"""
HTML/CSS template strings and pure helper functions for candidate PDF generation.

Keeping these out of candidates.py prevents that route file from bloating to
500+ lines. The PDF route (download_candidate_pdf) stays in candidates.py
because it owns the DB query, tenant check, and StreamingResponse — this file
owns everything below that: the rendering engine and the template itself.

Import pattern in candidates.py:
    from app.api.candidate_pdf_template import (
        PDF_STYLE, PDF_HTML, render_pdf,
        pdf_card, pdf_info_row, pdf_badge,
        pdf_e, pdf_clean_text, pdf_parse_skills, pdf_parse_to_bullets,
    )
"""

import html
import json
import re

from playwright.sync_api import sync_playwright

# ─────────────────────────────────────────────────────────────────────────────
# CSS — {banner_style} is the only runtime format argument.
#        All other {{ }} are escaped literal braces for the CSS itself.
# ─────────────────────────────────────────────────────────────────────────────

PDF_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=DM+Serif+Display&display=swap');

@page {{
    margin: 0;
    size: 8.5in 11in;
}}

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

body {{
    font-family: 'DM Sans', Arial, Helvetica, sans-serif;
    font-size: 10px;
    color: #1e293b;
    background: #f1f5f9;
    width: 8.5in;
    display: flex;
    flex-direction: column;
    min-height: 11in;
}}

/* ─── BANNER STRIP (pure visual — mirrors UI) ─── */
.banner-strip {{
    height: 140px;
    background: {banner_style};
    background-size: cover;
    background-position: center;
    flex-shrink: 0;
    display: block;
}}

/* ─── IDENTITY ZONE (avatar overlaps banner seam, mirrors .identityRow) ─── */
.identity-zone {{
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    padding: 0 36px 0 28px;
    margin-top: -42px;
    margin-bottom: 0;
    position: relative;
    z-index: 2;
}}

/* mirrors .avatarImg / .avatarInitial */
.avatar {{
    width: 80px;
    height: 80px;
    border-radius: 50%;
    border: 4px solid #ffffff;
    box-shadow: 0 2px 10px rgba(0,0,0,0.18);
    overflow: hidden;
    flex-shrink: 0;
    background: #1c3f6e;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    font-weight: 800;
    color: #fff;
    letter-spacing: -1px;
}}

.avatar img {{
    width: 80px;
    height: 80px;
    object-fit: cover;
    object-position: center top;
    display: block;
    border-radius: 50%;
}}

.identity-left {{
    display: flex;
    align-items: flex-end;
    gap: 12px;
    min-width: 0;
}}

.identity-name {{
    font-size: 16px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: -0.2px;
    padding-bottom: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* ─── NAME BLOCK (mirrors .nameBlock) ─── */
.name-block {{
    padding: 8px 36px 14px 28px;
    border-bottom: 3px solid transparent;
    border-image: linear-gradient(to right, #1e3a5f, #2563eb, #1e3a5f) 1;
    background: #ffffff;
}}

/* mirrors .name */
.candidate-name {{
    font-size: 22px;
    font-weight: 800;
    color: #0f2444;
    letter-spacing: -0.3px;
    line-height: 1.15;
    margin-bottom: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

/* mirrors .headline */
.candidate-meta {{
    font-size: 11px;
    color: #475569;
    font-weight: 500;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}}

.meta-divider {{
    color: #94a3b8;
    font-style: italic;
    font-size: 10px;
}}

/* mirrors .locationLine */
.candidate-location {{
    font-size: 10px;
    color: #0a66c2;
    margin-bottom: 8px;
    font-weight: 500;
}}

/* mirrors .badgeRow */
.badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 6px;
}}

.badge {{
    font-size: 9px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 20px;
    border: 1px solid;
    letter-spacing: 0.04em;
    text-transform: capitalize;
    white-space: nowrap;
}}

/* mirrors CAREER_LEVEL_COLORS */
.badge-exec  {{ background: #0f172a;  color: #f8fafc; border-color: #1e293b; }}
.badge-level {{ background: #eff6ff;  color: #1d4ed8; border-color: #bfdbfe; }}
.badge-exp   {{ background: #f0fdf4;  color: #15803d; border-color: #bbf7d0; }}
.badge-cert  {{ background: #1d4ed8;  color: #ffffff; border-color: #3b82f6; }}

/* ─── BODY — mirrors .profileBodyInner ─── */
.body {{
    flex: 1;
    display: flex;
    gap: 18px;
    padding: 20px 28px 20px 28px;
    align-items: flex-start;
    background: #f1f5f9;
}}

.main-col {{
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 13px;
}}

.side-col {{
    width: 245px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 13px;
}}

/* ─── SECTION CARD — mirrors .section ─── */
.card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    page-break-inside: avoid;
}}

.card-title {{
    font-size: 8px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #94a3b8;
    padding: 10px 16px 9px;
    border-bottom: 1px solid #f1f5f9;
    background: #f8fafc;
}}

.card-body {{
    padding: 13px 16px;
}}

/* mirrors .summaryText */
.summary-text {{
    font-size: 10px;
    color: #334155;
    line-height: 1.72;
    white-space: pre-wrap;
    word-break: break-word;
}}

/* mirrors .bodyText */
.body-text {{
    font-size: 9.5px;
    color: #334155;
    line-height: 1.75;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.35;
}}

/* mirrors .bulletList / .bulletItem */
.bullet-list {{
    margin: 0;
    padding: 0 0 0 16px;
    display: flex;
    flex-direction: column;
    gap: 7px;
}}

.bullet-list li {{
    font-size: 9.5px;
    color: #334155;
    line-height: 1.55;
    padding-left: 4px;
}}

/* ─── SKILLS — mirrors .skillTag ─── */
.skills-wrap {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}}

.skill-tag {{
    font-size: 9px;
    font-weight: 500;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    color: #334155;
    border-radius: 6px;
    padding: 3px 8px;
}}

/* ─── CERT BADGES — mirrors .certBadge ─── */
.cert-badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
}}

.cert-badge {{
    font-size: 9px;
    font-weight: 700;
    border-radius: 20px;
    background: #1d4ed8;
    border: 1px solid #3b82f6;
    color: #ffffff;
    padding: 3px 10px;
}}

/* ─── INFO ROWS — mirrors .infoRow / .infoLabel / .infoValue ─── */
.info-list {{
    display: flex;
    flex-direction: column;
    gap: 9px;
}}

.info-row {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
}}

.info-label {{
    font-size: 8px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #94a3b8;
    flex-shrink: 0;
    width: 66px;
    padding-top: 1px;
}}

.info-value {{
    font-size: 9.5px;
    color: #1e293b;
    word-break: break-word;
    line-height: 1.35;
}}

/* ─── FOOTER ─── */
.footer {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 2px solid #1e3a5f;
    background: #0f2444;
    padding: 9px 36px;
    flex-shrink: 0;
}}

.footer-left {{
    display: flex;
    align-items: center;
}}

.footer-brand {{
    font-size: 9px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.2em;
    text-transform: uppercase;
}}

.footer-sep {{
    display: inline-block;
    width: 1px;
    height: 10px;
    background: rgba(255, 255, 255, 0.3);
    margin: 0 10px;
}}

.footer-tagline {{
    font-size: 8px;
    color: rgba(255, 255, 255, 0.55);
}}

.footer-date {{
    font-size: 8px;
    color: rgba(255, 255, 255, 0.55);
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML template — named {placeholders} are filled by str.format() in the route
# ─────────────────────────────────────────────────────────────────────────────

PDF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>{style}</style>
</head>
<body>

<!-- BANNER (pure visual, mirrors UI) -->
<div class="banner-strip"></div>

<!-- IDENTITY ZONE: avatar overlaps the banner/white seam -->
<div class="identity-zone">
  <div class="identity-left">
    <div class="avatar">{photo_tag}</div>
    <div class="identity-name">{name}</div>
  </div>
</div>

<!--
<div class="name-block">
  <div class="candidate-name">{name}</div>
  {meta_line}
  {location_line}
  <div class="badges">{badges}</div>
</div>
-->

<!-- BODY: two-column, mirrors .profileBodyInner -->
<div class="body">

  <div class="main-col">
    {summary_section}
    {experience_section}
    {education_section}
  </div>

  <div class="side-col">
    {contact_section}
    {skills_section}
    {certs_section}
    {details_section}
  </div>

</div>

<!-- FOOTER -->
<div class="footer">
  <div class="footer-left">
    <span class="footer-brand">{footer_brand}</span>
    <span class="footer-sep"></span>
    <span class="footer-tagline">{footer_tagline}</span>
  </div>
  <div class="footer-date">Generated {today}</div>
</div>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Rendering engine
# ─────────────────────────────────────────────────────────────────────────────


def render_pdf(html_string: str) -> bytes:
    """Render an HTML string to PDF bytes via headless Playwright/Chromium."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_string, wait_until="networkidle")
        pdf = page.pdf(
            format="Letter",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    return pdf


# ─────────────────────────────────────────────────────────────────────────────
# Pure HTML helpers (no DB / no state)
# ─────────────────────────────────────────────────────────────────────────────


def pdf_card(title: str, inner: str) -> str:
    """Render a section card div — mirrors .section > .sectionTitle + .sectionBody."""
    if not inner.strip():
        return ""
    return (
        f'<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-body">{inner}</div>'
        f"</div>"
    )


def pdf_info_row(label: str, value: str) -> str:
    """Render a label/value row — mirrors .infoRow."""
    return (
        f'<div class="info-row">'
        f'<span class="info-label">{label}</span>'
        f'<span class="info-value">{value}</span>'
        f"</div>"
    )


def pdf_badge(cls: str, text: str) -> str:
    """Render a pill badge."""
    return f'<span class="badge {cls}">{text}</span>'


def pdf_e(value) -> str:
    """HTML-escape a value safely."""
    return html.escape(str(value or ""))


def pdf_clean_text(value, max_chars: int = 900) -> str:
    """Collapse whitespace, truncate, and HTML-escape."""
    t = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(t) <= max_chars:
        return pdf_e(t)
    return pdf_e(t[:max_chars].rstrip() + "…")


def pdf_parse_skills(value) -> list:
    """Return a list of skill strings from various storage formats, capped at 14."""
    if not value:
        return []
    if isinstance(value, list):
        return value[:14]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed[:14]
        except Exception:
            return [s.strip() for s in value.split(",") if s.strip()][:14]
    return []


_STRIP_PREFIXES = (
    "He then ",
    "He also ",
    "He currently ",
    "He is currently ",
    "She then ",
    "She also ",
    "She currently ",
    "She is currently ",
    "They then ",
    "They also ",
    "They currently ",
    "He ",
    "She ",
    "They ",
    "Concurrently, he ",
    "Concurrently, she ",
    "Concurrently, they ",
)


def pdf_parse_to_bullets(text: str, max_items: int = 6) -> str:
    """
    Converts AI prose experience/education text into an HTML bullet list.
    Strips redundant subject pronouns and skips the generic opening sentence.
    Returns an empty string if text is falsy.
    """
    if not text:
        return ""
    raw = str(text).strip()

    sentences = re.split(r"(?<=\.)\s+(?=[A-Z])", raw)

    bullets = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        # Skip generic intro like "John Smith has an extensive career..."
        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+ has (an|a) ", s):
            continue
        # Strip subject pronouns and recapitalise
        for prefix in _STRIP_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix) :]
                s = s[0].upper() + s[1:]
                break
        bullets.append(s)

    bullets = bullets[:max_items]
    if not bullets:
        return f'<p class="body-text">{pdf_e(raw)}</p>'
    items = "".join(f"<li>{pdf_e(b)}</li>" for b in bullets)
    return f'<ul class="bullet-list">{items}</ul>'
