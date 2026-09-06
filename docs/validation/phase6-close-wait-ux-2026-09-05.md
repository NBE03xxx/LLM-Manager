# Phase 6 cancel非協力区間の終了待機UX Gate

## 結果

2026-09-05、window close時にactive workerへcancelを送った後、workerを強制終了せず安全な終端までwindowを維持する既存境界へ、明示的な終了待機表示を追加した。

- English: `Closing after the current operation stops safely…`
- 日本語: `現在の処理が安全に停止するまで終了を待っています…`
- status labelのaccessible nameを表示文言と同期する。
- close待機中は診断・Apply・Restoreのcancel buttonを無効化し、重複要求を防ぐ。
- host selectionを含むbusy境界へclose待機を含める。
- worker threadや実行中のmutationを強制終了しない。

## 合成runtime Gate

300 msの有限区間でcancellation tokenを確認しないtaskをQt workerで実行した。task開始後にwindow closeを要求し、直後に以下を確認した。

- windowは可視のまま。
- 日本語の終了待機文言を表示。
- visible textとaccessible nameが一致。
- cancel buttonは無効。
- 10 ms timer eventを10回以上処理。
- taskが安全点へ到達して`OperationCancelled`で終端した後だけwindowが非表示。

Ubuntu 26.04 / Python 3.14.4 / PySide6 6.10.2のoffscreen実Qtで、i18n・Qt runtime・Qt windowの31 testを実行し、30成功・1 expected skip、1.549秒。artifact SHA-256は `d866b186e9936eafc08400bda7a9e7b8e009d13dfd20c3aaeda72032026e63b1`。ログは [実行結果](phase6-close-wait-ubuntu2604-tests-2026-09-05.txt) に保存した。

hostは全531 test完走、508成功・23 PySide6 runtime skip。compileall、local/remote packaging shell syntax、desktop-file-validate、diff checkも成功した。

## 限界とcleanup

このGateは有限のcancel非協力区間に対する表示とevent-loop応答性を確認する。永久に戻らないin-process taskを安全に中断する仕組みではない。LLM-Managerはworkerを強制終了せず、windowを開いたまま明示的に待機する。production adapter自身のsubprocess timeout/cancel/reapは別Gateで確認済み。

検証はUID 1000通常ユーザー、`QT_QPA_PLATFORM=offscreen`、VMとhostの一時directoryだけで実施した。package、実設定、systemd、SSHを変更していない。guest/host artifactとHTTP serverを削除し、Ubuntu VMを開始前の `shut off` へ戻した。Debian VMは起動していない。

次もPhase 6。complete/SSH/Apply性能と、ログイン済みDebianの実display/menu/screen reader Gateが残る。
