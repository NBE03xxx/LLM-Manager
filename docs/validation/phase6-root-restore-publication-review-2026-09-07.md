# Phase 6 local-root restore publication review — 2026-09-07

## Decision

Keep the production `LOCAL_ROOT` manual-restore route unavailable. The
implementation is registered in the normal Backup / Rollback window, but the
production availability allowlist intentionally contains only `LOCAL_USER`.
The system-restore control therefore stops before inventory I/O with
`local_root_restore_release_gate_pending`.

This is a publication decision, not a rollback of the completed root-restore
implementation. The dedicated inventory, review, execute, status, audit,
target-lock, origin-capture, provisioning, immutable-result and Qt workflow
boundaries remain packaged and testable. Publication requires evidence for the
remaining active-desktop PolicyKit boundary.

## Code and package review

| Boundary | Evidence | Result |
| --- | --- | --- |
| Production allowlist | `qt_app.main()` constructs `AssessProductionRestoreAvailability(frozenset({RestoreRoute.LOCAL_USER}))` | `LOCAL_ROOT` remains unavailable |
| Default construction | `MainWindow._root_restore_route_unavailable()` creates an empty availability service when none is supplied | fail closed |
| Host boundary | the root check calls `execute(host.kind, True)`; SSH maps to `SSH_ROOT` and is rejected | no SSH fallback |
| I/O ordering | `_open_root_restore()` checks root availability before invoking the workflow callback | disabled before inventory I/O |
| Explicit test activation | runtime tests require both a registered callback and an allowlist containing `LOCAL_ROOT` | no accidental activation |
| Privilege separation | review and execute use separate fixed PolicyKit actions and isolated `/usr/bin/python3 -I` launchers | GUI is not run as root |
| Policy defaults | both restore actions use `allow_any=no`, `allow_inactive=no`, `allow_active=auth_admin` | inactive sessions denied |
| Package verification | `packaging/verify-deb.sh` checks both fixed action paths, launchers, modes and package ownership | packaged boundary covered |

The completed Ubuntu offscreen Qt Gate already covers the disabled production
entry, explicit test-only activation, SSH rejection and localized status. The
installed deny/provisioning and disposable valid-request OS Gates cover the
privileged entries without claiming interactive authorization evidence.

## Remaining publication Gate

An active, normally logged-in desktop session is still required to record all
of the following against the installed development artifact:

1. review-action authentication prompt and explicit cancel;
2. review-action successful administrator authentication;
3. execute-action authentication prompt and explicit cancel without mutation;
4. execute-action successful authentication for an exact approved request;
5. resulting immutable status/evidence reconciliation and exact cleanup.

On 2026-09-07 the Ubuntu 26.04 VM was running, but guest-agent
`guest-get-users` returned no logged-in users. No password, synthetic desktop
login, PolicyKit policy, package, target, service, restore state, key or SSH
configuration was changed. Debian 13 was `shut off`. The host system SSH config
remained unsafe (`nobody:nogroup`, mode `0777`), so `ssh -F /dev/null` was not
used as production evidence.

Until the active-desktop Gate passes, the route must not be added to the
production allowlist and the recovery guide must continue to describe local
root manual restore as unavailable.

## Focused verification

The publication boundary was rechecked from commit `5d3a384` with 23 focused
tests covering route availability, production Qt composition, source-level Qt
separation, the execute CLI/PolicyKit package boundary and Debian packaging.
All 23 passed. `git diff --check` also passed after this documentation update.
