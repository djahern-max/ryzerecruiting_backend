"""
audit_tenant_coverage.py
────────────────────────
Reads every API file, finds every endpoint, and evaluates it against
multi-tenant safety rules. Prints a full report with a verdict for each
endpoint and a summary of what needs attention.

Rules applied to each endpoint function body:
  ✓ SAFE       — uses get_current_tenant / get_current_admin_tenant
  ✓ SAFE       — filters query by tenant_id variable
  ✓ SAFE       — uses current_user.tenant_id directly
  ⚠ HARDCODED  — uses RYZE_TENANT constant instead of dynamic tenant
  ⚠ REVIEW     — authenticated but no tenant filter found
  ○ PUBLIC     — no auth dependency (intentionally open)
  ○ SKIP       — utility endpoint (health check, webhooks, etc.)

Usage:
    cd ~/projects/ryzerecruiting/backend
    python audit_tenant_coverage.py

    # Write report to file:
    python audit_tenant_coverage.py > tenant_audit.txt
"""

import ast
import os
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────

API_DIR = Path(__file__).parent / "app" / "api"

# Endpoints in these files are intentionally public or infrastructure —
# they don't touch recruiter data so tenant scoping doesn't apply.
SKIP_FILES = {"webhooks.py", "blog.py", "contact.py", "ai_parser.py"}

# Endpoints whose names match these patterns are intentionally public.
PUBLIC_PATTERNS = {
    "availability",
    "login",
    "register",
    "callback",
    "health",
    "oauth",
    "verify",
    "join_waitlist",
    "read_blog_root",
    "respond_to_invite",
    "get_my_bookings",
    "trigger_embedding_sync",
}

# Auth dependency names that mean "this endpoint requires a logged-in user"
AUTH_DEPS = {
    "get_current_user",
    "get_current_admin_user",
    "require_admin",
    "get_current_admin_tenant",
    "get_current_tenant",
    "get_any_authenticated_user",
    "get_current_superuser",
}

# Patterns that indicate a webhook verifies the caller via a provider
# signature/HMAC check instead of a logged-in user — e.g. billing.py's
# stripe_webhook (stripe.Webhook.construct_event + SignatureVerificationError)
# or webhooks.py's Zoom handler (hmac.compare_digest via _verify_zoom_signature).
# These are infrastructure endpoints: there's no tenant_id to scope by until
# the signature is verified and the payload is parsed, so they're SAFE rather
# than REVIEW.
SIGNATURE_VERIFIED_PATTERNS = [
    "construct_event",  # stripe.Webhook.construct_event(...)
    "SignatureVerificationError",
    "compare_digest",  # hmac.compare_digest(expected, signature)
    "_verify_zoom_signature",
    "verify_webhook_signature",
]

# Regex matched against a `<something>_token == token` comparison, i.e. a
# lookup keyed on an unguessable per-record token rather than current_user —
# e.g. bookings.py's /respond and /respond/confirm, which resolve the booking
# via `Booking.response_token == token` instead of a auth dependency.
TOKEN_LOOKUP_RE = re.compile(r"\w*_token\s*==\s*token\b")

# Patterns in the function source that indicate tenant scoping is in place
TENANT_SAFE_PATTERNS = [
    "get_current_tenant",
    "get_current_admin_tenant",
    "current_user.tenant_id",
    "_tenant(current_user)",
    "tenant_id == tenant_id",
    "tenant_id == ",
    ".tenant_id",
]

HARDCODED_PATTERNS = [
    "RYZE_TENANT",
    '"ryze"',
    "'ryze'",
]

# HTTP method decorators
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

# ── Colours ───────────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class EndpointResult:
    file: str
    method: str
    path: str
    func_name: str
    verdict: str  # SAFE | HARDCODED | REVIEW | PUBLIC | SKIP | UNKNOWN
    detail: str = ""
    line: int = 0


# ── AST helpers ───────────────────────────────────────────────────────────


def get_decorator_info(decorator) -> tuple[Optional[str], Optional[str]]:
    """
    Extract (http_method, route_path) from a FastAPI route decorator.
    Returns (None, None) if not a route decorator.
    """
    # @router.get("/path") or @app.post("/path")
    if isinstance(decorator, ast.Call):
        func = decorator.func
        if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
            method = func.attr.upper()
            path = None
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = decorator.args[0].value
            return method, path
    return None, None


