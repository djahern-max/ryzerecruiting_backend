# Changelog

Completed features/fixes move here from `current-feature.md` once Status = Completed — paste in the final Goals + full History, newest entry at the top. `current-feature.md` then resets to a blank template for the next item.

This file doubles as source material for the Build in Public series — each entry is close to script-ready: what the problem was, what changed, and the dated sequence of how it got fixed.

<!--
Example entry format:

## Fix false positives in audit_tenant_coverage.py (completed 2026-07-XX)
Fixed the tenant audit script's detection logic so it recognizes aliased auth
dependencies and signature/token-based auth, eliminating 7 false-positive
REVIEW flags with no change to actual endpoint behavior.

History:
- 2026-07-07 — Ran full audit, found 8 REVIEW flags.
- 2026-07-07 — Verified 7 of 8 are false positives.
- 2026-07-08 — Script fixed, re-ran, confirmed 0 REVIEW flags.
-->
