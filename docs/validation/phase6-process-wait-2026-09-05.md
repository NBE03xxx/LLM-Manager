# Phase 6 subprocess終了待機 Gate（2026-09-05）

両VMが `shut off` のためDebian実display Gateは実施せず、host上でproduction `SubprocessRunner` の終了待機を検証した。既存の未コミット変更を保持し、実設定、systemd、SSH、package、VM状態は変更していない。

## 検出と修正

子プロセスがstdout/stderrを閉じてから処理を継続すると、selector loop終了後の無期限 `wait()` に入り、timeoutとcancelが無効になっていた。2秒継続する実Python childで、150 ms timeoutが通常終了として返り、cancelも例外にならないことを修正前の2 test失敗で確認した。

EOF後もprocessの生存を調べ、最大50 msずつwaitしてdeadlineとtokenを再確認する。既存のcancel/timeout時の停止・回収方針は変更しない。修正後のfocused 15 testは成功した。

## 再現可能な測定

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 packaging/measure-process-wait.py
```

一時directory内のready fileで両pipeのcloseを確認後、cancelを要求する。通常終了・400 ms timeout・cancelを各5回実行し、`waitpid`が `ChildProcessError` を返すことでadapterによる回収済みを検証する。作成したchildだけを対象にし、一時directoryは終了時に削除する。

測定hostはPython 3.14.4 / Linux 7.0.0-31-generic x86_64。生データは [JSON](phase6-process-wait-results-2026-09-05.json) に保存した。

| 指標 | 5 sampleの範囲 |
| --- | --- |
| 通常終了wall time | 217.548–223.525 ms |
| 400 ms timeoutのwall time | 401.321–403.809 ms |
| cancel要求→回収 | 4.096–48.433 ms |
| 親CPU / sample（全15 sample） | 0.672–2.641 ms |
| 親process累積peak RSS | 22,700–22,828 KiB |
| child回収 | 15/15 |

RSSは親process全体の累積high-water markであり、sample別の増分やchildのmemoryではない。短い合成workloadを実adapterへ流す境界測定で、実Agent、Qt event gap、SSH、Applyの性能やrelease SLOを保証しない。有限のcancel非協力区間のwindow close UXは[後続Gate](phase6-close-wait-ux-2026-09-05.md)で検証した。

## 次のPhase 6

検査: 全530 test完走（508成功・22 PySide6 runtime skip）。compileall、local/remote packaging shell syntax、desktop-file-validate、git diff --check成功。Qt runtimeはこのhostでは検証していない。

このscriptの同一artifactを対応VMで測定し、Qt workerでのevent gap・終了通知を併測する。complete診断、SSH/Apply、長時間workloadとDebian実display/menu/accessibility Gateは残る。
