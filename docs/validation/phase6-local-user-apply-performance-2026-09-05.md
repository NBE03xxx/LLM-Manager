# Phase 6 local user Apply複数sample Gate

## 範囲

2026-09-05、完成済みproduction `LocalUserApplyTaskFactory`を、host、Ubuntu 26.04、Debian 13で実行した。各sampleは新しい一時config/state rootだけを使用し、実OpenCode設定、Secret Service、systemd、SSHへ接続しない。

実compositionの次の境界を通した。

- AES-256-GCM local backupの作成と検証
- before hashとallowlistを使うatomic file Apply
- file/runtime validation
- local audit chainとoperation journal
- validation失敗後のrollback
- rollback失敗時の`recovery_required`

暗号処理そのものはproduction `AesGcmBackupCipher`を使用した。利用者のSecret ServiceへGate keyを作らないため、32 byteの固定test key providerを注入した。rollback pathはruntime validation失敗を注入し、`recovery_required` pathはさらにbackup restore失敗を注入した。

再実行:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 packaging/measure-local-user-apply.py
```

## 終端とevidence

各環境で`committed`、`rolled_back`、`recovery_required`を5回ずつ、計15 sample実行した。全45 sampleで期待した終端、暗号化backup 1件、journal 1件、audit HEAD、0700 state rootを確認した。

| 終端 | 最終target | host wall time | Ubuntu wall time | Debian wall time |
| --- | --- | ---: | ---: | ---: |
| `committed` | replacement | 1.489–3.118 ms | 1.663–5.141 ms | 1.644–5.665 ms |
| `rolled_back` | original | 1.852–1.941 ms | 2.155–2.219 ms | 2.054–2.646 ms |
| `recovery_required` | replacement | 1.631–1.675 ms | 1.929–2.043 ms | 1.787–2.201 ms |

process CPU範囲はhost 1.489–3.115 ms、Ubuntu 1.663–4.892 ms、Debian 1.644–4.993 ms。process累積peak RSSはhost 32,544 KiB、Ubuntu 49,900–50,028 KiB、Debian 31,216 KiB。

生データ: [host](phase6-local-user-apply-host-2026-09-05.json)、[Ubuntu](phase6-local-user-apply-ubuntu2604-2026-09-05.json)、[Debian](phase6-local-user-apply-debian13-2026-09-05.json)。

## Debian dependency lifecycle

Debian VMは製品未導入のため`python3-cryptography`がなく、最初の実行はimport前に停止した。APT candidate `43.0.0-3+deb13u1`を確認し、正式debのruntime依存を再現するため次の3 packageだけを一時導入した。

- `python3-cryptography`
- `python3-bcrypt`
- `python3-cffi-backend:amd64`

測定後に3件を明示purgeした。導入前2236 packageとの比較はadded `[]`、missing `[]`。Gate用config/stateは一時root内だけであり、purge後に一時rootも削除した。

## 限界とcleanup

単一小容量OpenCode JSONを、warm filesystem上の一時rootへ適用したmicrobenchmarkである。Secret Service、実OpenCode process、外部I/O、Qt表示、ユーザー操作時間を含まず、release SLOやhardware全体の性能保証には使わない。特に`recovery_required`の短い時間は復旧が軽いことを意味せず、意図的に復元失敗を即時返すGateの値である。

artifact SHA-256は `c720bc41c0b557ad2a189255307c4976dd86f1628bce4b63ba54ec9036e61f7c`。host/guestの転送・展開artifactとHTTP serverを削除し、両VMを開始前の `shut off` へ戻した。

次もPhase 6。SSH user Applyの完成GUI経路でdisconnect/reconciliationと複数sampleを再Gateする。complete診断とログイン済みDebian実display/menu/accessibilityも残る。
