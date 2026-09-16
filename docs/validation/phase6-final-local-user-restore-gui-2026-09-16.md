# Final artifact local user Apply/manual restore GUI Gate — 2026-09-16

final source commit `5b7d4de03e495fe630deab952de043f945a22bd7` の local deb を
Debian 13 Wayland の通常 user（UID 1000）へ導入し、通常 `qt_app.main` から Local 診断、
Agent 推奨2件、review、明示承認、Apply、暗号化 backup、同じ GUI での manual restore、
restore 後の明示 Refresh まで完了した。

## 採用結果

| 検査 | 結果 |
| --- | --- |
| source / local deb | `5b7d4de03e495fe630deab952de043f945a22bd7` / `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` |
| remote helper identity | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4`（未使用、同一 release set の identity 確認） |
| OpenCode | 1.18.25 archive `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |
| GUI Apply | Agent 推奨2件、review、明示承認、Apply 1回、`committed` |
| backup | 1件、complete、AES-256-GCM、Secret Service `local-master-v1` |
| GUI restore | 明示 Refresh、backup 選択、metadata-only preview、正確な同意、Run Restore 1回 |
| restore 結果 | attempt 1件、result 1件、`committed`、初期 config hash 復元 |
| restore 後 | 明示 Refresh 後 inventory に `restore: committed`、attention false |
| observer 境界 | plan、approval、GUI state の注入なし。可視 state と画面だけを保存 |
| cleanup | 専用 key/state/path と追加12 packageを削除、baseline/session完全一致、snapshot削除、VM running |

採用証拠は `local-user-restore-gui-final-2026-09-16-attempt2/` に保存した。
`gate-result.json` は Apply 1回、restore attempt/result各1件、初期hash復元、明示Refreshを記録する。
`binding-verification.json` では journal、manifest、restore attempt/result、5 event audit chain、
AES-256-GCM content reference、Secret Service lifecycle の canonical hash と相互参照を再計算した。
清掃後の read-only audit と `SHA256SUMS` 全件照合も成功した。

## 非採用試行

最初の試行は Apply 1回が `committed` した後、Wayland/AT-SPI の操作切り分け中に
metadata-only restore preview が期限切れとなった。restore は開始せず、release Gate 成功とは
扱っていない。`local-user-restore-gui-final-2026-09-16/attempt-failure.json` に理由を記録し、
専用 state/key/package を削除、Debian baseline/sessionを完全復帰してsnapshotを削除した。
その後、独立namespaceと新規snapshotのattempt2を最初から実行した。両試行を通じて保存済み
mutation の再送はなく、採用attempt2のApply/restoreは各1回だけである。

## 判定

final artifactでの local user Apply/manual restore通常GUI Gateは合格。release checklistの
該当項目を完了とする。SSH user Apply/rollback＋切断後immutable result照合、checksum/signature、
signed tag、publication後再取得は別Gateとして残る。
