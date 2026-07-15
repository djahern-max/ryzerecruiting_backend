# Current Feature

<!-- Feature/fix name -->
Tenant-branded candidate PDF footer — resolve the hardcoded RYZE footer via get_branding

## Status
<!-- Not Started | In Progress | Completed -->
Not Started

## Goals
<!-- Goals & requirements -->
The candidate profile PDF footer is hardcoded to RYZE.ai / "Prepared by your RYZE recruiter"
in candidate_pdf_template.py. Those strings live directly in the PDF_HTML template, so
.format() never touches them — the footer is the same regardless of which firm owns the
candidate. On a multi-tenant platform the PDF should carry the branding of the tenant that
owns the candidate. For the green_path_recruiting tenant it should read "Green Path
Recruiting"; RYZE's own PDFs must be byte-for-byte unchanged.

The resolver already exists — `get_branding(db, tenant_id)` in `app/services/branding.py`
returns a `TenantBranding` whose `brand_name` falls back to RYZE globals field-by-field
(`brand_name` <- `tenant.company_name`, else RYZE default). Use it; do not re-implement it.

Goal: turn the footer brand + tagline into `PDF_HTML` placeholders and feed them from
`get_branding` in the `download_candidate_pdf` route.

**Approach — audit first, do NOT write code yet:**
1. Show the current footer block in `PDF_HTML` (`candidate_pdf_template.py`) and the full
   `.format(...)` call in `download_candidate_pdf` (`candidates.py`) — confirm every existing
   placeholder so two new ones won't raise `KeyError`.
2. Confirm the route already has `db` and derives `tenant_id` via `_tenant(current_user)`.
3. Propose the plan (two placeholders `{footer_brand}` / `{footer_tagline}`; one
   `branding = get_branding(db, tenant_id)` line; pass `footer_brand=pdf_e(branding.brand_name)`
   and the tagline into `.format()`). Wait for my confirmation, then write a complete
   replacement of the footer block and the `.format()` call — not a partial diff.

**Constraints:**
- No new columns, no Alembic migration — read-only branding resolution at render time.
- `ryze-api` does not need to be stopped.
- `PDF_STYLE` uses escaped `{{ }}` braces; only `PDF_HTML` gets the new placeholders. Do not
  add placeholders to the CSS block.
- RYZE tenant footer must be unchanged (regression-safe because `get_branding` falls back).

## Related Files
<!-- Files this touches -->
- `app/api/candidate_pdf_template.py` — `PDF_HTML` footer block: two new placeholders
- `app/api/candidates.py` — `download_candidate_pdf`: call `get_branding`, pass footer kwargs
- Read-only reference, do not change:
  - `app/services/branding.py` — `get_branding` / `TenantBranding.brand_name`

**Explicitly out of scope for this task:**
- `app/api/employer_pdf_template.py` (footer "RYZE.ai" / "Recruiter Intelligence Brief") and
  `app/api/job_order_pdf_template.py` (footer "RYZE.AI" / "Job Order Brief") — same pattern,
  separate commits. Flag them; batch only if confirmed.
- The "Added" row in Profile Details (`candidate.created_at`, shows "—" when null) — on a
  hiring-manager-facing PDF the internal record-creation date is arguably noise. Keep / relabel /
  remove / swap for another field is a product call. Recommend in the plan, don't decide silently.
  Its own commit if changed.

## Verification
<!-- How we'll know it worked -->
1. Download the candidate PDF for a `green_path_recruiting` candidate (Renata Voss) as a
   `green_path_recruiting` admin → footer shows "Green Path Recruiting".
2. Download a candidate PDF as the `ryze` superuser → footer is unchanged ("RYZE.ai").
3. A tenant with all-NULL branding overrides → footer falls back to RYZE default cleanly.
4. `.format()` raises no `KeyError`; PDF renders and streams as before.
5. `python audit_tenant_coverage.py` clean if the route's query/auth was touched.

## Notes
<!-- Any extra notes -->
- Tagline decision point: "Prepared by your Green Path Recruiting recruiter" reads awkwardly
  ("Recruiting recruiter"). Since the brand name is already shown in footer-brand, recommend a
  generic tagline — "Prepared by your recruiter" — that works for any tenant name. Confirm
  wording before writing.
- This is the same class of fix as the branding resolver rollout (notifications/email already use
  `get_branding`); the PDF templates are the last hardcoded-identity holdouts flagged in the
  branding audit.
- Deploy commands handed to the user, not executed.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-15 — Task created. Origin: recording the Renata Voss demo on the
  `green_path_recruiting` tenant and noticed the downloaded candidate PDF footer reads "RYZE.ai"
  instead of the owning firm's brand. Root cause: the footer strings are hardcoded literals in
  `PDF_HTML`, predating the `get_branding` resolver. Also surfaced the "Added" row (`created_at`)
  as a possible product-noise item — parked as a separate decision.
