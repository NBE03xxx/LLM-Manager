# Phase 6 root restore inventory and workflow handoff — 2026-09-06

## Transaction lock decision

The privileged Apply and root restore entries remain one-shot authenticated
processes. This slice does not keep either privileged process alive across GUI
runtime validation or a later rollback request merely to retain an advisory lock.
Doing so would enlarge the elevated lifetime, couple authentication to an
unbounded external check, and still would not exclude administrator or older-tool
mutations that do not participate in the flock.

The production contract therefore remains fail closed at each request boundary:
the Apply request captures its origin and writes under one target lock; immutable
receipts prevent replay; post-capture expiry and before-hash are rechecked; a
separate rollback must match the exact post-Apply hash; mismatch or an unconfirmed
transition becomes `RECOVERY_REQUIRED`. This is deliberate serialization of each
mutation, not an atomic transaction across external validation and rollback.
Normal root GUI availability remains disabled while this scope and the completed
workflow receive supported-OS review.

## Bounded root inventory

`RootBackupEvidenceReader.list_inventory` now holds a shared store lock and returns
at most 32 records sorted by backup ID. It validates the private directory, every
canonical record and required payload, and the exact entry set before and after
the read. Orphan payloads, pending or unknown files, malformed IDs, missing pairs,
entry changes and excessive counts reject the entire inventory. Results are never
silently truncated.

The returned summary contains only backup ID, host, capture time, original fixed
file state, evidence hash, source Apply request hash and source manifest hash. It
does not expose ciphertext hash, key ID, payload bytes or key material.

The dedicated review CLI adds a no-argument `list` command. It independently
resolves the PolicyKit caller and local host, opens only the fixed backup store,
and filters summaries to that host. It does not open the key, current target or
execution store. The existing 32 KiB canonical response boundary remains in force.
The non-privileged client validates the exact schema, host, bounded length, sorted
unique IDs, timezone-aware timestamps, file metadata and all hashes.

## Explicit GUI workflow handoff

`RootRestoreInventorySession` binds review and execution clients to the same UID
and host. Inventory loading is one-shot per session. Empty, failed or invalid
inventory cannot select a backup. A selected summary only creates a review
session; it is not approval or mutation authority.

An explicit Qt inventory dialog loads metadata asynchronously, displays one
selected backup, and closes safely while loading. The existing review dialog can
show a Continue control only when constructed for this workflow and only after a
saved, still-live exact review. The workflow then creates a final execution
session from that same review client and request. Final execution still requires
the existing separate exact-hash consent checkbox. Closing any dialog stops the
handoff. No automatic retry or automatic dialog transition was added.

The production workflow exists as an explicit factory but is not registered in
the normal menu or production route allowlist. This keeps the new path reviewable
without publishing it before Qt and interactive PolicyKit Gates.

## Validation

11 new tests cover stable inventory, no sensitive metadata, orphan/unknown/partial
entries, mutation during read, cancellation, the 32-item bound, CLI fixed-store
composition, real CLI-to-client decoding, forged responses, one-shot session
state, identity binding and exact review-to-execution handoff.

Full host suite: 785 tests, 750 passed and 35 skipped because host PySide6 is
unavailable. Compilation, local and remote package shell syntax, desktop
validation, both SBOM JSON parses and `git diff --check` passed.

A fresh dev deb build ran the same 785 tests and passed
`packaging/verify-deb.sh`. Artifact:

```text
llm-manager_0.1.0~dev0_all.deb
SHA-256 60c21311c9952ad7d3b557a12112ef74d6c351e7dc3cf714c1c253ad923f637a
```

The artifact has not been installed. The isolated build remains under
`/tmp/llm-manager-capture-setup-build-2qo6twq0/`. A mistakenly started worktree
build was stopped before artifact creation and its generated files were removed
with `debian/rules clean`; the final build used the isolated copy.

No VM, real configuration, service, key or package was changed in this slice.
Existing workspace changes remain uncommitted. Current and next work is Phase 6:
gated main-window registration followed by supported-OS Qt layout/close and active
desktop PolicyKit prompt/cancel tests. The route remains unavailable until those
Gates and final publication review pass.
