# app/api/job_order_pdf_template.py
import html

from playwright.sync_api import sync_playwright

PDF_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');

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
    background: #ffffff;
    width: 8.5in;
    min-height: 11in;
    display: flex;
    flex-direction: column;
}}

.header {{
    background: #0f2444;
    padding: 24px 36px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.header-brand {{
    font-size: 14px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}}

.header-logo {{
    width: 52px;
    height: 52px;
    border-radius: 8px;
    object-fit: cover;
    background: #1c3f6e;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 800;
    color: #fff;
    overflow: hidden;
}}

.header-logo img {{
    width: 52px;
    height: 52px;
    object-fit: cover;
    border-radius: 8px;
}}

.title-block {{
    padding: 28px 36px 20px;
    border-bottom: 3px solid transparent;
    border-image: linear-gradient(to right, #1e3a5f, #2563eb, #1e3a5f) 1;
    background: #f8fafc;
}}

.job-title {{
    font-size: 24px;
    font-weight: 800;
    color: #0f2444;
    letter-spacing: -0.3px;
    margin-bottom: 6px;
}}

.job-meta {{
    font-size: 11px;
    color: #475569;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
}}

.meta-sep {{ color: #cbd5e1; }}

.status-badge {{
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid;
    text-transform: capitalize;
}}

.status-open   {{ background: #f0fdf4; color: #15803d; border-color: #bbf7d0; }}
.status-filled {{ background: #f8fafc; color: #64748b; border-color: #e2e8f0; }}
.status-on_hold {{ background: #fff7ed; color: #c2410c; border-color: #fed7aa; }}

.body {{
    flex: 1;
    padding: 24px 36px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    background: #ffffff;
}}

.divider {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 0;
}}

.section-label {{
    font-size: 8px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #94a3b8;
    margin-bottom: 10px;
}}

.section-text {{
    font-size: 10px;
    color: #334155;
    line-height: 1.75;
    white-space: pre-wrap;
    word-break: break-word;
}}

.notes-box {{
    background: #f8fafc;
    border-left: 3px solid #3b82f6;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 9.5px;
    color: #334155;
    line-height: 1.7;
    white-space: pre-wrap;
}}

.about-box {{
    background: #f0f9ff;
    border-left: 3px solid #1e3a5f;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 9.5px;
    color: #1e293b;
    line-height: 1.7;
}}

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
    background: rgba(255,255,255,0.3);
    margin: 0 10px;
}}

.footer-url {{
    font-size: 8px;
    color: rgba(255,255,255,0.55);
}}

.footer-date {{
    font-size: 8px;
    color: rgba(255,255,255,0.55);
}}
"""

PDF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<style>{style}</style>
</head>
<body>

<div class="header">
  <div class="header-brand">RYZE.ai</div>
  <div class="header-logo">{logo_tag}</div>
</div>

<div class="title-block">
  <div class="job-title">{job_title}</div>
  <div class="job-meta">
    <span>{company_name}</span>
    {location_part}
    {salary_part}
  </div>
  <span class="status-badge status-{status}">{status_label}</span>
</div>

<div class="body">

  <div>
    <div class="section-label">Requirements</div>
    <div class="section-text">{requirements}</div>
  </div>

  {notes_block}

  <hr class="divider"/>

  {about_block}

</div>

<div class="footer">
  <div class="footer-left">
    <span class="footer-brand">RYZE.ai</span>
    <span class="footer-sep"></span>
    <span class="footer-url">ryze.ai</span>
  </div>
  <div class="footer-date">Generated {today}</div>
</div>

</body>
</html>"""


def render_pdf(html_string: str) -> bytes:
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


def pdf_e(value) -> str:
    return html.escape(str(value or ""))


def fmt_salary(min_val, max_val) -> str:
    if min_val and max_val:
        return f"${min_val:,} – ${max_val:,}"
    if min_val:
        return f"From ${min_val:,}"
    return ""
