# app/api/employer_pdf_template.py
import html
import json
import re

from playwright.sync_api import sync_playwright

# ─────────────────────────────────────────────────────────────────────────────
# CSS — {banner_style} is the only runtime format argument.
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

.banner-strip {{
    height: 140px;
    background: {banner_style};
    background-size: cover;
    background-position: center;
    flex-shrink: 0;
    display: block;
}}

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

/* Rounded square logo — employer style */
.logo-wrap {{
    width: 80px;
    height: 80px;
    border-radius: 12px;
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

.logo-wrap img {{
    width: 80px;
    height: 80px;
    object-fit: cover;
    display: block;
}}

.identity-left {{
    display: flex;
    align-items: flex-end;
    gap: 12px;
    min-width: 0;
}}

.identity-name {{
    font-size: 20px;
    font-weight: 800;
    color: #0f2444;
    letter-spacing: -0.3px;
    padding-bottom: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.meta-row {{
    padding: 8px 36px 14px 28px;
    border-bottom: 3px solid transparent;
    border-image: linear-gradient(to right, #1e3a5f, #2563eb, #1e3a5f) 1;
    background: #ffffff;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}}

.meta-chip {{
    font-size: 9px;
    font-weight: 600;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    color: #334155;
    border-radius: 20px;
    padding: 3px 10px;
}}

.rel-chip {{
    font-size: 9px;
    font-weight: 700;
    border-radius: 20px;
    padding: 3px 10px;
}}

.body {{
    flex: 1;
    display: flex;
    gap: 18px;
    padding: 20px 28px;
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

.body-text {{
    font-size: 9.5px;
    color: #334155;
    line-height: 1.72;
    white-space: pre-wrap;
    word-break: break-word;
}}

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

.footer-date {{
    font-size: 8px;
    color: rgba(255,255,255,0.55);
}}
"""

PDF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>{style}</style>
</head>
<body>

<div class="banner-strip"></div>

<div class="identity-zone">
  <div class="identity-left">
    <div class="logo-wrap">{logo_tag}</div>
    <div class="identity-name">{company_name}</div>
  </div>
</div>

<div class="meta-row">
  {meta_chips}
</div>

<div class="body">
  <div class="main-col">
    {overview_section}
    {hiring_needs_section}
    {talking_points_section}
  </div>
  <div class="side-col">
    {contact_section}
    {details_section}
  </div>
</div>

<div class="footer">
  <div class="footer-left">
    <span class="footer-brand">{footer_brand}</span>
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


def pdf_card(title: str, inner: str) -> str:
    if not inner.strip():
        return ""
    return (
        f'<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-body">{inner}</div>'
        f"</div>"
    )


def pdf_info_row(label: str, value: str) -> str:
    return (
        f'<div class="info-row">'
        f'<span class="info-label">{label}</span>'
        f'<span class="info-value">{value}</span>'
        f"</div>"
    )


def pdf_parse_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def pdf_bullets_from_list(items: list) -> str:
    if not items:
        return ""
    li = "".join(f"<li>{pdf_e(i)}</li>" for i in items)
    return f'<ul class="bullet-list">{li}</ul>'
