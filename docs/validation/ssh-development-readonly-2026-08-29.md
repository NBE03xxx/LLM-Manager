# SSH `development` Read-only Integration Validation — 2026-08-29

## Scope

system OpenSSHのalias `development`を使用し、`BatchMode=yes`でPhase 2 Adapterをread-only統合確認した。sudo、設定変更、service操作、model実行、model downloadは行っていない。credential値、設定本文、base URL、model名は保存しない。

## Environment and result

| Item | Observed result |
|---|---|
| Report | `complete` |
| Host | `Ubuntu-dev` |
| OS | Ubuntu 26.04 |
| Kernel | Linux 7.0.0-29-generic、x86_64 |
| CPU | QEMU Virtual CPU、4 logical / 4 physical cores |
| RAM | 7,714,041,856 bytes total |
| Display device | QXL paravirtual graphic card。専用VRAMはunknown |
| Ollama | 未導入、service not-found、loopback API unavailable |
| OpenCode | 1.18.18、JSONC parse warning 0 |
| OpenCode schema | provider 2、model 4、base URL 2、Ollama互換接続を検出 |
| SSH identity | system OpenSSHでED25519 host-key SHA256 fingerprintを検証済み（値は本記録では非表示） |

## Findings and decisions

1. OpenCode 1.18.18は初期検証基準1.18.25の周辺版であり、read-only解析には成功した。ただしfixtureと変更互換性検証がないため自動変更対象にはしない。
2. 非対話SSHのPATHにはユーザー専用OpenCode binaryが含まれなかった。Hostごとに検証済み絶対pathを明示追加できる許可リスト契約を追加した。
3. QXLの`VGA compatible controller`を`ATI`と部分一致するvendor誤判定を検出した。単語境界による判定へ修正し回帰testを追加した。
4. aliasはidentity proofではない。`ssh -G`のeffective hostname/port、known_hosts、実接続でネゴシエートされたED25519 fingerprintの一致を確認した。Adapterには検証済みSHA256 fingerprintだけを注入する。

## Remaining gates

- host-key解決処理の自動化とhost key変更時のstale report拒否test
- OpenCode 1.18.18 fixtureと1.18.25との差分評価
- Ollama導入済みSSHホストでのAPI/systemd/model診断
- Debian 13