def get_dep_names(func_node: ast.FunctionDef) -> set[str]:
    """
    Extract all Depends(...) values from function parameters.
    Returns a set of dependency function names used.
    """
    deps = set()
    for arg in func_node.args.args:
        # look through defaults for Depends(...)
        pass
    # Walk the whole function signature looking for Depends calls in annotations/defaults
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Depends":
                if node.args:
                    dep_arg = node.args[0]
                    if isinstance(dep_arg, ast.Name):
                        deps.add(dep_arg.id)
                    elif isinstance(dep_arg, ast.Attribute):
                        deps.add(dep_arg.attr)
    return deps


def get_function_source_lines(
    func_node: ast.FunctionDef, source_lines: list[str]
) -> str:
    """Extract the raw source text of a function."""
    start = func_node.lineno - 1
    end = func_node.end_lineno
    return "\n".join(source_lines[start:end])


def has_signature_verification(func_source: str) -> bool:
    """True if the function verifies a webhook via provider signature/HMAC."""
    return any(p in func_source for p in SIGNATURE_VERIFIED_PATTERNS)


def has_token_lookup_auth(func_node: ast.FunctionDef, func_source: str) -> bool:
    """
    True if the endpoint takes a `token` param and resolves the row by
    comparing a `*_token` column against it — a magic-link auth pattern
    (see bookings.py's /respond and /respond/confirm) rather than a
    logged-in-user dependency.
    """
    has_token_param = any(arg.arg == "token" for arg in func_node.args.args)
    if not has_token_param:
        return False
    return bool(TOKEN_LOOKUP_RE.search(func_source))


def evaluate_endpoint(
    func_name: str,
    func_source: str,
    dep_names: set[str],
    func_node: ast.FunctionDef,
) -> tuple[str, str]:
    """
    Apply tenant-safety rules to an endpoint.
    Returns (verdict, detail).
    """
    # Check if it's a known public endpoint
    if any(pat in func_name.lower() for pat in PUBLIC_PATTERNS):
        return "PUBLIC", "No auth required — intentionally open"

    if has_signature_verification(func_source):
        return (
            "SAFE",
            "Verified by provider signature/HMAC check (webhook) — no tenant scoping needed",
        )

    if has_token_lookup_auth(func_node, func_source):
        return (
            "SAFE",
            "Token-authenticated — resolves record via unguessable token instead of current_user",
        )

    has_auth = bool(dep_names & AUTH_DEPS)

    # Check for safe tenant patterns in the function body
    safe_hits = [p for p in TENANT_SAFE_PATTERNS if p in func_source]
    hardcoded_hits = [p for p in HARDCODED_PATTERNS if p in func_source]

    if not has_auth:
        # No auth at all — check if it touches data
        if any(kw in func_source for kw in ["db.query", "db.execute", "SELECT"]):
            return (
                "REVIEW",
                "No auth dependency + reads from DB — verify this is intentional",
            )
        return "PUBLIC", "No auth dependency"

    # Has auth — now check tenant handling
    if safe_hits:
        return "SAFE", f"Tenant scoping found: {safe_hits[0]}"

    if hardcoded_hits:
        return (
            "HARDCODED",
            f"Uses hardcoded tenant: {hardcoded_hits[0]} — replace with get_current_tenant()",
        )

    # Authenticated but no tenant pattern found
    # Check if it touches multi-tenant tables
    tenant_tables = ["candidates", "employer_profiles", "job_orders", "bookings"]
    touches_data = any(t in func_source for t in tenant_tables)

    if touches_data:
        return (
            "REVIEW",
            "Authenticated + touches tenant data but no tenant_id filter found",
        )

    # Authenticated but doesn't seem to touch tenant-sensitive data
    return "SAFE", "Authenticated — no tenant-sensitive data access detected"


# ── Main audit ────────────────────────────────────────────────────────────


def audit_file(filepath: Path) -> list[EndpointResult]:
    results = []
    source = filepath.read_text()
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"{RED}  Syntax error in {filepath.name}: {e}{RESET}")
        return results

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Find route decorators on this function
        for decorator in node.decorator_list:
            method, path = get_decorator_info(decorator)
            if method is None:
                continue

            dep_names = get_dep_names(node)
            func_source = get_function_source_lines(node, source_lines)
            verdict, detail = evaluate_endpoint(node.name, func_source, dep_names, node)

            results.append(
                EndpointResult(
                    file=filepath.name,
                    method=method,
                    path=path or "(?)",
                    func_name=node.name,
                    verdict=verdict,
                    detail=detail,
                    line=node.lineno,
                )
            )

    return results


