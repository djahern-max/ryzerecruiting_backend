# Current Feature

<!-- Feature/fix name -->
Job Order PDF — banner render parity with Employer Profile PDF + tenant-branded footer

## Status
<!-- Not Started | In Progress | Completed -->
In Progress

## Goals
<!-- Goals & requirements -->
Two defects in the Job Order PDF export, both visible when comparing a job order PDF against
the employer profile PDF for the same employer (observed with the Greenscene Landscaping
tenant demo docs, both generated 2026-07-23):

**Defect 1 — Banner cropping.** The same uploaded employer banner image renders correctly on
the Employer Profile PDF but is visibly cut off / over-cropped on the Job Order PDF. Known
divergence to audit: `job_order_pdf_template.py` renders `.banner` at `height: 180px` while
`employer_pdf_template.py` renders `.banner-strip` at `height: 140px`; the two routes also
build `banner_style` differently (the job order route uses the shorthand
`url('...') center/cover no-repeat` while the CSS block *also* sets `background-size` /
`background-position`). The identity-zone overlap offsets differ too (`-44px` vs `-42px`).
Goal: the Job Order PDF banner must render the same image the same way the Employer Profile
PDF does.

**Defect 2 — Hardcoded RYZE footer.** The `PDF_HTML` footer in `job_order_pdf_template.py`
bakes in `RYZE.AI` / "Job Order Brief" as literals, so `.format()` never touches them and
every tenant's job order PDF ships RYZE-branded. This is the identical defect already fixed
on the candidate PDF (see `context/CHANGELOG.md` — "Tenant-branded candidate PDF footer")
and, based on current output, on the employer PDF. Apply the same pattern: `get_branding(db,
tenant_id)` from `app/services/branding.py`, footer brand as a `{footer_brand}` placeholder
fed with `pdf_e(branding.brand_name)`. Do NOT re-implement the resolver.

**Approach — audit first, do NOT write code yet:**
1. Review `context/CHANGELOG.md` for the candidate PDF footer branding entry (and employer,
   if present) and confirm exactly how the completed pattern was wired — placeholders used,
   where `get_branding` is called, how tenant_id is derived.
2. Show side-by-side: the `.banner` CSS block + banner_style construction in the job order
   template/route vs. `.banner-strip` + banner_style construction in the employer
   template/route. Identify every divergence (height, background declaration shape,
   overlap offset).
3. Show the current `PDF_HTML` footer block in `job_order_pdf_template.py` and the full
   `.format(...)` call in the job order PDF route — enumerate every existing placeholder so
   new ones won't raise `KeyError`.
