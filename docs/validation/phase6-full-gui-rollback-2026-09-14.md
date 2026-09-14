# ff7913b 通常GUI全経路のSSH自動rollback — 2026-09-14

Debian通常userが製品GUIのHosts→Diagnose→Recommendations→Review Changes→
Apply / Resultsを操作し、Ubuntu SSH user Apply後のruntime validation失敗から
自動rollbackして`rolled_back`を表示するまでを確認した（1 sample）。

## 結果

| 検査 | 結果 |
| --- | --- |
| plan / approval | 通常GUIで生成・利用者が選択/レビュー/承認、注入なし |
| Agent推奨 | `compaction.auto` / `compaction.prune`の2件 |
| Apply helper | 1回、exit 0、250 ms |
| production validation | installed / config parseともpassed |
| Gate validation fault | failed checkを1件追加、対象file改変なし |
| rollback helper | 1回、exit 0、219 ms |
| 最終状態 | rolled_back、GUI表示・process exit 0 |
| 復元後config | 開始時と同じSHA-256、auto/pruneともfalse |

GUI observerが保存したsummaryは
`Apply result: rolled_back; runtime validation failed`。利用者が最終表示を見逃した旨を
報告したが、observer JSONと保存画像の双方で同じ表示を確認した。

開始・復元後configのSHA-256は
`fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`。
Apply後hashはjournal上
`682128216e9141bd32169fd999804f3992827cbc902aaf6d4057fd4eecdac0ea`。
journalは`rolled_back`でrollback request hashを保持し、local AES-256-GCM manifestは
complete、remote recovery receiptはverified。plan/change set/backup/manifest/host/
before/after hashの対応を照合した。

## 構成と境界

source commitは`ff7913bb97e896f7992720b9a43c2382970a5fc8`。
candidateとOpenCode archiveは実行直前にhashを再確認した。

| artifact | SHA-256 |
| --- | --- |
| local deb | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| remote helper deb | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |
| OpenCode 1.18.25 archive | `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |

installed `qt_app.main`とproduction diagnostic/planner/approval/SSH Apply composition、
dual backup、remote helperを使用。observerは画面状態とtransport結果を保存するだけで、
plan、approval、GUI state、transportを変更しない。

rollback分岐を決定論的に起動するため、production validatorが返した全passed結果を保存後、
テスト専用failed checkを1件追加した。対象fileを壊す、validation結果をpassedへ変える、
Apply/rollbackを再送する操作はない。したがって通常GUI操作・rollback制御・復元の証拠だが、
自然発生したOpenCode runtime障害や最終artifactの代替ではない。

transport観測は26件。認証完了待ちを含むread-only result downloadは作成前20回exit 1、
作成後等4回exit 0、Apply/rollback mutationは各1回exit 0だった。本Gateでは通信断を
加えていない。rollback応答中の実NIC断とimmutable result照合は
`phase6-cross-vm-network-rollback-2026-09-13.md`で別途確認済み。

## 証拠とcleanup

入口は`full-gui-rollback-2026-09-14.py`、同名directoryにGUI履歴13件・画像、
production validation、transport、journal/manifest/receipt、config、APT、baselineを保存した。

専用SSH key/alias、Secret Service item、backup/state/cacheを削除。Debianの追加12 packageを
明示purgeしbaseline完全一致。Ubuntuは開始snapshotへrunningで復元しbaseline一致、
一時snapshotを削除。両VMともrunningで、実行中GUI/SSH/sudo processなし。
snapshot復元後、Ubuntuの約588秒の遅れを含め両VMのsystem clockを同期した。
NTP設定は変更していない。

公開チェックリストは最終artifact再実行等が残るため18/44件（40.9%）を維持する。
