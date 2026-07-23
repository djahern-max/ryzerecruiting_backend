# Current Feature

Employer Profile PDF — tenant branding + remove Red Flags from export

## Status
Not Started

## Goals
The employer profile PDF is a client-facing marketing artifact (sent to
prospective clients alongside the eventual Job Order), but it currently leaks
two internal things:

- The footer is hardcoded to "RYZE.ai" — the same bug fixed on the candidate
  PDF on 2026-07-15 (see CHANGELOG: "{footer_brand} placeholder fed by
  get_branding(db, tenant_id)"). Any non-RYZE tenant exporting this PDF ships
  RYZE branding to their client.
- The "⚠ Red Flags" section (recruiter-internal risk assessment from the AI
  brief) is rendered in the export. It must stay visible in the admin UI but
  never appear in the PDF — same boundary the job order PDF already draws for
  Recruiter Notes ("intentionally NOT exported" comment pattern in
  job_orders.py).

Numbered edit sites:

1. **app/api/employer_pdf_template.py — footer brand placeholder.**
   Replace the hardcoded `<span class="footer-brand">RYZE.ai</span>` with
   `{footer_brand}`, mirroring the candidate PDF fix in
   candidate_pdf_template.py (commit 72b6500). Keep the footer-date span
   unchanged.

2. **app/api/employer_pdf_template.py — footer tagline decision.**
   The footer also hardcodes the tagline "Recruiter Intelligence Brief". On
   the candidate PDF the tagline was removed entirely as noise (commit
   158645d, orphaned .footer-sep/.footer-tagline CSS cleaned up).
   DECISION — pick one and state it in the plan:
   - Path A: remove the tagline + .footer-sep (and orphaned CSS), matching
     the candidate PDF exactly (footer shows brand name only).
   - Path B: keep a tagline but make it neutral/client-facing (e.g.
     "Company Profile") — "Recruiter Intelligence Brief" reads internal on a
     marketing document either way, so the current string does not survive.

3. **app/api/employer_profiles.py (PDF route) — wire branding.**
   Call get_branding(db, tenant_id) (resolver already used in bookings.py
   and candidates.py — audit whether employer_profiles.py already imports it)
   and pass footer_brand=branding.brand_name (escaped via pdf_e) into the
   PDF_HTML.format(...) kwargs. RYZE's own PDFs must render unchanged via
   the resolver's per-field fallback, same as the candidate fix.

4. **app/api/employer_profiles.py (PDF route) — remove Red Flags from
   export.** Delete the red_flags_section builder block and its
   red_flags_section= kwarg. Add the boundary comment following the
   job_orders.py precedent:
   `# ── Red Flags — intentionally NOT exported ──` (client-facing artifact;
   red flags stay internal — still visible on the admin detail page and
   EmployerRoster brief panel, never in the PDF).

5. **app/api/employer_pdf_template.py — template cleanup for site 4.**
   Remove the {red_flags_section} placeholder from PDF_HTML and the
   now-orphaned .red-flag-box CSS rule from PDF_STYLE (confirm nothing
   else uses it in this template before deleting).

Out of scope — do NOT touch: the admin UI display of red flags (detail page,
EmployerRoster brief panel), the ai_red_flags field/model/API responses, the
candidate or job order PDFs, the AI brief generation, or the meta chips /
Details sidebar contents (see Notes for parked items).

## Related Files
- app/api/employer_pdf_template.py
- app/api/employer_profiles.py
- Reference (read-only, for the established patterns):
  app/api/candidate_pdf_template.py, app/api/candidates.py
  (download_candidate_pdf), app/api/job_orders.py (Recruiter Notes exclusion
  comment), app/services/branding.py

## Verification
- App import check clean (route count unchanged).
- Export the PDF for a RYZE-tenant employer: footer shows RYZE branding
  exactly as before (fallback path), no Red Flags section anywhere in the
  document, layout intact with no empty gap where the section was.
- Export for a non-RYZE tenant (e.g. green_path_recruiting, the tenant that
  surfaced the candidate-PDF version of this bug): footer shows that tenant's
  brand_name, not RYZE.ai.
- An employer profile with ai_red_flags populated exports with no trace of
  the content; admin UI still shows red flags unchanged on the detail page
  and roster brief panel.
- Grep confirms no orphaned references: red_flags_section, red-flag-box
  in the two edited files (admin UI CSS with the same visual style is
  separate and untouched).

## Notes
Origin: GreenScene Landscaping demo PDF (2026-07-23) showed "RYZE.AI —
Recruiter Intelligence Brief" footer and a "⚠ Red Flags" card on a document
intended as client-facing marketing collateral.

Parked observations — separate decisions, NOT part of this task:
- The relationship_status meta chip (e.g. "Prospect") is internal CRM state
  rendered on a client-facing PDF — candidate for removal in a future pass.
- "Key Talking Points" is recruiter prep material; whether it belongs on a
  document sent TO the prospect is a product decision worth revisiting.
- The "Added <date>" Details row was already parked as possible product noise
  during the candidate PDF task (2026-07-15) — same question applies here.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-23: Audit-first step done before writing code. Confirmed `RYZE_TENANT` still exported from `app/core/deps.py` and already imported/used in `employer_profiles.py`'s PDF route; `get_branding` was not yet imported there. Found a real divergence between the two cited precedents: job_orders.py's Recruiter Notes exclusion keeps an always-empty `{notes_section}` placeholder wired through, while this spec's sites 4-5 call for full deletion of the placeholder/kwarg — confirmed with user that full deletion is intentional, borrowing only job_orders.py's comment wording, not its keep-the-placeholder mechanism. Plan confirmed by user; Path A approved for the footer tagline (remove entirely, matching the candidate PDF's already-shipped end state — verified via grep that `candidate_pdf_template.py` has zero remaining `.footer-sep`/`.footer-tagline` trace).
- 2026-07-23: Pre-implementation verification (per user's added check) — traced `get_branding` (`app/services/branding.py:89`) and confirmed it short-circuits `if tid == RYZE_TENANT: return defaults` for the `ryze` tenant, never querying the `tenants` table, returning the literal `brand_name="RYZE.ai"` — byte-identical to the old hardcoded string. Combined with `pdf_e()` escaping (no-op on this string) and the pre-existing `text-transform: uppercase` CSS rule (applied to both old and new values equally), confirmed the RYZE-tenant PDF footer is guaranteed to render identically. No divergence to report.
- 2026-07-23: Implemented all 5 edit sites as a single commit-ready change. `employer_pdf_template.py`: deleted `.red-flag-box` CSS rule, deleted `.footer-sep`/`.footer-tagline` CSS rules, removed `{red_flags_section}` from `PDF_HTML`, replaced hardcoded footer brand/tagline spans with `{footer_brand}` only (no separator, no tagline). `employer_profiles.py`: added `get_branding` import, added `branding = get_branding(db, tenant_id)` call, deleted the `red_flags_section` builder block in favor of an "intentionally NOT exported" boundary comment (matching job_orders.py's wording, not its empty-placeholder mechanism), removed the `red_flags_section` kwarg, added `footer_brand=pdf_e(branding.brand_name)` kwarg. Grep confirmed zero remaining references to `red_flags_section`/`red-flag-box`/`footer-sep`/`footer-tagline` in either file. App-import check clean: 98 routes (unchanged). Awaiting user's manual PDF export verification (RYZE tenant, green_path_recruiting tenant, red-flags-populated profile) before commit/archive.