4. Confirm the route has `db` and how it derives tenant (currently
   `current_user.tenant_id or "ryze"` — note this differs from the `_tenant(current_user)`
   helper used in candidates.py; flag if it should be normalized, don't silently change it).
5. Propose the plan mapped to the numbered edit sites below, stating which of Path A / Path B
   you're taking for the banner and why. Wait for confirmation before writing code.

**Banner fix paths (pick one, justify):**
- **Path A** — Align the job order banner block wholesale to the employer template's
  `.banner-strip` treatment (140px, same background declaration shape, same overlap offset).
  Guarantees visual parity by construction.
- **Path B** — Keep the 180px height but fix the background sizing/position so the image
  crops identically to the employer PDF. Only choose this if there's a deliberate design
  reason the job order banner is taller (check CHANGELOG — a prior polish pass explicitly
  increased the banner height; that intent may conflict with parity and needs a decision).

**Numbered edit sites:**
1. `app/api/job_order_pdf_template.py` — `.banner` CSS block: banner parity per chosen path
2. `app/api/job_order_pdf_template.py` — `PDF_HTML` footer: `{footer_brand}` placeholder
   replacing the hardcoded `RYZE.AI` literal (tagline decision — see Notes)
3. `app/api/job_orders.py` (PDF route) — `banner_style` construction: align to the employer
   route's shape if divergent
4. `app/api/job_orders.py` (PDF route) — add `branding = get_branding(db, tenant_id)`; pass
   `footer_brand=pdf_e(branding.brand_name)` (+ tagline if made a placeholder) into
   `.format()`
5. Read-only reference, do not change: `app/api/employer_pdf_template.py`, the employer PDF
   route, `app/services/branding.py`, `app/api/candidate_pdf_template.py`

**Constraints:**
- No new columns, no Alembic migration — read-only branding resolution at render time.
- `ryze-api` does not need to be stopped for deploy.
- `PDF_STYLE` uses escaped `{{ }}` braces and `{banner_style}` is its ONLY runtime format
  argument — any CSS edits must preserve the escaping. New placeholders go in `PDF_HTML`
  only.
- RYZE tenant output must be regression-safe: footer unchanged for `ryze` (guaranteed by
  `get_branding` fallback), and the banner fix must not break the no-employer /
  no-banner-image gradient fallback.
- If the audit reveals the employer PDF footer is in fact still hardcoded (i.e. the branding
  observed in output came from somewhere else), STOP and flag it — that changes scope and
  needs a decision before proceeding.

## Related Files
<!-- Files this touches -->
- `app/api/job_order_pdf_template.py` — banner CSS block, `PDF_HTML` footer
- `app/api/job_orders.py` — PDF download route: banner_style construction, `get_branding`
  call, `.format()` kwargs
- Read-only reference, do not change:
  - `app/api/employer_pdf_template.py` + employer PDF route — source of truth for banner
    treatment and (presumed) completed footer branding pattern
  - `app/api/candidate_pdf_template.py` / `app/api/candidates.py` — completed footer
    branding pattern
  - `app/services/branding.py` — `get_branding` / `TenantBranding.brand_name`
  - `context/CHANGELOG.md` — history of the candidate footer branding fix and the earlier
    job order PDF banner polish pass

**Explicitly out of scope for this task:**
- Any change to the employer or candidate PDF templates
- Normalizing the tenant-derivation helper across routes (flag only)
- Recruiter Notes handling (intentionally excluded from the job order PDF — leave as is)

## Verification
<!-- How we'll know it worked -->
1. Download the Job Order PDF and the Employer Profile PDF for the same
   `green_path_recruiting` employer (Greenscene Landscaping) → the banner image crops
   identically in both.
2. Same job order PDF → footer shows "Green Path Recruiting", not "RYZE.AI".
3. Download a job order PDF as the `ryze` superuser → footer unchanged ("RYZE.AI" / current
   styling), banner unaffected.
4. A job order with no linked employer or no uploaded banner → gradient fallback renders
   cleanly at the new banner treatment.
5. `.format()` raises no `KeyError`; PDF renders and streams as before.
6. `python audit_tenant_coverage.py` clean if the route's query/auth was touched.

## Notes
<!-- Any extra notes -->
- Tagline decision point: "Job Order Brief" is tenant-neutral, unlike the candidate PDF's
  old "Prepared by your RYZE recruiter" tagline. Recommend keeping it as a literal and only
  parameterizing `footer-brand` — but confirm before writing, and match whatever the
  candidate/employer fix decided for consistency.
- Banner height decision point: CHANGELOG records a deliberate "banner height increased"
  polish on the job order PDF. If Path A (140px parity) reverses that, say so explicitly in
  the plan — parity vs. that earlier polish is a product call, not a silent revert.
- This closes out the last hardcoded-identity holdout flagged in the branding audit
  (CLAUDE.md lists the PDF templates as the remaining migration targets).
- Deploy commands handed to the user, not executed.

## History
<!-- Keep this updated. Earliest to latest -->
- 2026-07-23 — Task created. Origin: comparing the Greenscene Landscaping job order PDF
  against its employer profile PDF (both generated Jul 23) — the job order banner is cut
  off relative to the employer PDF, and the job order footer reads "RYZE.AI" while the
  employer PDF correctly reads "Green Path Recruiting". Footer root cause: hardcoded
  literals in `PDF_HTML` predating the `get_branding` resolver — same defect class already
  fixed on the candidate PDF. Banner root cause: suspected template divergence (180px
  `.banner` vs 140px `.banner-strip`, differing banner_style construction) — to be
  confirmed in audit.
- 2026-07-23 — Audit-first step done before writing code. Confirmed the employer PDF
  footer is already on the `get_branding`/`{footer_brand}` pattern (not hardcoded) — no
  stop/flag needed. Corrected the spec's framing: `banner_style` construction is actually
  identical between the two routes (same `url('...') center/cover no-repeat` shorthand);
  the real divergence is purely numeric — height (180px vs 140px), gradient fallback stop
  count (3-stop vs 2-stop), and identity-zone overlap offset (-44px vs -42px). Git history
  traced: the 180px value came from `5bcfc8c` (May 14, a full undocumented template
  redesign, pre-dates this CHANGELOG), not a reasoned rejection of the employer template's
  140px — supports parity over preservation. Confirmed `job_orders.py`'s PDF route has
  `db` available but no `get_branding`/`RYZE_TENANT` import; `tenant_id = current_user.tenant_id
  or "ryze"` (literal). Flagged, not fixed: three functionally-identical but
  differently-sourced tenant-derivation patterns exist across the codebase (job_orders.py
  literal, employer_profiles.py's `RYZE_TENANT` constant, candidates.py's `_tenant()`
  helper) — out of scope per spec. User confirmed Path A (full parity: 140px, -42px
  overlap, 2-stop gradient) and footer tagline removed entirely (not parameterized),
  matching the candidate/employer PDFs' shipped end state.
- 2026-07-23 — Implemented both defects as full replacements of the 3 numbered edit
  sites. `job_order_pdf_template.py`: `.banner` height 180px→140px, `.identity-zone
  margin-top` -44px→-42px; footer `PDF_HTML` block now renders `{footer_brand}` only (no
  separator/tagline spans); `.footer-sep`/`.footer-tagline` CSS rules deleted. `job_orders.py`:
  gradient fallback in `banner_style` changed to the employer route's 2-stop version;
  added `from app.services.branding import get_branding` import, `branding = get_branding(db,
  tenant_id)` call, and `footer_brand=pdf_e(branding.brand_name)` kwarg into the existing
  `.format()` call (additive — no collision with the 9 existing kwargs). Grep confirmed
  zero remaining `.footer-sep`/`.footer-tagline` references anywhere in the template.
  App-import check clean (98 routes, unchanged). `audit_tenant_coverage.py`: `/{job_order_id}/pdf`
  still SAFE, same 2 pre-existing unrelated REVIEW lines (`candidates.py` `/me/photo`,
  `/me/banner`), no new REVIEW/HARDCODED. Awaiting manual verification against the
  checklist (banner crop parity, non-RYZE footer brand, RYZE-tenant regression check,
  no-employer/no-banner gradient fallback, no `.format()` KeyError).
- 2026-07-23 — User deployed and tested against production. Footer branding confirmed
  correct. Banner: reported the bottom of the image still cut off on the job order PDF at
  140px, worse than before, while the employer PDF's own 140px crop of a *different* image
  looked fine to them. Confirmed the CSS was byte-identical between the two templates at
  this point (re-diffed both `.banner`/`.banner-strip` blocks side by side) — height,
  background-size/position, and overlap all matched. Since the two PDFs render different
  banner images (job order pulls `employer.banner_url` off the linked `EmployerProfile`,
  which for this test case is presumably a wider/taller-content image than whatever was
  used on the employer PDF test), identical CSS produces different visual crop outcomes
  per image — this was a real-world case the "180px was undocumented drift" git-history
  read didn't anticipate: strict 140px parity is demonstrably wrong for this image.
  **Reversing part of Path A per explicit user decision**: banner height set to 220px
  (deliberately taller than both the original 180px and the employer's 140px) to show
  more of the image and reduce the bottom-crop; `-42px` overlap and 2-stop gradient
  fallback from the parity fix are kept unchanged. Job order and employer banners are
  **no longer height-matched** — this is an intentional, confirmed departure from the
  Path A parity goal in the original Goals section, driven by production testing of a
  real image, not a silent revert. `PDF_STYLE`/`.format()` plumbing unaffected (still 1
  runtime arg). Awaiting user re-test against production before this can be marked
  Completed.
- 2026-07-24 — User re-tested 220px against production: **rejected**. 220px made cropping
  worse, not better — flipped from vertical crop (bottom trimmed) to horizontal crop (top
  and right edge of the banner script cut off, more zoomed-in overall than the employer
  PDF). This matches `cover`-fit math: a taller box requires a larger cover-scale factor,
  which generally increases total crop, not reduces it — going taller was the wrong
  direction. Critically, the user also clarified the root confusion from the prior 140px
  test: job order and employer PDFs render **the same banner image** for this employer,
  and at 140px the employer PDF has the *same* vertical trim on the photo strip that the
  job order PDF had — the user now confirms that trim is acceptable and already approved
  on the employer PDF. The earlier "only job order looks cropped" read was inaccurate; the
  actual issue was never a job-order-specific defect, it was the inherent `cover`
  trade-off, which the user is fine with. **Decision: revert `.banner` height 220px →
  140px, restoring full Path A parity** (140px, -42px overlap, 2-stop gradient — all three
  now match `.banner-strip` exactly, no remaining departure). Reverted in code; app-import
  clean (98 routes, unchanged). **Open follow-up, unscoped:** no fixed height +
  `background-size: cover` can show both the full banner script/logo and the full photo
  strip for every uploaded image — 140px trims the photo vertically (accepted), 180/220px
  trimmed differently-shaped images horizontally (rejected). A structural fix (e.g.
  `background-size: 100% auto`, a stored focal-point field, or enforcing a banner aspect
  ratio at upload) is needed to solve this generally, and belongs to a future spec, not
  this task. User will re-deploy and re-test the 140px revert before this task is archived.
