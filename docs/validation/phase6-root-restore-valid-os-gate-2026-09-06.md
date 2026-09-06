# Phase 6 valid local root restore OS Gate — 2026-09-06

## Scope

This Gate executes one valid, installed local root restore through the dedicated
privileged entry on Ubuntu 26.04. All mutation occurs inside a temporary VM
snapshot. The VM had no Ollama unit, listener, LLM-Manager drop-in, or production
root restore state before the Gate.

The Gate uses a disposable `ollama.service` and a separate loopback API fixture.
It validates real systemd reload/restart and the fixed `/api/version` and
`/api/tags` checks without changing a real Ollama installation.

## Artifact

The package was rebuilt from the current uncommitted Phase 6 source. Its build-time
758-test suite and `packaging/verify-deb.sh` passed. This third independent build
matched the two prior builds:

```text
llm-manager 0.1.0~dev0, UNRELEASED, architecture all
SHA-256 8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64
```

Host and guest verified the same SHA-256 before installation.

## Valid evidence and request

Installed modules created root-owned 0700 backup, key, execution, and audit
directories in the snapshot. The fixture then:

1. provisioned a root-owned 0600 key and ready marker;
2. captured and AES-GCM encrypted the original fixed drop-in;
3. changed the current drop-in to a different allowlisted literal setting;
4. recomputed the privileged review from the current target and encrypted origin;
5. saved the review and emitted its canonical five-minute request.

The request bound these target states:

```text
current  deb90d067dcd9436cd5a4e48eb0c88ff65e84b7fae81c985d1f01864bf9de3aa
original 82ff1fcf582006def7fdf45c42f243961f75f1ba685247a870d48077db13204c
request  131acbd76130388b53af27f186e1c12a7d79053a94b189392e3bc6faf3094bdf
```

## Execution evidence

The installed `/usr/bin/llm-manager-restore-execute` ran as root with the
snapshot user's synthetic `PKEXEC_UID=1000`. The entry decoded and revalidated the
exact canonical request, opened only fixed production paths, and returned a bound
`execution_recorded` result with state `committed`.

The Gate verified:

- the fixed target became the original hash and remained root-owned 0644;
- `systemctl daemon-reload` and restart of the disposable `ollama.service`
  completed, leaving it active/running;
- fixed loopback probes accepted version `0.33.2` and a model list;
- immutable review, attempt, and result files were root-owned 0600;
- the strict audit chain contained one start and one terminal event;
- read-only status reconciliation returned the same committed result without
  attention;
- replay of the exact request returned `root_restore_request_already_used`, left
  the target and persisted result unchanged, and performed no second restore.

Stable Gate output:

```json
{"audit_events":2,"replay":"rejected","result":"committed","service":"active","status":"committed","target_sha256":"82ff1fcf582006def7fdf45c42f243961f75f1ba685247a870d48077db13204c"}
```

## Cleanup and remaining boundary

Transferred artifacts and request metadata were deleted. After shutdown and
snapshot revert, the VM again contained the prior `0.1.0~dev0-1` package and had
no Ollama/Gate units, fixed target, root restore state, port 11434 listener, or
Gate artifacts. The VM ended `shut off`; the temporary snapshot was deleted and
the pre-existing snapshot list was restored.

This Gate exercised the installed privileged entry directly through QEMU guest
agent. It did not claim an interactive PolicyKit authentication result, and the
service/API were disposable fixtures rather than real Ollama. The production GUI
route therefore remains unpublished pending an active desktop PolicyKit prompt and
the final route/publication review.
