# Phase 6 通常GUI SSH Apply 5 sample performance Gate — 2026-09-14

## 結果

Debian 13の通常user、installed `ff7913b` candidate、通常`qt_app.main`から、
Ubuntu 26.04 SSH先へのproduction Applyを5回直列実行した。各sampleで利用者が画面上の
SSH hostを選び、診断、Agent profile、推奨2件、review、承認、Prepare、Run Applyを操作した。
plan、approval、transport、validation resultは注入していない。

全5 sampleで次を確認した。

- operationは各sampleで新規作成し、Apply invokeは各1回、再送なし
- 終端は`committed` 5/5
- `opencode.installed`と`opencode.config.parse`はともにpassed 5/5
- 開始config SHA-256は全sampleで
  `fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`
- 終了configは全sampleで`compaction.auto=true`、`compaction.prune=true`
- local AES-256-GCM backupとremote root recovery copyを通るproduction compositionを使用
- Debian画面に出る外部terminalからUbuntu `yoshimi`の対話sudo認証を実施

| sample | Applyクリック→完了（認証込み） | `ssh.user_apply.invoke` | status |
| --- | ---: | ---: | --- |
| 01 | 13,222.943 ms | 249.107 ms | committed |
| 02 | 32,539.075 ms | 214.865 ms | committed |
| 03 | 19,655.209 ms | 220.387 ms | committed |
| 04 | 13,550.948 ms | 252.493 ms | committed |
| 05 | 15,416.516 ms | 231.750 ms | committed |

- 認証込みApply時間: 最小13,222.943 ms、中央値15,416.516 ms、最大32,539.075 ms
- SSH Apply helper呼出し: 最小214.865 ms、中央値231.750 ms、最大252.493 ms

対話認証込み時間は人の入力待ちとremote result pollingを含むoperational latencyであり、
backendだけのbenchmarkではない。`ssh.user_apply.invoke`は既に準備されたhash-bound requestを
remote user helperが実行する区間で、backup、対話sudo、validationは含まない。

## 測定と証拠

one-shot入口は`ssh-apply-performance-2026-09-14.py`。証拠directoryには各sampleの
PID/exit、開始・終了target、timing、SSH correlation event、GUI state history、最終Results画像、
集計`summary.json`、APT/baseline/cleanup結果がある。`SHA256SUMS`は全件検証済み。

sample-01ではobserverの比較用recordへ観測時刻を直接追加したため、同一画面を差分と誤認して
historyを1,830件保存した。これはobserverによる画面/state保存だけの問題で、製品state、
GUI操作、plan/approval、transport、timing境界へは影響しない。sample-02より比較用recordと
時刻付き保存recordを分離し、各historyは13件となった。sample-01は全重複画像をhostへ回収せず、
history JSON、timing、transport、result、最終Results画像を保存した。

各sample間は次のsampleをactionableな同一fixtureから開始するため、Ubuntu通常userでfixture
configだけを開始内容へ戻した。この直接resetは前sampleの終了確認・証拠回収後、次sampleの
timed interval前に行い、各reset hashを保存した。製品のrestore routeやoperation再送としては
扱わない。

## Cleanupと限界

5件の回収後、Debian/Ubuntuの専用SSH・sudo process不在を確認した。専用Secret Service key、
SSH alias/key、state/config/cache、candidate packageと追加依存、OpenCode archive/binaryを削除し、
Ubuntu snapshotをrunningで復元後に削除した。両VMのpackage/manual/session baselineは完全一致し、
両VMはrunningを維持した。

snapshot復元直後、Ubuntu system clockがhostより約1,158秒遅れていたため、既存の承認済み
clock GateでNTP設定を変更せずsystem clockだけを補正した。補正後のDebian–Ubuntu差は0.023秒。
結果は`sync-gate-vm-clocks-2026-09-13.json`へappendした。両VMに`hwclock`はなく、RTC更新は
行っていない。

このGateは単一VM pair、同一network、同一小容量configの5 sample baselineであり、p95、
対応hardware全体、長時間・恒久切断、自然障害rollback、最終release artifactを保証しない。
現candidateは`0.1.0 / UNRELEASED`で、公開checklistの親項目は自然障害rollbackと最終artifact
反復が残るため未完了のままとする。

### 2026-09-15 cleanup訂正

後続の[authentication context installed UI Gate](phase6-auth-context-ui-installed-2026-09-15.md)の
開始時検査で、`local-master-v1`のSecret Service項目1件が残存していることを検出した。
非秘密propertyの作成/更新時刻は2026-09-14 23:08:20 JSTで、本Gate sample-01開始直前と一致する。
製品が作成した`local-master-v1`とcleanupが検索した専用referenceのharness置換ずれにより、
上記「専用Secret Service keyを削除」の主張はこの1件について誤っていた。

対応backup/state/configは本Gate終了時から不在。本日、属性・label・作成/更新時刻を再照合した
正確な1件だけを削除し、同referenceが不在であることを確認した。秘密値は取得していない。
package/manual/session baseline、性能測定、Apply結果への影響はない。cleanup完全性は本訂正を含めて判定する。
