# SSH Transfer Disconnect Validation — 2026-08-30

## Scope

Phase 4のdisposable SSH target `llm-manager-gate`（Ubuntu 26.04、host `Ubuntu-dev`）に対し、production `RemoteHelperRecoveryCopyStore` → `UserOnlySshRecoveryTransport` → `OpenSshUserStagingRunner`の境界で転送中の実切断を検証した。

専用のControlMaster socketを使い、Gate専用16 MiB dummy itemのSCPだけを64 Kbit/sへ制限して転送中にcontrol `exit`を送った。SSH設定、systemd、Ollama、OpenCodeは変更していない。既存root backup/keyにも変更を加えていない。

## Result

| Observation | Result |
|---|---|
| Remote host | `Ubuntu-dev` |
| ControlMaster切断 | 送信成功 |
| Transport終端 | `remote_staging_failed` |
| Root helper invocation | 0回 |
| `request.json` | 未公開 |
| `result.json` | 未公開 |
| Local authoritative backup | hash検証成功 |
| User staging cleanup | operation directory不在 |

item-first/request-lastのため、不完全な転送はroot operationとして可視化されなかった。transportはremote backup作成やApplyを自動再試行せず、再接続後に許可済み`user-stage-remove`でGate専用stagingだけを削除した。local正本は失敗時も保持された。

## Remaining Gate

remote root journal evidence取得とtargetのread-only reconciliationは後続Gateで完了した。Debian 13でのtransport差異は別Gateで確認する。
