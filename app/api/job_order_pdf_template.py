# app/api/job_order_pdf_template.py
"""
Job Order PDF template — matches the visual quality of the Employer Profile PDF.
Banner from linked employer, logo overlapping, two-column body, RYZE footer.
"""

import html
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def pdf_e(text) -> str:
    """HTML-escape a value safely."""
    if text is None:
        return ""
    return html.escape(str(text))


def fmt_salary(min_val, max_val) -> str:
    """Format salary range as $85,000 – $110,000."""
    if not min_val and not max_val:
        return ""
    fmt = lambda n: f"${int(n):,}"
    if min_val and max_val:
        return f"{fmt(min_val)} \u2013 {fmt(max_val)}"
    if min_val:
        return f"{fmt(min_val)}+"
    return f"up to {fmt(max_val)}"


def fmt_hourly(min_val, max_val) -> str:
    """Format hourly range as $25.00/hr – $40.00/hr."""
    if not min_val and not max_val:
        return ""
    fmt = lambda n: f"${float(n):,.2f}/hr"
    if min_val and max_val:
        return f"{fmt(min_val)} \u2013 {fmt(max_val)}"
    if min_val:
        return f"{fmt(min_val)}+"
    return f"up to {fmt(max_val)}"


EMPLOYMENT_TYPE_LABELS = {
    "contract": "Contract",
    "contract_to_hire": "Contract-to-Hire",
    "direct_hire": "Direct Hire",
}


def pdf_card(title: str, body_html: str) -> str:
    """Render a section card with a label header."""
    return f"""
    <div class="card">
        <div class="card-label">{title}</div>
        <div class="card-body">{body_html}</div>
    </div>"""


def pdf_info_row(label: str, value: str) -> str:
    return f"""
    <div class="info-row">
        <span class="info-label">{label}</span>
        <span class="info-value">{value}</span>
    </div>"""


def render_pdf(html_str: str) -> bytes:
    """Render HTML to PDF bytes via Playwright (sync, runs in threadpool)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="Letter",
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            print_background=True,
        )
        browser.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# CSS
# {banner_style} is the only runtime format argument.
# All other {{ }} are escaped literal braces for Python str.format().
# ---------------------------------------------------------------------------

PDF_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@400;500;600;700;800&display=swap');

@page {{
    margin: 0;
    size: 8.5in 11in;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

body {{
    font-family: 'DM Sans', -apple-system, sans-serif;
    background: #f1f5f9;
    color: #1e293b;
    font-size: 13px;
    line-height: 1.6;
    width: 8.5in;
    min-height: 11in;
    display: flex;
    flex-direction: column;
}}

/* ── Banner ── */
.banner {{
    width: 100%;
    height: 140px;
    background: {banner_style};
    background-size: cover;
    background-position: center;
    display: block;
    position: relative;
    flex-shrink: 0;
}}

/* ── Identity Zone ── */
.identity-zone {{
    background: #fff;
    padding: 0 32px 12px;
    margin-top: -42px;
    position: relative;
    z-index: 2;
    display: flex;
    align-items: flex-end;
    gap: 16px;
}}

.identity-left {{
    display: flex;
    align-items: flex-end;
    gap: 14px;
    flex: 1;
    min-width: 0;
}}

.logo-wrap {{
    width: 88px;
    height: 88px;
    border-radius: 12px;
    border: 3px solid #fff;
    background: #f8fafc;
    overflow: hidden;
    flex-shrink: 0;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
}}

.logo-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #fff;
}}

.logo-initial {{
    font-size: 2.2rem;
    font-weight: 800;
    color: #fff;
    background: #1e3a5f;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}}

.identity-info {{
    padding-bottom: 4px;
    min-width: 0;
    flex: 1;
}}

.job-title {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 22px;
    font-weight: 400;
    color: #0f172a;
    line-height: 1.2;
    margin-bottom: 4px;
    word-break: break-word;
}}

.company-name {{
    font-size: 13px;
    font-weight: 600;
    color: #0a66c2;
    margin-bottom: 2px;
}}

/* ── Name block / divider ── */
.name-block {{
    background: #fff;
    padding: 6px 32px 14px;
    border-bottom: 3px solid transparent;
    border-image: linear-gradient(to right, #1e3a5f, #2563eb, #1e3a5f) 1;
}}

/* ── Chips ── */
.chip-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
}}

.chip {{
    display: inline-block;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    color: #475569;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
}}

.chip-open    {{ background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }}
.chip-filled  {{ background: #eff6ff; border-color: #bfdbfe; color: #1e3a5f; }}
.chip-on_hold {{ background: #fff7ed; border-color: #fed7aa; color: #c2410c; }}

/* ── Two-column body ── */
.body {{
    padding: 20px 32px 0;
    display: grid;
    grid-template-columns: 1fr 220px;
    gap: 18px;
    align-items: start;
    background: #f1f5f9;
    flex: 1;
}}

/* ── Cards ── */
.card {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 14px;
}}

.card-label {{
    font-size: 0.65rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #94a3b8;
    padding: 9px 14px 8px;
    border-bottom: 1px solid #f1f5f9;
    background: #f8fafc;
}}

.card-body {{
    padding: 12px 14px;
}}

.body-text {{
    font-size: 13px;
    color: #475569;
    line-height: 1.75;
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
}}

/* ── Recruiter Notes — navy left accent (matches UI) ── */
.notes-card {{
    border-left: 3px solid #1e3a5f;
    background: #f8fafc;
}}

.notes-box {{
    font-size: 13px;
    color: #475569;
    line-height: 1.7;
    white-space: pre-wrap;
}}

/* ── About employer ── */
.about-box {{
    font-size: 13px;
    color: #475569;
    line-height: 1.75;
}}

/* ── Sidebar info rows ── */
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
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94a3b8;
    flex-shrink: 0;
    width: 60px;
    padding-top: 1px;
}}

.info-value {{
    font-size: 12.5px;
    color: #1e293b;
    font-weight: 500;
    word-break: break-word;
}}

/* ── Footer ── */
.footer {{
    background: #0f2444;
    padding: 10px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 20px;
    flex-shrink: 0;
}}

.footer-brand {{
    font-size: 10px;
    font-weight: 800;
    color: #fff;
    letter-spacing: 0.2em;
    text-transform: uppercase;
}}

.footer-date {{
    font-size: 10px;
    color: rgba(255, 255, 255, 0.5);
}}
"""


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

PDF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>{style}</style>
</head>
<body>

<!-- Banner -->
<div class="banner"></div>

<!-- Identity Zone -->
<div class="identity-zone">
    <div class="identity-left">
        <div class="logo-wrap">
            {logo_tag}
        </div>
        <div class="identity-info">
            {company_name_tag}
            <div class="job-title">{job_title}</div>
        </div>
    </div>
</div>

<!-- Chips row -->
<div class="name-block">
    <div class="chip-row">
        {chips}
    </div>
</div>

<!-- Two-column body -->
<div class="body">

    <!-- Main column -->
    <div class="main-col">
        {requirements_section}
        {notes_section}
        {about_section}
    </div>

    <!-- Side column -->
    <div class="side-col">
        {details_section}
    </div>

</div>

<!-- Footer -->
<div class="footer">
    <div>
        <span class="footer-brand">{footer_brand}</span>
    </div>
    <div class="footer-date">Generated {today}</div>
</div>

</body>
</html>"""
