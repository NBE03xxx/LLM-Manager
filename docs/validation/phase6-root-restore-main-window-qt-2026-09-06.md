# Phase 6 root restore gated main-window and Ubuntu Qt Gate — 2026-09-06

## Scope and route boundary

The normal Backup / Rollback page now registers a separate system-restore
control and the production composition supplies the completed three-dialog root
restore workflow. The control performs an independent `requires_root=True`
availability check for the selected host before calling the workflow. It rejects
SSH hosts even when no availability service is supplied.

Production still allowlists only `LOCAL_USER` restore. `LOCAL_ROOT` is not in the
allowlist, so the registered system-restore control is disabled before inventory
I/O and explains that supported-OS and publication Gates are pending. Enabling
the route in a test requires both the explicit `LOCAL_ROOT` allowlist and a
registered workflow callback. The existing local-user backup inventory and
restore controls retain their independent availability check.

The previous `local_root_restore_protocol_missing` refusal text was no longer
accurate after the dedicated inventory, review, execution, audit, PolicyKit and
installed OS Gates. The fail-closed reason is now
`local_root_restore_release_gate_pending`; this changes no production allowlist.

## Qt timing defect found by the OS Gate

The first Ubuntu 26.04 run exposed a pre-existing sub-millisecond expiry defect.
The change-plan timer truncated a positive remainder to zero, synchronously
called the expiry handler, observed that the plan was still live, and recursively
rescheduled until `RecursionError`. The scheduler now expires only a non-positive
remainder and otherwise starts a timer of at least 1 ms. A focused runtime and
source-boundary regression test cover the condition.

## Validation

Host full suite after the fix: 789 tests, 751 passed and 38 skipped because host
PySide6 is unavailable. Compilation, local and remote package shell syntax,
desktop validation, both direct SBOM JSON parses, and `git diff --check` passed.

A fresh workspace-external dev deb build ran the same 789-test package Gate and
passed `packaging/verify-deb.sh`. Inspection of the extracted package confirmed
the registered workflow, separate system-restore control, release-pending reason
and sub-millisecond timer fix:

```text
llm-manager_0.1.0~dev0_all.deb
SHA-256 0ee77ebd3389e0120d3c037dd48c3246a0c90adda4b4190532277a62f21913d5
```

It remains a `0.1.0~dev0 / UNRELEASED` development artifact and was not installed.

Ubuntu 26.04 was started from the prior `shut off` state. Guest-agent inspection
found only the UID 1000 systemd manager session (`Type=unspecified`, no seat or
display) plus the GDM greeter, so no interactive PolicyKit authentication was
attempted and no password or synthetic desktop login was used.

The current source artifact was transferred only to a fixed `/tmp` directory and
verified on both sides:

```text
SHA-256 63a7887ec1550ea613ba0fb4ee29fdbffbef5ad2c3092bcef510907e6787e82c
```

Under UID 1000 with Python 3.14.4, PySide6 6.10.2 and the offscreen Qt platform,
the main-window runtime, root inventory session, root review dialog and root
execution dialog suites ran 42 tests: 40 passed and the two inverse
"PySide unavailable" boundary tests were expected skips. This covered the new
disabled production entry, explicit allowlist activation, SSH rejection,
localized accessible status, existing layout/close behavior and the 1 ms expiry
regression.

The guest artifact and host transfer artifact were removed, the temporary HTTP
server was stopped, and absence was verified in the guest. The isolated build
copy and extracted package inspection were also removed after verification. No package, target,
root restore state, service, key, SSH setting or PolicyKit policy was changed.
Ubuntu was returned to `shut off`; Debian remained `shut off` throughout.

Current and next work remains Phase 6. The remaining root-route Gate is active
desktop interactive PolicyKit prompt/authentication/cancel behavior, followed by
final publication review. The route remains unavailable until those checks pass.