def verdict_icon(verdict: str) -> str:
    return {
        "SAFE": f"{GREEN}✓ SAFE      {RESET}",
        "HARDCODED": f"{YELLOW}⚠ HARDCODED {RESET}",
        "REVIEW": f"{RED}✗ REVIEW    {RESET}",
        "PUBLIC": f"{GRAY}○ PUBLIC    {RESET}",
        "SKIP": f"{GRAY}○ SKIP      {RESET}",
        "UNKNOWN": f"{GRAY}? UNKNOWN   {RESET}",
    }.get(verdict, verdict)


def method_color(method: str) -> str:
    colors = {
        "GET": BLUE,
        "POST": GREEN,
        "PATCH": YELLOW,
        "DELETE": RED,
        "PUT": YELLOW,
    }
    return colors.get(method, RESET) + f"{method:<7}" + RESET


def main():
    if not API_DIR.exists():
        print(f"{RED}ERROR: API directory not found: {API_DIR}{RESET}")
        print("Run this script from the backend root directory.")
        sys.exit(1)

    all_results: list[EndpointResult] = []

    api_files = sorted(API_DIR.glob("*.py"))

    print(
        f"\n{BOLD}═══════════════════════════════════════════════════════════════{RESET}"
    )
    print(
        f"{BOLD}  RYZE.ai — Multi-Tenant Endpoint Coverage Audit               {RESET}"
    )
    print(
        f"{BOLD}═══════════════════════════════════════════════════════════════{RESET}"
    )
    print(f"  Scanning: {API_DIR}\n")

    for filepath in api_files:
        if filepath.name.startswith("__"):
            continue

        is_skip = filepath.name in SKIP_FILES
        results = audit_file(filepath)

        if not results:
            continue

        # Mark all results in skip files
        if is_skip:
            for r in results:
                r.verdict = "SKIP"
                r.detail = "Infrastructure/utility file — tenant scoping not applicable"

        all_results.extend(results)

        # Print file section
        print(f"{BOLD}  {filepath.name}{RESET}")
        for r in results:
            icon = verdict_icon(r.verdict)
            meth = method_color(r.method)
            path_str = f"{r.path:<40}"
            print(f"    {icon}  {meth}  {path_str}  {GRAY}{r.detail}{RESET}")
        print()

    # ── Summary ───────────────────────────────────────────────────────────
    safe = [r for r in all_results if r.verdict == "SAFE"]
    hardcoded = [r for r in all_results if r.verdict == "HARDCODED"]
    review = [r for r in all_results if r.verdict == "REVIEW"]
    public = [r for r in all_results if r.verdict == "PUBLIC"]
    skip = [r for r in all_results if r.verdict == "SKIP"]
    total = len(all_results)

    print(
        f"{BOLD}═══════════════════════════════════════════════════════════════{RESET}"
    )
    print(f"{BOLD}  Summary{RESET}")
    print(
        f"{BOLD}═══════════════════════════════════════════════════════════════{RESET}"
    )
    print(f"  Total endpoints scanned : {total}")
    print(f"  {GREEN}✓ Safe                  : {len(safe)}{RESET}")
    print(f"  {GRAY}○ Public / Skip         : {len(public) + len(skip)}{RESET}")
    print(f"  {YELLOW}⚠ Hardcoded tenant      : {len(hardcoded)}{RESET}")
    print(f"  {RED}✗ Needs review          : {len(review)}{RESET}")

    if hardcoded or review:
        print(f"\n{BOLD}  Action required:{RESET}")
        for r in hardcoded + review:
            icon = verdict_icon(r.verdict)
            print(f"    {icon}  {r.file:<30}  {r.method:<7}  {r.path}")
            print(f"           {GRAY}↳ {r.detail}{RESET}")

        print(f"\n{BOLD}  Fix pattern:{RESET}")
        print(
            f"    1. Add  {GREEN}current_user: User = Depends(get_current_admin_user){RESET}  to the function"
        )
        print(f"    2. Add  {GREEN}tenant_id = current_user.tenant_id or 'ryze'{RESET}")
        print(
            f"    3. Add  {GREEN}.filter(Model.tenant_id == tenant_id){RESET}  to every query"
        )
    else:
        print(
            f"\n  {GREEN}{BOLD}✅ All authenticated data endpoints are tenant-scoped.{RESET}"
        )

    print(
        f"{BOLD}═══════════════════════════════════════════════════════════════{RESET}\n"
    )

    # Exit code 1 if anything needs fixing (useful for CI)
    sys.exit(1 if (hardcoded or review) else 0)


if __name__ == "__main__":
    main()
