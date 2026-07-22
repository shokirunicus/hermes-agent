---
recordedAt: "2026-07-22T13:19:33+09:00"
timezone: "Asia/Tokyo"
type: "development-handoff"
repo: "hermes-agent"
profile: "hdev"
branch: "fix/hdev-gateway-log-permissions"
implementationCommit: "443f3919ecbb5c7ff663673992a311bcce3cd390"
pr: "https://github.com/shokirunicus/hermes-agent/pull/3"
prBase: "chore/hdev-v0.18.2-integration"
status: "ready-for-review; do-not-merge-without-explicit-approval"
finalForSession: true
---

# hdev P0 security remediation — continuation handoff

## Conclusion

The hdev Hermes runtime is operating with corrected dependency versions, owner-only state/log permissions, config schema v33, working MCP connections, and a launchd-supervised Gateway. The implementation is saved on a fresh branch and reviewed in PR #3.

Two custom `pre_tool_call` shell hooks are intentionally disabled. An independent hostile review found self-approval and fail-open paths. Do not reapprove them until they are redesigned and separately reviewed.

The final handoff commit and remote branch SHA must always be verified live with:

```bash
cd <repo-root>
git status --short --branch
git rev-parse HEAD
git ls-remote fork refs/heads/fix/hdev-gateway-log-permissions
```

Do not compare against a hard-coded predicted final handoff SHA.

## Source of truth and branch state

- Repository: `hermes-agent`
- Working branch: `fix/hdev-gateway-log-permissions`
- Remote branch: `fork/fix/hdev-gateway-log-permissions`
- PR: `https://github.com/shokirunicus/hermes-agent/pull/3`
- PR base: `chore/hdev-v0.18.2-integration`
- Implementation commit: `443f3919ecbb5c7ff663673992a311bcce3cd390`
- PR #3 contained exactly the six implementation files before this handoff was added.
- PR #3 was OPEN and MERGEABLE when this memo was written.
- Merge is not authorized by this handoff.

The previous branch `fix/hdev-launchd-transient-retry` was already merged through PR #2. It was not reused. This new branch was created to preserve a clean review boundary.

Do not open the current operational branch directly against `NousResearch/main`. The official main branch is far ahead of the v0.18.2 integration base. An upstream contribution requires a separate clean port onto current official main, reproduction there, and new tests.

## What changed in Git

### macOS launchd log confidentiality

- launchd plist now uses decimal `Umask=63`, equivalent to POSIX `0077`.
- `gateway.log`, `gateway.error.log`, and `launchd-reload.log` are created or tightened to `0600`.
- The profile logs directory is created or tightened to `0700`.
- Existing files from older Hermes versions are repaired; the fix is not limited to newly created logs.
- Log paths are opened with `O_NOFOLLOW` when available and must resolve to regular files.
- File descriptor ownership and close behavior are covered for success and failure paths.

### Fail-closed launchd operations

The following operations stop before plist mutation, `launchctl`, or detached helper execution when log safety cannot be established:

- install
- refresh
- start
- restart

Regression tests use a real symlink log and prove that the target file and plist remain unchanged and no service subprocess runs.

### Detached reload safety

The detached launchd reload helper no longer appends with shell path redirection. Python safely opens `launchd-reload.log`, passes the already-validated descriptor through `pass_fds`, and the shell writes only to that inherited descriptor. The parent closes its descriptor in `finally`.

### Dependency remediation

Security-sensitive eager and lazy dependency declarations and `uv.lock` were aligned:

- `mcp==1.28.1`
- `pydantic-settings==2.14.2`
- `httplib2==0.32.0`
- `pyasn1==0.6.4`

The final `pyasn1` update resolves:

- `GHSA-8ppf-4f7h-5ppj`
- `GHSA-hm4w-wwcw-mr6r`

The existing general metadata contract verifies that exact pins shared by `pyproject.toml` and `tools/lazy_deps.py` do not drift.

