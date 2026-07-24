# Current Feature

<!-- Feature/fix name -->
PDF banners — intrinsic-aspect rendering (replace fixed-height `cover` cropping)

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
Successor to the "banner render parity" task (see CHANGELOG). That task proved
empirically that no fixed height + `background-size: cover` can show a banner
image intact: at 8.5in page width, 140px crops the image vertically (bottom
photo strip trimmed) and any taller height (180px, 220px both tested) flips
`cover` to height-driven scaling and crops the sides (banner script cut off).

Goal: banner images in the PDF exports render at the page's full width at
their **natural aspect ratio** — no horizontal crop, no vertical crop — with
the banner's rendered height derived from the image instead of a hardcoded
pixel value. For the Greenscene test image this means a banner taller than
140px showing the complete composition (script + full photo strip).

**Approach — audit first, do NOT write code yet:**
1. Read the `.banner` block + `banner_style` construction in
   `app/api/job_order_pdf_template.py` / `app/api/job_orders.py`, and
   `.banner-strip` + its construction in `app/api/employer_pdf_template.py`
   / the employer PDF route. Also check `candidate_pdf_template.py` — does it
   share the same fixed-height `cover` pattern? Report.
2. Determine how the identity-zone overlap (`margin-top: -42px`) interacts
   with a variable-height banner — confirm the overlap works off the banner's
   *bottom edge* regardless of banner height (it should, since the identity
   zone follows the banner in flow).
3. Propose implementation per the strategy below, including exact max-height
   cap value and fallback treatment, mapped to numbered edit sites. Wait for
   confirmation before writing code.

**Rendering strategy (proposed — audit may refine):**
Replace the CSS `background-image` banner div with a real `<img>` element:

```html
<div class="banner-frame">{banner_img_tag}</div>
```
```css
.banner-frame {
    width: 100%;
    max-height: 240px;        /* cap — confirm value in plan */
    overflow: hidden;
    background: linear-gradient(...);  /* fallback fill / letterbox bed */
    flex-shrink: 0;
}
.banner-frame img {
    width: 100%;
    height: auto;             /* intrinsic aspect — width-driven, never side-crops */
    display: block;
}
```

Behavior by image shape:
- Wide/short image (typical banner): renders full width at natural height,
  fully intact. This is the primary win.
- Tall/square image: renders full width; `max-height` + `overflow: hidden`
  crops the *bottom* only — sides are never cut. Acceptable degradation.
- No employer / no banner uploaded: `{banner_img_tag}` is empty; the frame
  renders the existing gradient at a fixed fallback height (e.g. 140px via
  `min-height` on the empty state — propose exact mechanism in plan).

**Numbered edit sites:**
1. `app/api/job_order_pdf_template.py` — `.banner` CSS → `.banner-frame`
   pattern; `PDF_HTML` banner div → `{banner_img_tag}` placeholder
2. `app/api/job_orders.py` (PDF route) — build `banner_img_tag`
   (`<img src="...">` when `employer.banner_url` exists, else empty string);
   keep/adapt the gradient fallback
3. `app/api/employer_pdf_template.py` + employer PDF route — same treatment,
   so the two exports stay on one rendering strategy (do NOT let them diverge
   again)
4. `app/api/candidate_pdf_template.py` + route — same treatment IF the audit
   confirms it shares the pattern; otherwise flag and leave for a follow-up

**Constraints:**
- `PDF_STYLE` brace-escaping conventions preserved; new placeholders go in
  `PDF_HTML` only unless the plan explicitly justifies otherwise.
- Tenant footer branding (just completed) must be untouched — regression
  check it renders identically.
- The `<img>` must load before Playwright snapshots the page —
  `wait_until="networkidle"` should cover it, but confirm; if flaky, propose
  the fix (e.g. explicit wait) in the plan rather than shipping a race.
- No schema changes, no migration. Focal-point / aspect-ratio-at-upload
  ideas remain out of scope — this task is render-side only.
- One template per commit (job order, employer, candidate-if-included).

## Related Files
- `app/api/job_order_pdf_template.py`, `app/api/job_orders.py`
- `app/api/employer_pdf_template.py` + employer PDF route
- `app/api/candidate_pdf_template.py` + `app/api/candidates.py` (audit; include
  only if pattern matches)
