# Phase 6 installed setup and authenticated Apply capture OS Gate — 2026-09-06

## Scope

This Gate validates the packaged administrator setup entry and the production
local Apply origin-capture connection on Ubuntu 26.04. All package, key, backup,
receipt and target mutations occurred inside a temporary VM snapshot.

The VM began shut off with `llm-manager 0.1.0~dev0-1`, a safe root-owned 0755
`/var/lib/llm-manager` created by earlier helper use, and no local-root-restore
state, target drop-in or transferred artifact. The only pre-existing snapshot was
`phase4-pre-local-deb-20260831`.

## Artifact

The dev package was built from the current uncommitted Phase 6 source. Its build
ran 774 tests: 739 passed and 35 host-Qt skips. `packaging/verify-deb.sh` passed.

```text
llm-manager_0.1.0~dev0_all.deb
SHA-256 8e2897a083ab7b7ae86d7136cc8a2e58f41b84c2906ebd8d1e3c8b0530f73615
```

The host and VM matched this digest before the package replaced the older build
inside the snapshot.

## Installed setup Gate

Running `/usr/bin/llm-manager-restore-setup initialize` as UID 1000 returned the
canonical `root_required` failure and performed no initialization. An explicit
effective-UID-0 execution then returned `initialized` for fixed key ID
`local-root-v1`.

The installed entry created the fixed `keys`, `backups`, `executions` and `audit`
directories as root:root 0700 beneath a root:root 0700 restore directory. The key
and ready marker were root:root 0600. It accepted the pre-existing safe 0755
`/var/lib/llm-manager` parent without changing its mode.

A second initialize returned canonical `root_setup_existing_state`. The key digest
before and after matched. No key material was printed, rotated or replaced.

## Authenticated Apply origin capture Gate

A root-owned 0644 fixed drop-in was created as the original fixture. A canonical
local helper request bound UID 1000's PolicyKit identity, the VM hostname, approval,
backup ID, manifest, current hash and changed staged bytes. The user-owned staging
tree used 0700 directories and 0600 files. The installed
`/usr/bin/llm-manager-helper` ran once as root with synthetic `PKEXEC_UID=1000`,
matching the identity boundary used by the earlier installed PolicyKit Gates.

The helper returned `completed`. Before replacing the target it used the setup key
to publish root-owned 0600 evidence and ciphertext under the held target lock. The
installed reader and cipher verified the record binding and decrypted the original
bytes. The helper receipt was root-owned 0600 and terminal `completed`; the target
became the requested root-owned 0644 content.

Stable result:

```json
{"backup_id":"phase6-installed-backup-1","evidence_hash":"c94a697a733be8494f36163817e28c65a3991f62377cc82954e2b502b0bd678b","key_hash":"32b51a40965da2d9924ef811cb2c8bd98975be1e4ab025b647a99baf742f1851","original_sha256":"82ff1fcf582006def7fdf45c42f243961f75f1ba685247a870d48077db13204c","replay":"rejected","request_hash":"3d7339c3f9945f2e98a76590600e1f61ac9248a809b88aabf0f8e69927a9d6e2","result":"completed","target_sha256":"deb90d067dcd9436cd5a4e48eb0c88ff65e84b7fae81c985d1f01864bf9de3aa"}
```

Replaying the exact helper request returned canonical `replayed_request`. The
target and both backup files retained identical digests, proving no second capture
or write occurred.

## Cleanup and remaining boundary

Transferred files were removed, the VM was shut down and the temporary snapshot
was reverted. After a verification boot, the VM again contained
`llm-manager 0.1.0~dev0-1`; the restore state, target drop-in and Gate artifacts
were absent, and `/var/lib/llm-manager` was again root-owned 0755. The VM was shut
down, the temporary snapshot deleted, and the pre-existing snapshot list restored.

This Gate invoked the authenticated installed helper with a synthetic PolicyKit
caller identity through QEMU guest agent. It proves the helper-side identity,
setup and capture connections but does not claim an active-desktop authentication
prompt result. Normal GUI root availability remains disabled. Cross-request
locking across external validation and a later rollback, normal GUI inventory and
review-to-execute connection, interactive PolicyKit, and completed-flow supported-OS
Gates remain outstanding.

No host configuration, service, key or package was changed. Existing workspace
changes remain uncommitted. Current and next work is Phase 6.
