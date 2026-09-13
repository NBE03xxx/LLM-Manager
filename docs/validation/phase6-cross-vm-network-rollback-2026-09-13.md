# ff7913b rollback応答中の実NIC断と結果照合 — 2026-09-13

Debian GUI→Ubuntu SSHで自動rollback完了後の応答を保留し、Ubuntu live NICを
4.055358秒切断した。実SSHがexit 255となった後、復旧後のimmutable result照合で
`rolled_back`を確認した（network-rollback2、1 sample）。

| 検査 | 結果 |
| --- | --- |
| Apply / rollback呼出し | 各1回 |
| rollback helper終了 | 0 |
| rollback SSH終了 | 255、2751 ms、製品deadline timeout false |
| NIC down→up | 4.055358秒 |
| 独立復旧watchdog | exit 0、最終link up |
| result読み取り | 正常Apply後1回、rollback通信失敗後1回 |
| GUI | rolled_back、画像確認済み、Gate exit 0 |
| 復元後SHA-256 | `b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088` |

OpenCode 1.18.30存在検証はpassed、不正JSONのparse検証は期待どおりfailed。
GUIの`runtime validation failed`は自動rollbackを起動した理由を表す。
helper成功応答のrequest ID/hashが切断markerに一致し、restored hashがfixtureと一致する。

## 試験条件

ff7913b candidateのlocal deb hashは
`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`、
remote helper debは`830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`。
製品sourceとinstalled helperは変更していない。

利用者がDebianのRun Applyを1回押し、外部端末でUbuntuのsudo認証を行った。
正常Apply応答は通常配送し、不正JSONの実検証後に自動rollbackする。
試験専用relayは`user-rollback`だけを1回実行し、成功応答を10秒保留する。
rollback SSHにだけServerAliveInterval=1 / ServerAliveCountMax=1を指定する。
監視ready確認後にGUIをlaunchし、2秒未満の成功markerを受けてNICをdownにした。
4秒後の復旧と7秒後の独立watchdogをlibvirt経由で実行した。

実installed module、production診断・Apply composition、dual backupを使用する一方、
plan/approvalは試験注入である。AdapterErrorの注入・mutation再送はない。
同一物理ホスト上の別VM間の仮想NIC断であり、物理ケーブル抜去、変更途中の切断、
長時間切断、通常の診断→推奨→review全GUI操作、最終release artifactの完了は意味しない。

## 先行network-rollbackの非採用結果

Apply後、rollback helperが222 msでexit 1となり、成功markerもrollback resultも
作られなかった。GUIは`recovery_required`、対象hashは不正JSONのhashを保持。
NICは切断されず、watcherを停止した。Apply/rollbackは各1回、再送なし。
失敗結果・GUI画像・transport・metadata・cleanup・checksumを別directoryへ保存した。

実行後の純粋decoderは要求を受理し、対象hashとstaging owner/modeも一致した。
次のrollback2ではsnapshot作成後にUbuntuの約1.72秒の遅れを測定し、prepare/setup後に
両VM時計を同期して成功した。時計ずれは先行失敗の有力な説明だが、先行helperの
stdoutエラーコードと実行時刻は未採取のため、確定原因とは扱わない。
会話中の「原因が確定」という表現をここで訂正する。
rollback2ではhelper応答を追加保存した。製品の有効期間判定は緩和していない。

## 証拠・復元

入口は`cross-vm-network-rollback2-2026-09-13.py`、証拠は同名directory。
先行非採用試行は`cross-vm-network-rollback-2026-09-13.py`と同名directory。
両試行とも有限relay・専用SSH/sudo不在を確認し、Debianの専用Secret Service item・
key・alias・backup/runtimeを削除、新規12 packageだけを明示purgeした。
Ubuntuはrunning snapshotへ復元、baseline一致後に一時snapshotを削除した。
両VMのpackage/manual/保全path/sessionは開始値と完全一致し、runningを維持。
既存snapshotは保持した。復元後に両VMのsystem clockを再同期し、NTP設定は未変更。
時計の記録は`sync-gate-vm-clocks-2026-09-13.json`に追記した。

公開チェックリストは18/44件（40.9%）を維持する。
host回帰806件（767成功・39 expected skip）、両試行の証拠checksum全67件、
操作script/実行harness/relayの構文検査、Git空白検査が成功した。