- Read-only reference: `context/CHANGELOG.md` (parity task history — 140/180/220
  evidence)

**Explicitly out of scope:**
- Web UI banner rendering (CSS Modules pages) — PDFs only
- Banner upload validation / aspect enforcement / focal-point field
- Tenant-derivation helper normalization (still flagged, still parked)

## Verification
1. Greenscene job order PDF: full banner composition visible — script intact
   left to right, photo strip intact top to bottom, banner taller than the
   old 140px.
2. Greenscene employer profile PDF: same image, same rendering — the two
   exports match by construction.
3. Job order with no linked employer / no banner: gradient fallback renders
   cleanly at fallback height; no broken-image icon, no zero-height collapse.
4. Identity zone: logo overlap sits correctly on the banner's bottom edge at
   the new variable height.
5. Footer branding unchanged (tenant brand for firm tenants, RYZE.AI for
   `ryze`).
6. Body content still fits one page for typical job orders — a taller banner
   must not push the footer to page 2 (check the flex column behavior).
7. `.format()` raises no KeyError; PDF streams as before.

## Notes
- Rationale for `<img>` over `background-size: 100% auto`: identical scaling
  behavior, but a real element gives the document intrinsic height (no
  hardcoded guess needed), participates in networkidle waiting, and makes the
  empty-state branch explicit rather than a CSS-shorthand edge case.
- The `max-height` cap is the only remaining "magic number," and it's a
  ceiling, not a target — most banner images will never hit it. Propose the
  value with reasoning (page-budget math: banner + identity + body + footer
  ≤ 11in for a typical job order).
- Deploy commands handed to the user, not executed. No service stop needed —
  template-only.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-24 — Task created as the structural successor to the banner parity
  task. Evidence base: 140px crops this image's bottom, 180px and 220px crop
  its sides; `cover` at fixed height provably cannot render the full
  composition. Strategy: width-driven intrinsic-aspect `<img>` with
  max-height cap and gradient fallback, applied uniformly across PDF
  templates.
- 2026-07-24 — Audit-first step completed (no code written). Confirmed CSS
  structure identical across all three templates (140px height,
  background-size:cover, background-position:center, flex-shrink:0) —
  candidate's `.banner-strip` is byte-identical to employer's, confirming it
  shares the fixed-height cover pattern and belongs in this task. Confirmed
  `candidate.banner_url` is a genuine per-candidate column (no
  employer/company join anywhere in `download_candidate_pdf`), not a shared
  or derived value. Found candidate's fallback gradient is a distinct 3-stop
  navy (`#0f2444`/`#1a3a6b`/`#1e4a8a`) vs job order/employer's 2-stop
  (`#1e3a5f`/`#2563eb`) — never unified by the prior parity task; user
  confirmed preserve as-is, no color unification. Found candidate's
  non-fallback `banner_style` omits `center/cover no-repeat` (harmless today;
  moot after this change since the CSS `background: url(...)` approach is
  replaced by a real `<img>`). Confirmed the `.identity-zone`
  `margin-top: -42px` overlap is flow-relative and anchors to the banner's
  actual bottom edge regardless of banner height — no CSS change needed
  there. Confirmed `wait_until="networkidle"` is sufficient for the new
  banner `<img>` — all three routes already load remote-CDN `<img>` tags
  (`logo_tag`/`photo_tag`) under the same wait today; no new race. Flagged,
  not fixed: candidate's `photo_tag` src is not passed through `pdf_e()`
  (unescaped), unlike `logo_tag` in the other two templates — pre-existing,
  out of scope, flag-only per user decision.
