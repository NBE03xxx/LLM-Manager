# Phase 5 Qt restore execution boundary validation (2026-09-04)

## Decision

短命authorizationをQt stateへ保存せず、exact previewとapprovalから作る一つのworker task内部でstrict preflightとexecutionを連続実行する。GUI controlは注入されたrestore taskがある場合だけ有効にし、production `main()`にはまだ注入しない。

## Safety boundary

- 実行クリック時にpreview、approval、host、backup、expiryを再確認する。
- host単位の`QtWorkerCoordinator` lockより前にactive restoreを記録し、二つ目の実行を受け付けない。
- worker中はhost selector、inventory refresh、approval、runを無効化する。
- cancelは同じworker cancellation tokenへ渡す。
- success、failure、cancelのすべてでpreviewとapprovalを破棄する。
- success後もinventoryを自動mutation authorityにせず、明示refreshまでrunを再有効化しない。
- production compositionはrestore taskを渡さないためrun controlはdisabledのままである。

## Sandbox and Qt Gate

composition testでpreflight authorizationがworker task外へ公開されず、暗号化backupからCOMMITTEDまで到達することを確認した。

Ubuntu 26.04、PySide6 6.10.2、Qt offscreenで`test_restore_worker_locks_host_rejects_double_click_and_consumes_review`を実行した。実行中のhost lock、run無効化、double click時のfactory call 1回、完了後のapproval解除・run無効化を確認し、1件が0.114秒で成功した。artifact SHA-256は`a60b86f4d068e4ff4d38f8fea37bde1f8ee71d3665ec8cb23bc1cdf04f220de3`で一致し、VMの一時Gate directoryは削除した。

実OpenCode/Ollama設定、systemd、SSH設定、production restore compositionは変更していない。

main hostの全446件は0.565秒で成功し、PySide6依存11件と明示Secret Service Gate 2件の計13件をskipした。compileall、local/remote packaging shell構文、`git diff --check`も成功した。

## Next

production restore taskを公開する前に、COMMITTED/FAILED/UNKNOWNの結果表示と明示inventory refresh、cancel/error runtime Gateを監査する。
