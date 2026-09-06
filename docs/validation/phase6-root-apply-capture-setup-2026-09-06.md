# Phase 6 authenticated Apply origin capture and explicit setup — 2026-09-06

## Connection and contract

The production local `run_helper` path now validates local host identity and
complete approval/backup/manifest bindings for every ATOMIC_REPLACE request.
It accepts a single replacement followed by optional reload and restart, rejecting
service-before-capture and mixed/multiple file operations before claiming a receipt.
The existing PolicyKit Apply action remains the authentication boundary; no
restore or setup authorization is inferred from a request hash.

After claiming the existing replay receipt, the executor takes the target lock,
checks current bytes and staged content, and passes the same borrowed target
directory FD to the production origin-capture adapter. It reads the fixed existing
`local-root-v1` key, captures original bytes directly, encrypts with existing AEAD
bindings, verifies the round trip, and durably publishes evidence before writing.
The key is required even for an absent original. No key or store is auto-created.
Expiry and before-hash are checked again after capture, before replacement.
The lock remains held through the request's declared service operations.

Missing keys, invalid staging, capture failure and expiry stop the write.
Partial or complete capture evidence is retained, and the claimed receipt blocks
replay. A retained origin proves what was captured, not successful Apply completion.
Existing rollback operations do not create another origin or require the capture
key; their previous validation remains in effect. Alternate backends are the
existing internal test seam, not a CLI option to bypass production capture.

## Explicit administrator setup

The isolated `/usr/bin/llm-manager-restore-setup initialize` entry requires effective
UID 0. It accepts no path, key material, key ID, rotation or repair parameters.
It is an explicit administrator command with no PolicyKit action or GUI launcher.
It is not called during package installation or any normal read/Apply/restore.

Starting at securely opened `/var/lib`, it creates only fixed private directories
under `llm-manager/local-root-restore`: keys, backups, executions and audit.
No-follow FD-relative opens and root:root 0700 checks reject unsafe existing paths
without repairing their ownership or mode. An exclusive state-directory lock
serializes setup, then all four directories must be empty before generating the
fixed 32-byte key and ready marker with the existing publication protocol.

Existing keys, surviving backup/history, unknown entries and partial key publication
are refused and preserved. Empty directory-only partial initialization can be
retried. Removing evidence to force initialization is not an implemented recovery
procedure. Key loss still requires administrator-led recovery of the original key.

## Validation

15 new tests use temporary real files, key provisioning, encryption/decryption,
the helper entry and receipts, and real flock contention. They cover capture before
write, shared lock through capture/service, replay refusal, missing key even on
first creation, partial publication, expiry after capture, staged-content tampering,
host/binding/order rejection, rollback behavior, setup races, unsafe paths, surviving
evidence, interrupted keys, root guard and bounded CLI errors.

The final fresh dev build ran 774 tests: 739 passed, 35 skipped because host Qt is
unavailable. Compilation, shell syntax, desktop validation, SBOM JSON parsing and
diff whitespace checks passed. The deb verifier passed, including the setup
entry's root ownership, 0755 mode and isolated Python launcher. Manpages are included.

Artifact: `llm-manager_0.1.0~dev0_all.deb`, SHA-256
`8e2897a083ab7b7ae86d7136cc8a2e58f41b84c2906ebd8d1e3c8b0530f73615`.
Build output is retained at `/tmp/llm-manager-capture-setup-build-2qo6twq0/`.
An intermediate build was accidentally invoked in the worktree and refused its
parent-directory artifact write; `debian/rules clean` removed its build products.
The final successful build ran in the isolated temporary copy.

## Remaining Gates

Normal GUI root availability remains disabled. This slice does not complete the
cross-request transaction across external Apply validation and later rollback,
root backup inventory/selection and review-to-execute GUI connection, or the
interactive desktop PolicyKit and completed-flow OS Gates. The new installed
setup and authenticated capture path passed its
[disposable Ubuntu OS Gate](phase6-root-apply-capture-installed-os-gate-2026-09-06.md).
The previous restore execution OS evidence used fixture provisioning/capture; the
new Gate closes that product connection without changing normal GUI availability.

No real configuration, service, key, package or VM was changed. Existing edits
remain uncommitted. Current and next work is Phase 6.