- 2026-07-24 — Plan finalized and confirmed by user, with two amendments to
  the original spec:
  1. **`PDF_STYLE.format()` stays, with zero kwargs**, in all three routes —
     the escaped `{{ }}` braces throughout the CSS only render correctly
     through `.format()`; converting `PDF_STYLE` to a plain string would
     leave every escaped brace un-collapsed. Each template's header comment
     (`"{banner_style} is the only runtime format argument"`) is stale as of
     this change and gets corrected in the same commit that removes the
     format arg.
  2. **Commit 3's one-page verification must use a dense candidate record**
     (full experience + education + skills + certs sections populated), not
     a sparse one — the 240px page-budget math below was computed against
     the job order layout only, not independently verified against the
     candidate template's own (denser) chrome. If a dense candidate spills
     to page 2 at the cap, stop and flag before adjusting the cap or
     anything else.

  Decisions locked in: **240px max-height cap**, approved as a ceiling, not
  a target (page-budget math: job order's fixed chrome outside the banner —
  identity-zone net overlap ~58px, name-block/chip-row ~44px, body top
  padding 20px, footer ~54px — totals ~176px; at today's 140px banner that's
  316px consumed, leaving ~740px for body content, already confirmed to fit
  one page by the prior parity task; at 240px that drops to ~640px, still
  generous since most real banner images will render well under the cap).
  **Commit 3 (candidate) confirmed in scope.** **Per-template fallback
  gradients preserved** — no color unification across templates. **Two-state
  fallback mechanism approved**: `.banner-frame` (real `<img>`, max-height +
  `overflow: hidden`) vs a separate `.banner-empty` (fixed 140px, the
  template's own existing gradient), branched in the route by
  `banner_url`/`photo_url`/`banner_url` presence — this replaces the
  original spec's single-div-plus-`min-height` pseudocode, which had a real
  bug: an empty div with only `max-height` set and no `<img>` child collapses
  to zero height and never paints the gradient. Proceeding with Commit 1
  (job order).
- 2026-07-24 — Commit 1 implemented (job order). `job_order_pdf_template.py`:
  `.banner` replaced with `.banner-frame` (width 100%, `max-height: 240px`,
  `overflow: hidden`) + `.banner-frame img` (width 100%, `height: auto`) +
  `.banner-empty` (fixed 140px, the existing 2-stop gradient); `PDF_HTML`'s
  `<div class="banner"></div>` replaced with the `{banner_html}` placeholder;
  header comment corrected to note `PDF_STYLE.format()` now takes zero
  kwargs. `job_orders.py`: `banner_style` construction replaced with the
  two-branch `banner_html` builder (real `<img src="{employer.banner_url}">`
  wrapped in `.banner-frame`, or `.banner-frame.banner-empty` alone);
  `PDF_STYLE.format(banner_style=banner_style)` → `PDF_STYLE.format()` per
  the confirmed amendment (kept the `.format()` call, zero kwargs, so the
  escaped `{{ }}` braces still collapse correctly); `PDF_HTML.format(...)`
  gained `banner_html=banner_html`. App-import clean (98 routes, unchanged).
  `audit_tenant_coverage.py`: same 2 pre-existing unrelated `candidates.py`
  REVIEW lines (`/me/photo`, `/me/banner`), no new REVIEW/HARDCODED.
  Not committed to git yet — awaiting user's deploy + visual check
  (Greenscene job order PDF: full banner composition, no crop; no-banner
  job order: gradient fallback at 140px; identity-zone overlap; footer
  branding unchanged; one-page fit) before commit and before starting
  Commit 2 (employer).
- 2026-07-24 — User deployed/tested and committed Commit 1 (`0431ea0`),
  then instructed to proceed directly through Commits 2 and 3.
- 2026-07-24 — Commit 2 implemented (employer). `employer_pdf_template.py`:
  `.banner-strip` replaced with `.banner-frame` (max-height 240px,
  `overflow: hidden`) + `.banner-frame img` (width 100%, height auto) +
  `.banner-empty` (fixed 140px, same 2-stop gradient as job order — parity
  preserved); `PDF_HTML`'s banner div replaced with `{banner_html}`; header
  comment corrected. `employer_profiles.py`: `banner_style` replaced with
  the same two-branch `banner_html` builder; `PDF_STYLE.format(banner_style=...)`
  → `PDF_STYLE.format()`; `banner_html` added to `PDF_HTML.format()` kwargs.
  App-import clean (98 routes, unchanged). `audit_tenant_coverage.py`: same
  2 pre-existing unrelated `candidates.py` REVIEW lines, no new
  REVIEW/HARDCODED. Not committed to git yet — committing employer and
  candidate as two separate commits (employer first), matching commit 1's
  granularity, before user deploys and runs the visual checklist.
