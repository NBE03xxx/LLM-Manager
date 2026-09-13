# ff7913b 実NIC切断後のSSH Apply結果照合 — 2026-09-13

## 結果（net2、1 sample）

Debian GUI→Ubuntu SSHでhelperの変更処理完了後、応答を受け取る前にUbuntuの
仮想NICを切断した。実SSHの失敗後、通信復旧後のimmutable result照合によって
`committed` と確認できた。Applyの再送なし。

| 検査 | 結果 |
| --- | --- |
| helper終了コード（切断前） | 0 |
| NICのdown→up | 4.020秒 |
| SSH終了コード | 255 |
| SSH呼出し全体の時間 | 2941 ms |
| 製品runnerのdeadline timeout | false（SSH自身のkeepalive失敗） |
| SSH stderr | server 192.168.122.48 not responding |
| Apply呼出し | 1回 |
| 失敗後result読み取り | 1回 |
| 最終GUI | Apply result: committed.（可視、画像確認済み） |
| 終了時NIC | up |

OpenCode installed / config parseの両検証がpassed、エラーなし。
対象SHA-256は`b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088`。

## 試験方法と限界

source ff7913bの現candidateを使用。Debian local debのSHA-256は
`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`、
Ubuntu remote helperは`830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`。
製品sourceとinstalled helperは未変更。

- 利用者がDebian GUIのRun Applyを押し、外部端末でUbuntuのsudo認証を行う。
- 実production Apply factory/diagnostics/runtime validatorとinstalled moduleを使用。
  plan/approvalは既存Gateと同じく注入する。開始時の対象は不在で、新規作成case。
- 試験専用relayが固定helperを1回実行する。helperのexit 0を確認して通知fileを作り、
  stdoutだけを10秒保留する。helperの処理、保存結果、終了コードは改変しない。
- 監視をGUI表示より先に開始する。QGAで2秒未満の新しい完了通知だけを受理し、
  MAC `52:54:00:f8:49:29` のlive linkをdownにする。永続NIC設定は変更しない。
- mutation呼出しのSSHにだけServerAliveInterval=1 / ServerAliveCountMax=1を指定。
  応答保留中に実回線断でSSH自身がexit 255を返す。AdapterErrorの注入はしていない。
- 4秒後にlibvirt経由でupへ戻す。独立processも7秒後にupを実行し、正常終了を確認。
  復旧はSSHに依存しない。
- production経路が失敗を処理し、復旧後に保存結果を読み取って検証する。

これは同一物理ホスト上の別VM間の仮想ネットワーク断で、物理ケーブル抜去ではない。
変更途中の切断、rollback応答中の切断、長時間/恒久的切断、通常の診断→推奨→review全操作、
モデル推論、最終release artifact Gateを完了したとは扱わない。
応答保留relayと短いkeepalive値は試験の計測条件であり、通常の性能基準ではない。

## 初回netの非採用記録

初回はGUI表示が監視開始より先になり、監視開始時にhelperが既に終了していた。
古い通知の検査でNIC切断を中止した。Applyはcommitted、SSH exit 0だが
Gateのverifiedはfalse。`network-not-cut.json`を含む非採用証拠を保存した。
同じApplyを再送せず両VMを復元し、新しいnet2 namespace/operationで再検証した。
net2では監視のready出力を確認してからGUIを表示した。

## 証拠とcleanup

`cross-vm-network-2026-09-13.py` は操作script、net2入口は
`cross-vm-network2-2026-09-13.py`。各証拠dirに実GUI harness、relay、結果、画像、
SSH出力、link状態、APT、baseline/cleanup、checksumを保存した。

両試行とも有限relayと専用SSH/sudoの不在を確認してcleanupした。
Debianの専用Secret Service item、試験SSH鍵・alias、backup/runtimeを削除し、
新規12 packageだけを明示purge。package/manual/保全path/sessionが開始値と一致。
Ubuntuはrunningで開始snapshotへ復元し、baseline一致後に一時snapshotのみ削除。
両VMともrunning。既存snapshotを保持し、最後に承認済みのsystem clock補正を再実施した。
ホスト時計とNTP設定は未変更。

host回帰は806件中767成功・39 expected skip。製品source変更なし。
