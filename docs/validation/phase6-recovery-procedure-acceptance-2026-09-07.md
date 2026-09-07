# Phase 6 recovery procedure acceptance review — 2026-09-07

## Scope and result

The user recovery guide was reviewed against the implemented Apply, dual-copy
backup and manual-restore state machines for four required cases:

| Case | Required user boundary | Result |
| --- | --- | --- |
| Apply `recovery_required` | stop mutation and cleanup, preserve evidence, compare current target with before/after hashes | documented |
| Restore `failed` | treat terminal failure evidence as requiring attention; do not infer target or service health | documented |
| Restore `unknown` | do not retry because mutation may have occurred or terminal persistence may have failed | documented |
| One-side copy/key loss | preserve the healthy copy, manifest, receipt and key; do not recreate the missing side under the same identity | documented |

The guide continues to prohibit passwords in the GUI or command arguments,
plaintext secrets in support records, package purge as recovery, and direct use
of unpublished restore helpers. It distinguishes read-only immutable-result
reconciliation from mutation retry.

## Implementation evidence

- local and privileged Apply coordinators return `RECOVERY_REQUIRED` when
  rollback or its durable evidence cannot be confirmed;
- SSH Apply reconciliation reads only the exact immutable result and never
  authorizes automatic Apply replay;
- local-user restore consumes the authorization once and persists `FAILED`
  evidence for pre-mutation rejection without retry;
- local-root restore records `FAILED` for a known terminal service-validation
  failure and `UNKNOWN` after mutation-side uncertainty, and rejects replay once
  an attempt exists;
- dual-copy backup uses independent local and remote keys and binds manifests,
  receipts, copy hashes and host fingerprint; missing or inconsistent evidence
  fails closed rather than being treated as absent.

## Verification

Focused tests cover Apply rollback failure, SSH reconciliation, local-user
restore failure/replay, local-root failed/unknown persistence, status lookup,
backup crypto authentication and dual-copy integrity. The documentation review
does not publish any unavailable restore route and changes no package, backup,
key, target, service, PolicyKit policy or SSH configuration.

The focused run executed 81 tests: 80 passed and the explicit Secret Service
desktop Gate was the one expected skip. `git diff --check` passed after the
guide, checklist, traceability and handoff updates.
