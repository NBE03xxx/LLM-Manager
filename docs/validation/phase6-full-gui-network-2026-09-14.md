# ff7913b 通常GUI全経路と実NIC断後のSSH結果照合 — 2026-09-14

Debian通常userが製品GUIのHosts→Diagnose→Recommendations→Review Changes→
Apply / Resultsを操作し、Ubuntu SSH user Applyの成功応答中にlive NICを切断した。
実SSH exit 255後、復旧した通信でimmutable resultを読み取り、GUIに`committed`を表示した。

## 結果

| 検査 | 結果 |
| --- | --- |
| plan / approval | 通常GUIで生成・利用者が選択/レビュー/承認、注入なし |
| Apply mutation | 1回 |
| helper exit | 0（切断前） |
| NIC down→up | 4.023363秒 |
| Apply SSH | exit 255、2210 ms、製品deadline timeout false |
| 結果照合download | exit 0、3200 ms |
| 最終状態 | committed、GUI表示・exit 0 |
| config | compaction.auto/pruneともtrue、autoupdate=false維持 |
| validation | opencode installed/config parseともpassed |

OpenCode 1.18.25のAgent profileで2件のactionable推奨を生成した。開始configの
SHA-256は`fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`、
変更後は`682128216e9141bd32169fd999804f3992827cbc902aaf6d4057fd4eecdac0ea`。
journalはcommittedで、local AES-256-GCM manifestはcomplete、remote recovery receiptは
verified。plan/change set/manifest/before/after hashの対応を照合した。

## 構成と境界

ff7913bのtracked sourceを再展開してcandidateを再buildした。build内806 test
（767成功・39 expected skip）、両verifierに成功し、以前採用したhashと一致した。

| artifact | SHA-256 |
| --- | --- |
| local deb | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| remote helper deb | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |
| OpenCode 1.18.25 archive | `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |

installed `qt_app.main`とproduction diagnostic/planner/approval/Apply compositionを使用。
観測subclassは画面状態と画像を保存するだけで、plan/approval/GUI stateを設定しない。
transportにだけ、成功したfixed helperのstdoutを10秒保留するrelayと
ServerAliveInterval=1 / ServerAliveCountMax=1を挿入した。AdapterError注入なし。

watcher ready確認後にGUIをlaunch。2秒未満のhelper成功markerを確認してUbuntuの
MAC `52:54:00:f8:49:29`をdownにし、4秒後にupへ戻した。独立watchdogもexit 0。
同一物理host上の別VM間仮想NIC断であり、物理ケーブル抜去ではない。

sudo認証待ち中、remote recovery resultの存在確認downloadが19回exit 1（未作成）し、
作成後2回exit 0となった。このread-only pollingと、Apply切断後の照合download 1回を
transport証拠へ保存した。mutation再送はない。

これは現UNRELEASED candidateのcommit case 1 sample。rollback caseは別の注入plan Gate、
長時間/恒久切断、複数sampleの性能判定、最終release artifactの代替ではない。

## 証拠とcleanup

入口は`full-gui-network-2026-09-14.py`、同名directoryにGUI履歴13件・画像、transport、
network、journal/manifest/receipt、config、APT、baseline、再build logを保存した。
全checksumと構文・結合検査に成功。

専用SSH key/alias、Secret Service item、backup/state/cacheを削除。Debianの追加12 packageを
明示purgeしbaseline完全一致。Ubuntuは開始snapshotへrunningで復元しbaseline一致、
一時snapshotを削除。両VMともrunning。既存snapshotは保持した。
snapshot復元後、Ubuntuの約420秒の遅れを含め両VMのsystem clockを同期した。
NTP設定は変更していない。

公開チェックリストは性能の複数sample等が残るため18/44件（40.9%）を維持する。
