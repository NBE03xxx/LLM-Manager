# Phase 6: 60分 long-running Agent Gate — 2026-09-13

## 結果

Ubuntu 26.04のsystem Python 3.14.4 / PySide6 6.10.2で、release必須として定義した
3600秒の合成Agent相当workloadとGUI cancel Gateを完走し、全15 checkに合格した。
2026-09-12に開始し、日付をまたいで2026-09-13に結果を回収した。

- 実行時間: 3600.116秒（`release_duration_met=true`）
- Qt event loop最大gap: 66.258 ms（上限250 ms）
- cancelからworker/child回収: 53.625 ms（上限1000 ms）
- 親process RSS: 75,820 → peak 78,848 KiB、増加3,028 KiB（上限65,536 KiB）
- 親process CPU比率: 0.007387（上限0.25）
- child peak RSS: 50,252 KiB（上限131,072 KiB）
- heartbeat sequence: 17,400、cancel時のage 3.896秒（上限10秒）
- Qt tick: 72,002回、RSS sample: 3,498回
- GUI: `running → cancel_requested → failed / operation_cancelled`
- 実行中は開始button無効、取消button有効。
- childはreap済み、worker inactive、watchdog不使用。

`failed`は取消を明示する既定terminal statusで、error code
`operation_cancelled`との組合せを合格条件としている。クラッシュや測定失敗ではない。

## sourceと実行境界

commit `8056850bf6c2747ca25dd26d006a003066ed9f3d`のtracked sourceへ、accessibility
修正中のUI sourceを重ねた限定archiveをUbuntuの`/tmp`へ転送した。

- archive SHA-256: `13470947c15393d8c001e6ce37dbf1922481bfd0f5aa1c308ad8913e4dbab113`
- 収録範囲: `src/`と`packaging/measure-long-running-agent.py`
- 実行: UID 1000 `yoshimi`、Qt offscreen、production `MainWindow`、
  `QtWorkerCoordinator`、`SubprocessRunner`
- workload: 32 MiB固定working set、SHA-256計算、bounded JSON progress、周期heartbeat

モデル推論、network API、利用者設定、package、serviceには触れていない。したがって、
実モデルや外部APIを含む耐久試験ではなく、製品のQt/worker/subprocess/cancel境界に対する
release Gateである。

## 初回launchの扱い

最初の転送archiveが`src`と`tests`だけで測定scriptを含まなかったため、Pythonは負荷開始前に
exit 2となった。監視の最初のpollで即時検出し、QEMU結果を`failed-launch.json`へ保存した。
製品process、workload、3600秒計時は開始していない。測定scriptを含む限定archiveへ交換後、
別guest-agent PIDで3600秒を最初から実行した。失敗launchを合格結果や実行時間へ含めていない。

## 証拠とcleanup

`long-running-agent-2026-09-12/`にbaseline/environment、失敗launch、QEMU process結果、
判定JSON、実行script、restored inventoryを保存した。

完了後にguestの限定source treeとarchiveを削除し、package/manual/保全pathのinventoryが
開始値と完全一致することを確認した。Ubuntu VMは開始時どおりrunningで、snapshot、設定、
package、serviceを変更していない。Debian VMは操作していない。

## 残件

60分release Gateは完了。任意の4時間soakと実モデル推論を含む追加試験は未実施だが、
必須60分Gateの代替条件ではない。accessibility修正は未コミットのため、commit後candidateの
再現build、残るSSH切断、final SBOM/license、UNRELEASED解除判断、署名・公開を継続する。