## Git-managed implementation files

- `hermes_cli/gateway.py`
- `pyproject.toml`
- `tools/lazy_deps.py`
- `uv.lock`
- `tests/hermes_cli/test_gateway_service.py`
- `tests/tools/test_computer_use.py`
- `CONTINUATION_MEMO_2026-07-22_hdev-p0-security-closeout.md` — this final continuation record

Generated `build/` output was removed and is not part of the savepoint. Virtual environments, logs, databases, backups, credentials, and profile configuration are not tracked by this repository.

## Local runtime changes outside Git

These are live hdev profile/runtime changes and are not fully represented by the Git commit:

- `~/.hermes/profiles/hdev/config.yaml` migrated from schema v30 to v33.
- `agent.verify_on_stop: false` was materialized by migration.
- deprecated `delegation.max_async_children` was removed while the supported concurrency setting was retained.
- `hooks_auto_accept` is `false`.
- shell Hook allowlist contains zero approvals.
- two obsolete profile aliases, `test-prof-2` and `soul-prof`, were backed up and removed.
- `state.db` is `0600`.
- logs directory is `0700`.
- top-level Gateway/reload logs are `0600`.
- hdev Gateway environment is installed from this worktree in editable mode.
- Local STT dependency is present and importable.
- current dependency audit reports zero findings.

Local remediation backup entrance:

- `~/.hermes/profiles/hdev/backups/p0-remediation-20260720-215442/`

Do not publish backup contents; they can include machine-specific operational state.

## Shell Hook isolation — critical boundary

Configured Hook commands:

- `auto-backup-before-change.cjs`
- `pdca-destructive-guard.cjs`

Current state:

- configured: 2
- approved: 0
- `hooks_auto_accept: false`
- runtime behavior: neither Hook fires

Independent review found these blocker classes:

1. command executors can self-assert external-send approval with an environment variable;
2. external mutations such as generic HTTP POST, GitHub API mutation, mail send, release creation, and some secret operations are not comprehensively classified;
3. destructive-operation backup proof can be self-generated without proving it corresponds to the target data or is restorable;
4. malformed JSON and empty Hook input fail open;
5. shell expansion and large-glob forms can bypass backup targeting;
6. shared policy integrity is not independently protected.

Do not run Hermes with `--accept-hooks` for these commands and do not set `hooks_auto_accept: true`. Hook redesign belongs in the separate tools repository and requires RED tests, fail-closed parsing, server-side/human-bound approval evidence, artifact binding, and a new independent hostile review.

`hermes hooks doctor` currently reports two issues because the configured Hooks are deliberately unapproved. This is expected isolation evidence, not permission to approve them.

## Verification actually run

### Independent review

- First final reviewer verdict: HOLD because install/refresh ignored secure-log failure and the detached helper reopened a path.
- Fix: common fail-closed guard for install/refresh/start/restart plus secured inherited fd logging.
- Follow-up reviewer verdict: PASS; no commit blockers.
- Earlier review blockers covering existing 0644 logs and detached fallback were also converted into regression tests and fixed.

### Local tests and static gates

- focused launchd, metadata, and lazy dependency suite: `68 passed`
- broader touched test command: `206 passed, 6 failed`
- the six failures are existing Linux systemd user-D-Bus preflight tests executed on macOS; they were present before this final patch and are outside the launchd/dependency diff
- Ruff on changed Python files: PASS
- `git diff --check`: PASS
- `uv lock --check`: PASS
- wheel build to an OS temporary directory: PASS
- changed-line secret/dangerous-code scan: no findings
- `pip check`: no broken requirements
- Google auth import with `pyasn1 0.6.4`: PASS
- Hermes security audit: 137 components scanned, 0 findings

### Live runtime checks

