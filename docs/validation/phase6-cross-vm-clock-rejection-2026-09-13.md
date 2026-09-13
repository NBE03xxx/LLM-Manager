# 別VM間rollback試験の時刻ずれによる拒否 — 2026-09-13

## 結論

現candidate ff7913bのDebian GUI→Ubuntu SSHを新規operationで再検証した。
利用者がRun Applyを押してsudo認証したが、Apply前で停止した。
sudoログとrequestの比較により、実行側の時計が要求作成時刻より199.638238秒前だった。
保存requestに対し、そのsudo実行時刻を渡す純粋decoderだけを実行すると
`expired_remote_request: remote helper request is outside its validity window` を再現した。
helperやmutationは再実行していない。

| 証拠 | UTC |
| --- | --- |
| Ubuntu sudo実行記録 | 2026-09-13 03:32:12.337792 |
| Debian request作成 | 2026-09-13 03:35:31.976030 |
| request期限 | 2026-09-13 03:40:31.976030 |

後続の時計測定でもUbuntuはDebianより約246秒遅れていた。
DebianはNTP=no/NTPSynchronized=no、UbuntuはNTP=yes/NTPSynchronized=no。
時計がずれた根本原因までは特定していない。snapshot復元後も含め、時計の同期を
検証環境の前提条件として確認する必要がある。

## 試験結果と限界

`cross-vm-rollback-r2-2026-09-13/` に結果と画像、sudo記録、時刻測定、
decoder再現、package/baseline/cleanup記録を保存した。
remote stagingのowner/modeは対象userの0700/0600。sudo helper実行を確認したが、
そのoperationのroot receipt/resultは生成されなかった。
GUIは `approved; both SSH backup copies must verify` と表示した。
Apply/rollbackイベントは0件、対象設定hashは開始時と同じ。

これは時刻制約が拒否した失敗証拠であり、rollbackの成功証拠ではない。
前回の「認証入力タイムアウト」という推測をこのr2へ適用しない。
最初のcross-vm試験とは別operationであり、過去の失敗原因まで断定しない。

## 復元と時計補正

r2の専用SSH/sudoプロセス不在を確認し、Debianの試験専用key/alias/backupと
追加12 packageをcleanup。package/manual/保全path/session一致。
Ubuntuは開始snapshotへrunning復元後にbaseline一致、その一時snapshotだけを削除。

続いて利用者の明示承認で、両VMのsystem clockをホスト時刻へ一度ずつ補正した。
`guest-set-time`は両VMで`/sbin/hwclock`不在のRTC更新エラーとなったため、
guest-execの`date --set`でsystem clockのみ補正。最初の試行は例外で記録前に停止し、
後続scriptはエラーと補正後の実測を保存するようにした。
ホスト時計・NTP設定・package構成を時計補正のために変更していない。
`sync-gate-vm-clocks-2026-09-13.json` に実行ごとの記録を保存する。

補正後の再検証は新しいr3 namespace/operationで行い、r2を再送しない。
