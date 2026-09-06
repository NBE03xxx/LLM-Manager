# Phase 6 Qt layout・終了処理 hardening（2026-09-05）

## 対象

Phase 6 acceptance項目のうち、実displayを必要としない次の境界を検証した。

- 6工程すべてで狭いwindowや長文を縦scrollできること
- recommendation、review、approval、result、backup、restoreの長文summaryを折り返すこと
- background worker実行中もQt event loopをblockしないこと
- windowを閉じる操作がactive workerへcancelを送り、worker終了までwindow破棄を待つこと

実Ollama/OpenCode設定、既存systemd unit、SSH設定は変更していない。

## 実装境界

`MainWindow`の各工程pageを`QScrollArea`へ収め、`widgetResizable`を有効にした。主要summary labelには`wordWrap`を設定した。すべてのQt task起動を共通のworker追跡境界へ通し、`closeEvent`はactive hostをcancelして最初のcloseを保留する。最後のworkerが`finished`を送った後にQt event loopからcloseを再要求する。

worker threadを強制終了しない。taskがcancelを確認しない間はwindowが開いたままになる。有限の非協力区間の明示的待機UXは[後続Gate](phase6-close-wait-ux-2026-09-05.md)で評価した。

## Ubuntu 26.04実Qt Gate

- VM: `ubuntu26.04`
- Qt: VMに導入済みのPySide6 runtime、`QT_QPA_PLATFORM=offscreen`
- 最終転送artifact SHA-256: `9fcbd7dc5f10ca7f7b8c90ca0d31984e75c8284ec8895c68900ff697936d2728`
- 実行: `tests.test_ui_qt_runtime tests.test_ui_qt_window`
- 結果: 23 tests成功、1 expected skip、1.242秒

新規runtime testは480x320 windowで6個のscroll areaと主要labelの折返しを確認した。終了処理testはworkerがcancelを観測してから50 ms後に終了するようにし、最初のclose要求直後はwindowが可視のまま、worker終了後に閉じることを確認した。

長時間task Gateは、cancelされるまで継続するworkerをUI thread外で動かし、Qt event loopが10 ms間隔のeventを20回以上処理してからcancelした。workerがcancelを0.5秒以内に観測し、`cancelled`終端となることを確認した。この0.5秒は協力的fake taskのpoll境界であり、実backendの性能値ではない。既存のevent-loop sentinel、result/cancel、Apply/restore境界も同じrunで回帰がない。

Gate後にguest/hostの一時artifactとHTTP serverを削除し、`ubuntu26.04`と`debian13`がともに`shut off`であることを確認した。

## 全体回帰

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`: 526 tests、505成功、21 skip、失敗なし、0.982秒
- `compileall`: 成功
- local/remote packaging shell syntax: 成功
- `desktop-file-validate`: 成功
- local/remote CycloneDX JSON parse: 成功
- `git diff --check`: 成功

hostの21 skipはPySide6 runtime不在による。実Qtの対応testはUbuntu VMで上記のとおり実行した。

## 残件

- Debian 13のログイン済みdesktopでmenuから起動し、実displayの狭幅・長文・keyboard focus・screen reader情報を確認する。
- 実Agentまたは同等の長時間production taskで、cancel到達時間、進捗表示、終了待機UX、memory/CPUを測定する。
- 永久に戻らないin-process taskは強制終了しない境界を維持する。有限の非協力区間の表示と安全な待機方針は後続Gateで完了。
- 完成済みGUI経路からSSH切断後のimmutable result再照合を再Gateする。

## Accessible name follow-up

実画面確認後、primary controlとstatus/summaryの`accessibleName`が内部object IDのままである問題を修正した。visibleな英日文言へ同期し、言語切替時にも更新する。host側は全527 tests（506成功・21 PySide6 skip）、compileall、`git diff --check`が成功した。変更後のUbuntu 26.04実PySide6 Gateはartifact SHA-256 `2639ca9acc3aa9d730b2dfc0f0ef6b10b5beece7c4186c31295f0f6a21ca8b09`から24件（1 expected skip、1.272秒）が成功した。

Hosts画面のkeyboard focusについて、host selectorへfocusした後のTabがlanguage selectorへ移るruntime testを追加した。hostにPySide6がないため、この追加分の実Qt確認は次回VM Gateへ束ねる。

追記: [対応VM＋Qt終了待機Gate](phase6-qt-process-wait-2026-09-05.md)でQtTestへの依存をQtGuiのキーイベントへ置換し、Ubuntu実PySide6でこのTab移動testの成功を確認した。実display/accessibility全体の完了とは扱わない。
