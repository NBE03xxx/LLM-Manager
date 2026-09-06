# Phase 6 local root restore route review — 2026-09-06

## Decision

Keep the normal GUI root restore route unavailable. The installed valid-request
OS Gate proves the executor with provisioned fixture evidence; an interactive
PolicyKit check alone will not complete the product route.

Source review found these remaining connections:

- `CaptureRootBackup` and `ProvisionLocalRootKey` have no production callers in
  `src/llm_manager`. The installed OS Gate created their inputs through a fixture.
  An explicit provisioning entry and authenticated Apply-side origin capture
  must be designed and connected before ordinary users can produce this evidence.
- `LocalSystemHelperBackend.locked` protects one helper request. Origin capture
  is not connected inside that interval, and external validation / a later
  rollback request do not share a transaction lock. The earlier target-lock
  Gate explicitly leaves this boundary open.
- `qt_app.py` enables only `RestoreRoute.LOCAL_USER`. The root review and final
  execution dialogs are separate explicit factories, not a normal inventory,
  selection, saved-review and final-consent workflow in the main window.
- Interactive desktop PolicyKit prompt/cancel and the completed GUI flow on
  supported OS environments remain unverified. Both VMs were read-only checked
  as `shut off` during this review and were not started.

Next implementation slice: define the authenticated Apply origin-capture and
explicit provisioning boundary, including the shared target-lock interval and
failure/reconciliation contract. Do not enable availability by adding the root
route to the allowlist before these connections and their Gates are complete.

## Transport correction

The execution client classified exit 126/127 before checking a timeout or late
cancellation. Consequently, conflicting transport evidence could produce a
pre-execution rejection and disable the session's status reconciliation path.

Timeout and cancellation now take precedence and raise the bound
`RootRestoreExecutionUnconfirmed`. Ordinary uninterrupted 126/127 outcomes retain
their existing classification. There is no automatic retry.

The regression failed before the fix in all four combinations (126/127 with
timeout/late cancellation). After the fix, the execute-client and execution-session
suites passed all 17 tests, including the actual CLI/temporary coordinator test.

Full host suite: 759 tests, 724 passed and 35 skipped (Qt runtime unavailable).
Compilation, local/remote packaging and launcher shell syntax, desktop validation,
both packaged SBOM JSON parses, and `git diff --check` passed. This does not replace
the supported-OS Qt or interactive PolicyKit Gates.

No installed deb was rebuilt for this change. The previous artifact hash remains
evidence for the previous source. No real configuration, service, key, package,
or VM state was changed. All work remains uncommitted; current and next work is
Phase 6.
