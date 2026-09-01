# SSH Remote Journal Reconciliation Validation — 2026-08-30

## Scope

Phase 4のdisposable SSH target `llm-manager-gate`（Ubuntu 26.04、host `Ubuntu-dev`）で、production helper compatibility Gate、`OpenSshRemoteJournalPort`、`RemoteJournalReconciler`を通したroot journal evidence取得とread-only target照合を検証した。

Gate専用operation `journal-gate-20260830`のcanonical evidenceだけを`/var/lib/llm-manager/journals/evidence`へroot:root 0700/0600で配置した。製品のjournal readerにはwriterを追加せず、外部端末で特定operation ID/request hashの固定read commandだけを一時NOPASSWD許可した。SSH、systemd、Ollama、OpenCode設定と既存backup/keyは変更していない。

## Result

| Observation | Result |
|---|---|
| Remote helper | 0.1.0~dev0、compatibility `ready` |
| Canonical evidence | 928 bytes、取得成功 |
| Evidence binding | operation/plan/host/fingerprint/change-set/backup/manifest/request/status/target一致 |
| Remote host identity | `ssh:llm-manager-gate` / known fingerprint一致 |
| Target observation | actual hashとbefore hash一致 |
| Reconciliation | `unapplied` |
| Mutation retry | Apply/rollbackとも未実行 |

照合後にGate専用root evidence、空のjournal directory、一時sudoers、user `/tmp`ファイルを削除した。削除後はevidenceとsudoersが不在、通常の`sudo -n`が拒否、同じproduction journal取得が`remote_journal_failed`となることを確認した。

## Closure status

後続のDebian 13 package/desktop GateとUbuntu 26.04 local package/desktop Gateで残存差異を確認した。Phase 4 closure判定は[closure audit](phase4-closure-audit-2026-09-01.md)を参照する。
