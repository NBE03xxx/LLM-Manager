# ff7913b 別VM間rollbackと応答喪失後照合 — 2026-09-13

## 結果

Debian 13の一般ユーザーWayland GUIからUbuntu 26.04へ、現candidate ff7913bの
SSH user Applyを行い、自動rollbackとimmutable result照合に成功した。
利用者がRun Applyを押し、外部端末でUbuntuのsudo認証を行った。

| 項目 | 結果 |
| --- | --- |
| 実OpenCode 1.18.30の存在検証 | passed |
| 意図的な不正JSONの検証 | failed（期待どおり） |
| 最終状態 | rolled_back |
| Apply呼出し | 1回 |
| rollback呼出し | 1回 |
| 応答喪失注入後のresult読み取り | Apply/rollbackそれぞれ1回 |
| 元の設定hash | 開始時と一致 |
| GUI Results表示 | rolled_back、可視、画像確認済み |

正常fixtureは `{"autoupdate": false}` と末尾改行、対象user所有0600。
復元後SHA-256は
`b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088`。
表示中の `runtime validation failed` は不正JSONを検出した期待どおりの理由であり、
rollback失敗ではない。

## 前提と証拠の境界

local deb SHA-256 `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`、
remote deb SHA-256 `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`。
製品sourceの変更なし。実installed module、production SSH診断・Apply factory・
Secret Service暗号化local backup・root recovery copy・runtime validatorを使用した。

r2は[時刻ずれによる拒否](phase6-cross-vm-clock-rejection-2026-09-13.md)で終了・復元済み。
時計補正後、独立したr3 namespace、snapshot、key reference、operationを新規作成した。
過去のmutationの再送ではない。製品の時刻検査・認証timeoutは緩和していない。

旧Gateと同じplan/approval注入およびhelper成功直後の応答喪失例外注入を含む。
実際のNIC切断・物理回線断は行っておらず、通常の診断→推奨→人手review全経路や
最終release artifact Gateの代替ではない。モデル推論も対象外。

操作scriptは `cross-vm-rollback-r3-2026-09-13.py`（r2と既存lifecycleを再利用）。
実行したGUI harness、結果、画像、APT・復元記録は
`cross-vm-rollback-r3-2026-09-13/` に保存。旧失敗証拠は上書きしていない。

## cleanupと時計

専用SSH/sudo process不在を確認し、Debianの試験専用Secret Service item、SSH key/alias、
暗号化試験backup/runtimeを削除。新規追加12 packageだけを明示purgeし、
package/manual/保全path/sessionが開始値と完全一致。dpkg auditとAPT check成功。
Ubuntuはrunningで開始snapshotへ復元し、baseline一致後に一時snapshotだけを削除。
両VMともrunning、既存snapshotは保持。

Ubuntuはsnapshot復元後、ホストより約169秒遅れていた。承認済みの時計合わせを
最後に再実施し、両VMの測定区間がホスト時刻の±1秒内に入ることを確認した。
時計補正は意図した変更であり、「時計もsnapshot開始値に戻した」とは扱わない。
ホスト時計・NTP設定は変更していない。hwclock不在を事前検査してsystem clockだけを補正。
実測は `sync-gate-vm-clocks-2026-09-13.json`。

host回帰は806件中767成功・39 expected skip。製品source変更なし。
