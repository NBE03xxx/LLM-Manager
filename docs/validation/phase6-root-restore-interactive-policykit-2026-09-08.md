# Phase 6 local-root restore interactive PolicyKit Gate — 2026-09-08

## Decision

Publish the local-root manual-restore workflow in the production GUI. Keep local-root
Apply and both SSH restore routes fail closed. The installed restore implementation
completed the remaining active-desktop PolicyKit boundary with exact immutable
result reconciliation.

## Artifact and environment

- source commit: `9fe071d`
- package: `llm-manager_0.1.0~dev0_all.deb`
- SHA-256: `6e2a70515f38554bc35e5151ff6cc847fc26d4a2d864ba0226c975925d89d984`
- guest: Ubuntu 26.04.1 LTS, active local Wayland session 3, UID 1000, seat0
- package verification: all 790 build tests and `packaging/verify-deb.sh` passed
- isolation: internal VM snapshot `llm-manager-policykit-gate-20260908`

The first source-archive extraction inherited host `umask 0002`, turning indexed
0755 scripts into 0775 files and correctly failing five source-mode tests. A fresh
archive was extracted with `umask 0022`; indexed/worktree modes were independently
confirmed as 0755 before the successful build. Release build instructions now state
this mode requirement.

## Interactive authorization evidence

The package was installed only inside the disposable snapshot. Both installed
actions had fixed executable annotations, `allow_any=no`, `allow_inactive=no`, and
`allow_active=auth_admin`.

The normally logged-in user completed these desktop operations without sharing or
transporting a password:

1. cancelled `restore-review list`; `pkexec` returned 126;
2. authenticated `restore-review list`; the helper returned the expected
   `restore_review_unavailable` before provisioning;
3. cancelled `restore-execute` with a noncanonical dummy request; `pkexec` returned
   126 and the target, store and service remained absent;
4. authenticated the same dummy request; the dedicated helper returned
   `invalid_root_restore_request`, proving fail-closed dispatch;
5. authenticated inventory preview, exact review approval, exact execution, and
   read-only status for a valid five-minute request.

The successful request was:

```text
request_id   phase6-policykit-restore-ready
request_hash 3e5fcea00d06ee7fab8f34a3938ba13900b4bdd3e23974c0deb2d7b639e6fa1a
attempt_hash e10bcd6ee9ca06e918af9042a9cbb04b04b07bd6bfe6e11c92ded730d6ca39f7
state        committed
attention    false
```

## Mutation and reconciliation

The fixture used the fixed production Ollama drop-in, encrypted root-owned origin
evidence, a disposable `ollama.service`, and a loopback API reporting version
`0.33.2` and an empty model list. It did not install or modify a real Ollama runtime.

The first exact approved request used a `Type=simple` fixture. The immediate API
probe raced socket readiness and produced an immutable
`service_validation_failed` terminal result. The request was not retried. Post-state
showed that the fixed target had been restored and the service/API subsequently
became healthy. A distinct backup and request then used `Type=notify`, making socket
readiness part of systemd startup completion; that request committed.

Final verification established:

- fixed target SHA-256
  `391a06e89a7a33b0402ca88d85541d8d12dad8a22c24ed238a4246a5b183bde1`;
- target metadata root:root 0644;
- service `loaded`, `active`, `running`, with the restored literal environment;
- HTTP 200 and strict schema for `/api/version` and `/api/tags`;
- review, attempt, and result files root:root 0600;
- a valid four-event audit chain: failed request start/finish followed by committed
  request start/finish;
- interactive read-only status returned the same committed request/result with
  `requires_attention=false` and exit 0.

The readiness race was a disposable fixture issue, not treated as authority to add
automatic retry to production. The recorded failure additionally confirmed the
terminal evidence and no-retry boundary.

## Cleanup and publication boundary

After shutdown, the VM reverted to the pre-Gate snapshot. A verification boot
confirmed package `0.1.0~dev0-1`, no root restore state, no target/drop-in/unit,
no Gate server or transferred files, an inactive absent Ollama service, and no port
11434 listener. The VM was shut down again and the temporary snapshot deleted.
Debian 13 remained shut off throughout.

Production composition now explicitly enables `RestoreRoute.LOCAL_ROOT` alongside
`LOCAL_USER`. The availability service default remains an empty fail-closed set;
SSH user/root restore remain unavailable, and local-root Apply remains blocked by
`local_root_apply_rule_pending`.

After publication, the host suite passed all 790 tests (752 passed, 38 expected
PySide6 skips), plus compileall, packaging shell syntax, desktop validation and
diff checks. A fresh `umask 0022` deb build passed its embedded suite and
`packaging/verify-deb.sh`; SHA-256 was
`7da8c5965e0c4e205dad1a82a6cf1cfdd21dae4d9b4f6fdc8479fa96a6876e3c`.
Archive inspection confirmed the published `LOCAL_USER` plus `LOCAL_ROOT` set in
the packaged production entrypoint. This remains a `dev0`/`UNRELEASED` artifact,
not a public release artifact.
