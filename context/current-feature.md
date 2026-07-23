# Current Feature

Job Orders — hourly rate range + employment type + industry-agnostic parser (backend)

## Status
Not Started

## Goals
Extend the job order model and pipeline to support any industry and any engagement type:

1. Add **hourly_min / hourly_max** alongside the existing annual salary_min / salary_max — a job order can carry either, both, or neither.
2. Add **employment_type** with the standard recruiting values: `contract`, `contract_to_hire`, `direct_hire` (Direct Hire = permanent placement).
3. Make the AI job-description parser **industry-agnostic** and teach it to extract the new fields (hourly rates and employment type), mapping common phrasings (temp-to-hire → contract_to_hire, permanent/full-time → direct_hire, etc.).
4. Flow the new fields through the **embedding text** (so RYZE Intelligence can match on them) and the **PDF export** chips.

Companion frontend task exists in the frontend repo's `context/current-feature.md`. **This repo ships first** — run the migration, deploy backend, then frontend. Pydantic tolerates missing fields in either direction, so there is no breaking window.

### Numbered edit sites
1. **`app/models/job_order.py`** — add columns to `JobOrder`:
   - `hourly_min`, `hourly_max` — see Decision (Path A/B) below
   - `employment_type = Column(String(50), nullable=True)` — values: `contract | contract_to_hire | direct_hire` (comment them, matching the existing `status` comment style)
2. **Alembic migration** — new revision adding the three columns, all nullable, with a working `downgrade()`. No data backfill.
3. **`app/schemas/job_order.py`** — add `hourly_min: Optional[float] = None`, `hourly_max: Optional[float] = None`, `employment_type: Optional[str] = None` to **all five** classes: `JobOrderCreate`, `JobOrderUpdate`, `JobOrderResponse`, `JobOrderParseResponse`, `JobMatchResult`.
4. **`app/services/ai_parser.py`** → `parse_job_description` — replace the prompt:
   - open with "job description or job posting **from any industry**"
   - add JSON keys `hourly_min` (number or null), `hourly_max` (number or null), `employment_type` (string or null, one of the three values) with mapping rules: temp/temporary/contractor/W2 contract/1099 → `contract`; temp-to-hire/temp-to-perm/contract-to-hire → `contract_to_hire`; permanent/full-time employee/direct placement → `direct_hire`
   - rules: salary fields are annual only, hourly fields are hourly only, **never convert between them**; if pay is stated hourly fill hourly and leave salary null (and vice versa); null all four if pay unstated
5. **`app/services/embedding_service.py`** → `build_job_order_text` — after the salary block, append hourly range (formatted `$32.50 - $45.00/hr`) and employment type using human labels (`Contract`, `Contract-to-Hire`, `Direct Hire (Permanent)`), so engagement type becomes semantically searchable.
6. **`app/api/job_order_pdf_template.py`** — add `fmt_hourly(min_val, max_val)` next to `fmt_salary` (same shape: `$25.00/hr – $40.00/hr`, `+`, `up to`), and an `EMPLOYMENT_TYPE_LABELS` dict (`contract` → Contract, `contract_to_hire` → Contract-to-Hire, `direct_hire` → Direct Hire).
7. **`app/api/job_orders.py`** → `download_job_order_pdf` chips block — after the salary chip, add an hourly chip (if any hourly value) and an employment-type chip (if set), reusing the helpers from edit site 6.
8. **(In scope, small) `app/api/candidates.py`** — both explicit `JobMatchResult(...)` constructions (`get_my_job_matches` ranked + `_unranked_fallback`): add `hourly_min`, `hourly_max`, `employment_type` from the job. Not strictly required (schema defaults to None) but candidate-facing matches should show engagement type.
9. **(Out of scope unless I say otherwise) `seed_full.py`** — seed data stays finance-flavored for now. Do not touch.

## Related Files
- `app/models/job_order.py`
- `alembic/versions/` (new migration)
- `app/schemas/job_order.py`
- `app/services/ai_parser.py`
- `app/services/embedding_service.py`
- `app/api/job_order_pdf_template.py`
- `app/api/job_orders.py`
- `app/api/candidates.py`

## Decisions to flag in the audit
- **Hourly column type — Path A (preferred): `Numeric(8, 2)`** because hourly rates commonly carry cents ($32.50). Pydantic side is `Optional[float]`. **Path B: `Integer`** for symmetry with salary columns — only take this if you find a serialization/JSON issue with Numeric in the existing response patterns. State which path you're taking and why in the plan.
- **Embedding backfill:** existing job orders re-embed automatically on their next PATCH (the background task already fires on every update). Confirm in the plan whether you'll also propose a one-off backfill script as a follow-up, but do **not** write or run one as part of this task.

## Verification
- [ ] Migration runs cleanly (`alembic upgrade head`), and `\d job_orders` shows `hourly_min numeric(8,2)`, `hourly_max numeric(8,2)`, `employment_type varchar(50)` (adjust if Path B); `alembic downgrade -1` then re-upgrade also clean on local
- [ ] POST `/api/job-orders` with hourly + employment_type only (no salary) → 201, response echoes the new fields
- [ ] PATCH updating just `employment_type` → persists, other fields untouched
- [ ] POST `/api/job-orders/parse` with a pasted **hourly contract** posting from a non-finance industry (e.g. a warehouse or nursing role, "$28–$35/hr, temp-to-hire") → returns hourly_min/max filled, salary null, `employment_type: "contract_to_hire"`
- [ ] Same with a salaried permanent posting → salary filled, hourly null, `direct_hire`
- [ ] After creating a job order with the new fields, check logs for successful embed, and confirm `build_job_order_text` output includes the hourly range and employment-type label (log or quick shell check)
- [ ] GET `/api/job-orders/{id}/pdf` for an hourly contract order → chips show hourly range + "Contract" alongside status; a salary-only order still renders exactly as before
- [ ] Existing orders (all salary-only, no employment_type) list and render with zero visual/API change

## Notes
- All three columns nullable, no defaults — old rows and old clients remain valid.
- Employment-type values are stored lowercase snake_case; display labels live in the PDF template dict (backend) and in the frontend. Don't invent a fourth value.
- One concern per commit: model+migration+schemas can be one commit; parser prompt another; embedding+PDF another — propose a split in the plan.
- Deploy order: migration → backend deploy → then the frontend task ships.

## History
<!-- Keep this updated. Earliest to latest -->
