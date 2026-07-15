---
recordedAt: "2026-07-15T19:01:23+09:00"
timezone: "Asia/Tokyo"
finalForSession: true
originSessionId: "019f63ba-bd94-7482-a809-ee87652191bd"
repo: "hermes-agent"
branch: "chore/hdev-v0.18.2-integration"
---

# Hermes cross-machine security closeout

## Objective

Close the Hermes 0.18.2 integration work without interrupting a running Hermes session. The work covers runtime reliability, profile isolation, authorization refresh, safe delivery behavior, dependency alignment, regression tests, a security review, and a resumable handoff.

## Repository state

- Working branch: `chore/hdev-v0.18.2-integration`
- Runtime and security commit: `52e30bbc9`
- CI remediation commit: `eaa1908fb`
- Review PR: `https://github.com/shokirunicus/hermes-agent/pull/1`
- Review base: `integration/v0.18.2-base` at the v0.18.2 release commit
- Intended production destination remains the user fork's `main` branch after a separate upstream-port pass.
- Upstream is retained as the read-only integration source; do not open this private operational closeout directly against upstream.
- Current upstream is 685 commits ahead of the release base. A read-only merge simulation found seven content conflicts, so this closeout did not invalidate the verified diff with a late bulk merge.
- Two unrelated, older untracked G100 orchestration files were excluded from this change and moved to a temporary archive before commit. Do not recreate or include them without a separate scope decision.

## Implemented behavior

- External synthetic events and durable Kanban notifications re-check current authorization even when the source has no user identifier.
- Trusted local internal events retain their intended bypass.
- Kanban subscriptions retain chat scope and external-origin state; ambiguous legacy external rows fail closed.
- Transcript mirroring defaults to the main profile and carries the active profile through direct-message and cron paths.
- QQ approval buttons bind to one pending request; typed slash approvals preserve FIFO behavior.
- Remote relay connections reject plaintext WebSocket transport after case-normalized URL parsing.
- Delivery errors are redacted before reaching external chat surfaces.
- Lazy Discord installation uses the same exact security-sensitive dependency versions as the eager installation path.
- Existing gateway, shutdown-forensics, dead-target, platform, state, tool, and packaging reliability changes on the branch were retained and reviewed.

## Security review

- The complete intended working-tree diff was inventoried across 24 review units.
- Six additional candidates were reproduced with controls, attack-path reviewed, remediated, and regression-tested.
- Final current findings: zero open findings in the intended diff.
- Python dependency audit: no known vulnerabilities.
- Photon sidecar audit: zero vulnerabilities.
- No secrets were intentionally added. Run the staged-diff secret check again if this branch is amended.
- Detailed scan receipts are stored with the closeout report outside the repository; do not publish the raw exploit reproductions.

## Verification evidence

- Focused remediation suite: 585 passed.
- Messaging, cron, and approval suite: 396 passed.
- Broader selected suite: 2,053 passed, 1 skipped.
- Earlier canonical relevant suite: 1,179 passed.
- Dependency compatibility: all 94 installed packages compatible.
- Python dependency audit: no known vulnerabilities.
- Photon install and audit: zero vulnerabilities; post-install patch verified.
- Static lint, lockfile verification, Node syntax checks, and whitespace checks passed.
- Repository-wide parallel suite: 39,359 passed and 113 failed across 1,930 files. The failures are outside the intended behavior and cluster around missing optional ACP support, operating-system process guards, local provider state, network/catalog access, and timing-sensitive process tests. One stale dependency expectation related to this diff was found, fixed, and re-tested.
- Final wheel built successfully. SHA-256: `c2ce46aaea967508ec230ac3656302f11f25042dc02e3f3c04b44d0eea7f0d7b`.
- Repository-wide formatter check reports broad pre-existing drift. Do not bulk-format this branch; lint passes and the diff stays scoped.
- The first PR CI run exposed two inherited integration defects: cleanup-order expectations lagged the security-motivated finalizer order, and an explicit nested-dispatch identity leaked into the next unrelated call. The expectation was updated, dispatch identity is now scoped and reset, and the 35-test focused regression set passes.
- The user fork's `main` branch was fast-forwarded to current upstream so contributor attribution CI no longer compares the PR against an obsolete fork history.

## Runtime state

- Both the local workstation and automation host report Hermes 0.18.2.
- The local workstation's active Hermes session was deliberately left untouched.
- The automation host gateway remains supervised and connected to its configured chat lanes.
- The local workstation gateway can connect when run directly, but its service bootstrap still returns an operating-system I/O error. Two safe attempts produced the same result, so no further service mutation was made.
- Automatic skill generation is aligned to roughly every 50 eligible interactions, with weekly curation on both systems.
- Context compression, tool-result limits, and prompt-injection filtering are aligned across both systems.

## Known non-blocking items

- The local workstation service bootstrap issue is not fixed in this branch. Investigate it in a fresh maintenance window with no active Hermes session.
- The repository-wide test runner includes optional-provider, live-system-guard, process-permission, network/catalog, and timing-sensitive failures unrelated to this diff.
- Two older G100 orchestration files remain outside Git in a temporary archive and require a separate ownership decision.
- The raw scan-contract auto-sealer rejected the locally assembled manifest twice because artifact records were not pre-generated. Per the two-failure rule, retries stopped; the unsealed source receipts were preserved for a later tooling-specific closeout.

## Resume procedure

1. Read this memo and the Draft PR before modifying the branch.
2. Confirm the branch, status, and running Hermes processes. Do not restart or stop a live session.
3. Review only the Draft PR diff; keep the archived G100 files out of scope.
4. If amending code, rerun the focused changed-path suites, dependency audits, lint, and staged secret scan.
5. Treat the local workstation service bootstrap issue as a separate task.
6. Merge only after Draft PR review and CI results are acceptable. This closeout does not authorize an automatic merge.

## Closeout references

- Draft PR: `https://github.com/shokirunicus/hermes-agent/pull/1` (open and mergeable against the fixed review base; final CI rerun pending at recording time).
- Branch push: completed to the user fork.
- Shared workspace handoff: created during final closeout and referenced from the workspace index.
