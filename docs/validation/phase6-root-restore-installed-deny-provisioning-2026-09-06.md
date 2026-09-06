# Phase 6 installed root restore deny/provisioning Gate — 2026-09-06

## Scope

This Gate checks the freshly packaged local root restore boundary on the existing
Ubuntu 26.04 VM without authorizing or executing a restore. It covers installed
files, PolicyKit registration and denial, privileged entry rejection, and explicit
key provisioning inside a temporary root-owned directory.

The normal GUI route remains unpublished. No valid restore request was submitted.

## Artifact and isolation

Two independent out-of-tree builds produced the same development deb SHA-256:

```text
8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64
```

`packaging/verify-deb.sh` passed for both builds. The package is
`llm-manager 0.1.0~dev0`, distribution `UNRELEASED`, architecture `all`.

The Ubuntu VM started `shut off`. A temporary internal snapshot protected the
existing state. Before the Gate it contained the older Gate package
`0.1.0~dev0-1`; both the fixed Ollama target and
`/var/lib/llm-manager/local-root-restore` were absent.

## Installed checks

The new package was installed inside the snapshot. These checks passed:

- `dpkg -V llm-manager` reported no differences.
- review and execute launchers were root-owned 0755.
- the PolicyKit policy and both manpages were root-owned 0644.
- installed isolated imports succeeded for the execute client, execution session,
  and Qt execution dialog.
- `pkaction --verbose` reported two distinct actions. Review was bound only to
  `/usr/bin/llm-manager-restore-review`; execution was bound only to
  `/usr/bin/llm-manager-restore-execute`. Both use `auth_admin` only for an active
  session and deny inactive/other sessions.
- with `--disable-internal-agent` in the inactive SSH session, both PolicyKit calls
  exited 127, emitted zero stdout bytes, and did not start either helper.
- direct root entry tests used the installed isolated launchers with a synthetic
  `PKEXEC_UID=1000`. Invalid review input returned only
  `invalid_restore_argument`; a noncanonical execution request returned only
  `invalid_root_restore_request`. Both exited 1 before production composition.

## Temporary key provisioning

The installed provisioning module ran as root through QEMU guest agent against a
new 0700 directory under `/tmp`. It created only one key and ready marker, both
root-owned 0600, reloaded the same 32-byte key, rejected duplicate provisioning as
`root_key_exists`, and deleted the temporary directory on completion. Key bytes
were never printed or copied from the VM.

After the checks, the production root restore state and fixed Ollama target were
still absent. The deb, Gate script, denial output, and temporary key directory were
removed.

## Cleanup and limits

The VM was shut down, reverted to the temporary snapshot, and booted once to verify
the original `0.1.0~dev0-1` package, absent target, absent production root state,
and absent Gate artifacts. It was then shut down and the temporary snapshot was
deleted. The pre-existing snapshot list was restored and the VM ended `shut off`.

This Gate does not cover an active desktop PolicyKit prompt, a valid approved
request, real backup/key material, Ollama file mutation, service restart, or
post-restore validation. Those require a separately constructed disposable OS
fixture and remain closed in production.
