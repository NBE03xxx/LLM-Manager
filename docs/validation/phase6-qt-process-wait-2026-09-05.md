# Phase 6 対応VM subprocess・Qt終了待機 Gate

## 範囲

2026-09-05、Ubuntu 26.04とDebian 13を開始前の `shut off` から一時起動し、前sliceのEOF後cancel/timeout修正を同一artifactで検証した。guest-agent疎通と現在IPを取得し直し、HTTP転送後のSHA-256を検証した。

最終artifact SHA-256: `bb731b44ac717600d20f3c2b5c08a78c5debd23d4beeabfde1c1c22f4afb777d`。

検証は各VMのUID 1000（Ubuntu `yoshimi`、Debian `user`）から `/tmp/llm-manager-qt-wait-gate-v2` 内で実行した。GUIは非特権、offscreen。package追加、実Ollama/OpenCode設定、SSH設定、systemd unitの変更なし。

## 回帰とテスト依存の修正

初回Ubuntu Gateで、前回追加したkeyboard focus testの `PySide6.QtTest` importが失敗した。配布runtimeにQtTestを追加せず、QtCore/QtGuiの `QKeyEvent` を `QApplication.sendEvent` で送るよう修正した。実Qtでhost selectorからlanguage selectorへのTab移動を確認した。

最終artifactでの結果:

- Ubuntu Python 3.14.4 / PySide6 6.10.2: process、Qt runtime、Qt windowの40 test、39成功・1 expected skip、1.690秒。
- Debian Python 3.13.5: processの15 test全成功、0.441秒。
- host: 全530 test、508成功・22 PySide6 runtime skip。compileall、packaging shell syntax、desktop validation、diff check成功。

実行ログ: [Ubuntu](phase6-process-wait-ubuntu2604-tests-2026-09-05.txt)、[Debian](phase6-process-wait-debian13-tests-2026-09-05.txt)。

## 測定

両VMで `packaging/measure-process-wait.py` を実行し、通常終了・timeout・cancel各5 sampleを確認した。全30 childをadapterが回収済み。cancel→回収はUbuntu 1.463–50.574 ms、Debian 47.004–50.505 ms。

生データ: [Ubuntu process](phase6-process-wait-ubuntu2604-2026-09-05.json)、[Debian process](phase6-process-wait-debian13-2026-09-05.json)。

Ubuntuでは次を追加実行した。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 packaging/measure-qt-process-wait.py
```

Qt workerからproduction `SubprocessRunner` で有限の合成childを起動する。childはstdout/stderrをclose後に一時ready fileを書き、処理を継続する。cancel/closeはready確認後5秒待って実行し、window closeは実 `MainWindow` のDiagnoseボタンから開始したworkerへ送る。10 ms QTimerでevent gapを測り、回収後のworker終端・window非表示を確認する。

| 指標 | 結果 |
| --- | --- |
| 通常終了/timeout/cancel/close | 各3 sample、計12成功 |
| 全sample最大event gap | 10.957 ms |
| cancel/close sampleのevent ticks | 503–509 |
| cancel→adapter回収（cancel/close計6 sample） | 5.152–50.497 ms |
| close要求→window非表示検出 | 10.218–60.346 ms |
| close要求直後のwindow維持 | 3/3 |
| child回収 | 12/12 |
| 親CPU / sample | 3.994–69.512 ms |
| 親process累積peak RSS | 61,172–76,728 KiB |

生データ: [Qt process JSON](phase6-qt-process-wait-ubuntu2604-2026-09-05.json)。event gap 250 ms未満、cancel→回収500 ms未満はこのGateの異常検出閾値で、release SLOではない。close非表示の検出には10 ms polling遅延が含まれる。RSSは親processの累積high-water markで、child memoryやsample増分ではない。

## 限界とcleanup

5秒継続する合成childによるproduction adapter/Qt接続の検証であり、実Agentの推論負荷や長時間memory安定性、complete診断、SSH/Apply性能を保証しない。有限の非協力taskのclose待機UXは[後続Gate](phase6-close-wait-ux-2026-09-05.md)で完了。実display/accessibilityは未完了。

Debian `guest-get-users` は空で、実display/menu Gateは実施していない。DebianへのQt dependency追加も行っていない。

host/guestの今回作成した転送・展開artifactだけを削除し、HTTP server停止、両VMの正常shutdown後に `shut off` を確認した。検証ログと測定JSONはこのdirectoryへ保存した。

次もPhase 6。complete/SSH/Apply性能、ログイン済みDebian実display/menu/accessibilityを継続する。
