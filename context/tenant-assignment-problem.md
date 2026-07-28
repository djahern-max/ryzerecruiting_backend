# Tenant assignment problem — stray `slug='none'` / `company_name='None'` rows

## Status
Observed in production (2026-07-28) — not yet root-caused or fixed.

## What's known
During live Stripe go-live testing on 2026-07-28, a self-serve signup produced a
`tenants` row with `slug = 'none'` and `company_name = 'None'` (row id 2 at the
time — since deleted after confirming no `users` row referenced it). The literal
string `"None"`/`"none"` rather than a null/empty value strongly suggests a Python
`None` got stringified somewhere in the signup path (e.g. an f-string or
`str(None)` used to build the slug or read a form field that came back empty),
rather than a deliberate default.

This had previously been discussed as a theoretical risk; this is the first
observed instance in production. Root cause not yet investigated — needs tracing
through `app/api/auth.py`'s `signup_firm` (and its slug-generation helper) to find
where a missing/empty input can flow through to a literal `"none"`/`"None"` string
instead of being rejected or defaulted safely.

## Evidence log
- 2026-07-28 — Live self-serve signup during Stripe go-live testing created
  `tenants` row id 2: `slug='none'`, `company_name='None'`. Confirmed no `users`
  row had `tenant_id` pointing at it, then deleted the row. Upgrades this from a
  theoretical gap to an observed production occurrence.

## Next steps (not started)
- Reproduce locally: submit `signup-firm` with an empty/missing company name and
  see whether the slug generator or `Tenant(...)` construction is what produces
  the literal string.
- Decide the correct behavior: reject the signup with a 400 if company name is
  missing, vs. generate a safe fallback slug — and fix at the validation layer,
  not just patch the symptom.
