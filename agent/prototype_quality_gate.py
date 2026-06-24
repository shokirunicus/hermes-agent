"""Prototype/demo/report quality gate guidance for market-facing work.

The gate is intentionally prompt-level, not a hard tool blocker.  Its job is
to stop the agent from presenting low-quality prototypes to the user as if they
were ready for review, and to force a separation between three audiences:
market-facing UI/UX, owner/operator review notes, and internal QA checks.
"""

from __future__ import annotations

from typing import Any, Mapping

QUALITY_GATE_PROMPT = """# Prototype / Demo / Report Quality Gate

Apply this gate whenever the user asks to build, improve, review, show, demo,
prototype, MVP, landing page, app, website, tool, report, sales material, or
market-facing artifact.

Core rule:
- Do not show the user a low-quality prototype as if it were ready for review.
- "It runs" is not enough. The artifact must be useful, understandable, and safe
  enough for a first paid-user / paid-pilot / sales-validation review, unless the
  user explicitly asked for a throwaway sandbox.

Separate these three layers. Never mix them:
1. Market-facing UI/UX layer — what an actual visitor/customer/user sees.
   Include only product-natural content: value, next action, sample/preview labels
   where needed, confidence/status, and no-side-effect notices when they are part
   of the product experience.
2. Owner review layer — what the owner/BOSS must decide.
   Put this outside the product UI: review brief, acceptance criteria, what to
   inspect, business hypothesis, pricing/sales/readiness gaps, and go/no-go notes.
3. Internal QA layer — what the agent must check before showing anything.
   Keep this out of the product UI and out of the user's review burden unless it
   changes the decision: tests, lint, build, browser smoke, copy quality, security,
   mock/fallback labels, broken states, and implementation gaps.

Before presenting a prototype/demo/report to the user, verify or explicitly mark:
- Primary user journey has been exercised end-to-end, or the artifact is clearly
  labelled internal-only / sandbox / not market-facing.
- Empty/loading/error/success states are not trash-level placeholders.
- Mock, sample, deterministic fallback, and unverified claims are labelled in the
  right layer, not hidden and not dumped into the customer UI as operator notes.
- If called a report, it contains decision-grade substance. For code/repo reports,
  security risk, dangerous commands, dependency/license risk, build/use potential,
  business opportunity, and monetization paths must be addressed or marked
  unverified. Surface summaries alone are not reports.
- The user is not asked to debug obvious UI/UX, copy, purpose, or quality defects
  that the agent can fix first.

If the artifact fails this gate:
- Do not say it is done.
- Fix it first when tools/scope allow.
- If blocked, say exactly what is blocked and present it as internal-only evidence,
  not as a finished demo/prototype/report.
"""


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def build_quality_gate_prompt(config: Mapping[str, Any] | None) -> str:
    """Return quality-gate prompt text when enabled by config, otherwise empty."""

    cfg = _as_mapping(config)
    gate_cfg = _as_mapping(cfg.get("prototype_quality_gate"))
    if not _truthy(gate_cfg.get("enabled"), default=False):
        return ""
    return QUALITY_GATE_PROMPT
