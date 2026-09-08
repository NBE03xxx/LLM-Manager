# Phase 6 local-root Apply refusal reason audit — 2026-09-08

## Finding and decision

The production local-root Apply route remains unavailable. Its previous stable
reason, `local_root_apply_composition_missing`, was no longer accurate: the
PolicyKit/helper, root Apply composition, target lock, encrypted origin capture,
rollback, immutable receipt and installed OS boundaries are implemented and
validated.

The actual publication blocker is the absence of an evidence-based actionable
Ollama recommendation in the production rule catalog. The allowlist describes
which settings a planner may accept, but its unverified numeric thresholds are
explicitly not recommendation evidence. Enabling flash attention, changing
cache format, retention or bind settings without hardware/runtime evidence
would exceed the safe rule boundary.

The refusal code is therefore now `local_root_apply_rule_pending`, with matching
English and Japanese UI text. This is a fail-closed accuracy change only:
`qt_app.main()` still excludes `ApplyRoute.LOCAL_ROOT` from the production
allowlist, and no rule, setting value, target, helper operation or package
boundary was expanded.

## Verification

`ProductionApplyAvailabilityTests` tracks all four route/reason pairs and the
explicit completed-route allowlist. A dedicated i18n regression test fixes the
English and Japanese rule-pending meaning. The full host suite ran 790 tests:
752 passed and 38 were expected skips because PySide6 is unavailable on the
host. Compilation, local and remote packaging shell syntax, desktop validation,
both direct SBOM JSON parses and `git diff --check` passed.
