# Phase 6 root history Qt gate on Ubuntu 26.04 — 2026-09-06

開始時のvirsh確認でUbuntu/Debianはともにshut off。Ubuntuだけを起動し、guest agentからIP 192.168.122.48を再取得した。通常UID 1000、Python 3.14.4、既存PySide6 6.10.2を確認した。packageの追加・更新なし。

src/tests/setup.pyをpycacheなしでarchive化し、host/guest双方のSHA-256一致を確認した。

`a416bed2d8ed4f52c1ca3eaf41a304f2c1a82548a9f0048eeec9272c63aaab17`

通常userで`QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/python3 -m unittest`を実行。対象moduleはtest_root_restore_review_dialog、test_root_restore_review_session、test_root_restore_review_client、test_root_restore_status、test_root_restore_status_client、test_root_target_lock。

52件を0.959秒で完走、51成功・1 expected skip（runtime不在境界）。新規GUI 2件、保存失敗後の明示履歴照会・重複click抑止・照会中close/worker待機・遅延履歴破棄が成功した。既存review同意/expiry/480px幅/close応答性、status client→実CLI→一時store、実flock競合/receipt replayも同じartifactで成功した。offscreen pluginのpropagateSizeHints未対応メッセージはあったがtest失敗なし。

Qtのclientはfixtureであり、実PolicyKit認証、installed deb、実display/menu/screen reader、Debian Qt Gateの完了根拠ではない。SSH転送は既存鍵/known_hostsを使用した明示`-F /dev/null`の検証経路であり、production SSHの代替根拠ではない。

guestの今回専用directoryとhost archive/directoryを削除し、不在確認成功。Ubuntuを通常shutdownし、virshで両VMがshut offに戻ったことを確認した。実Ollama/OpenCode設定、service設定、SSH設定、packageは変更していない。Debianは起動していない。

今回source修正なし。前sliceのhost全713 test（682成功・31 skip）と必須検査に加え、上記VM Gateを完了した。全変更未コミット。現在・次ともPhase 6。root専用実行認可/CLI・production audit・要求間排他・provisioning・実PolicyKit/installed deb・両OS最終Gateを継続する。