- hdev Gateway: launchd-supervised and running at closeout
- launchd umask: `0077`
- `state.db`: `0600`
- logs directory: `0700`
- `gateway.log`: `0600`
- `gateway.error.log`: `0600`
- `launchd-reload.log`: `0600`
- MCP `maestro`: connected, 9 tools
- MCP `payment-control-plane`: connected, 1 tool
- MCP `multi-venture-revenue-os`: connected, 1 tool
- Hook approvals: 0

The Gateway is a persistent product service and was intentionally left running. No temporary development server was started.

## PR and CI

PR #3 is the required review surface because this change modifies a security boundary and dependency pins. It targets the user fork's established v0.18.2 integration branch, not official upstream main.

The implementation push triggered CI. At memo creation, checks were still running. The final operator must inspect the exact latest PR head SHA after this handoff commit and must not reuse the implementation commit's earlier CI result as proof for the final head.

Useful live checks:

```bash
cd <repo-root>
SHA=$(git rev-parse HEAD)
gh pr view 3 -R shokirunicus/hermes-agent --json state,mergeable,statusCheckRollup,url,headRefName,baseRefName
gh run list -R shokirunicus/hermes-agent --commit "$SHA"
```

## Intentionally not enabled or performed

- custom shell Hooks were not repaired or re-enabled
- PR #3 was not merged
- no official upstream PR was opened
- no force push, reset, clean, or history rewrite was used
- no public deployment or release was performed
- no customer contact, public posting, billing, charging, or live checkout was performed
- no credentials or secret values were recorded in Git or this handoff
- optional web-search and Computer Use backends were not installed merely to silence Doctor warnings

## Rollback and pause

### Pause safely

- Leave PR #3 open and unmerged.
- Keep `hooks_auto_accept: false` and Hook approval count at zero.
- Keep the Gateway running unless a maintenance window explicitly requires a restart.

### Revert the Git change after merge or local adoption

First verify the live commit range; then use a normal revert, not reset or force push:

```bash
cd <repo-root>
git log --oneline --decorate -5
git revert <implementation-or-merge-commit-sha>
```

Do not deliberately broaden log permissions back to `0644`; owner-only permissions are safe even if code is rolled back.

### Local profile recovery

Use the local remediation backup entrance listed above. Never restore `.env`, auth files, or profile configuration by copying from an unverified archive. Compare structure and permissions first, and do not print secret values.

## Remaining work

### Required before merge

1. Confirm the final continuation memo commit is pushed and PR #3 contains only the seven intended files.
2. Wait for CI on the exact final PR head SHA.
3. If CI fails, inspect the exact job and distinguish product failure from pre-runner/account failure.
4. Do not merge without explicit BOSS approval.

### Separate future work

1. Redesign the two custom Hooks in the tools repository and keep them disabled until hostile review passes.
2. If contribution to official Hermes is desired, port only the generic launchd log hardening onto current `NousResearch/main`, reproduce on that code, and open a separate clean upstream PR.
3. Decide separately whether the six macOS-triggered systemd test failures should be repaired upstream; do not mix them into this security PR unless current-main reproduction shows the same defect.

## Next smallest safe action

Review CI for PR #3 at its final head SHA. If all required checks pass, stop and wait for explicit merge approval. Do not start Hook redesign or upstream porting in the same closeout.

## Copy-paste restart prompt

```text
Resume the hdev Hermes P0 security closeout. Locate the live hermes-agent checkout, then read AGENTS.md and CONTINUATION_MEMO_2026-07-22_hdev-p0-security-closeout.md before changing anything. Verify branch fix/hdev-gateway-log-permissions, local/remote SHA equality, PR #3 file list, and exact-head CI. Keep both custom shell Hooks unapproved with hooks_auto_accept=false. Do not merge PR #3, reapprove Hooks, update official upstream, restart the Gateway, or modify credentials unless BOSS explicitly approves that specific action. If CI is green, report readiness and stop. If CI fails, inspect only the exact failing job and make the smallest causal fix on the same PR.
```
