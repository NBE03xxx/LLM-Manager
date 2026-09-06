# Phase 6 review dialog history lookup — 2026-09-06

## 実装

既存の非公開root review dialogへ「保存済み履歴を確認（管理者認証）」を追加した。保存成功または保存task作成後の失敗時だけ有効にする。保持したexact requestを専用status clientへ渡す。自動照会はせず、dialog内の照会は一度だけ。期限切れ後も履歴照会できるが、preview/approveの再送や復元実行にはつなげない。

sessionはchecking/checkedを管理し、遅延結果・別要求の結果を拒否する。QtTaskRunnerで非同期照会し、重複clickを抑止する。close時は既存のcancel/worker終了待機を使い、遅延履歴を捨てる。review-only、committed、failed、unknown、照会失敗に固定の英日表示を用意した。現在service状態を確認したとは表示せず、照会失敗を未実行と扱わない。helperのerror文字列は表示しない。

## 検証

新規5 test: 純粋session 3件は成功。保存結果不明後の明示単発status、期限切れ履歴、再送なし、照会失敗後の遅延成功拒否、別要求のattempt拒否を確認した。新規Qt 2件はPySide6不在によりskip。保存失敗後の照会ボタンと重複click、照会中close/遅延結果破棄のruntime testを追加したが、実Qtでの実行結果はまだない。

host全713 test: 682成功・31 skip。compileall、local/remote shell syntax、desktop-file-validate、git diff --check成功。今回VM/実PolicyKit/installed deb/実display検証、deb rebuildは行っていない。GUI runtime Gate完了とは扱わない。

## 残件

次もPhase 6。対応VMで追加Qt testと既存review/status関連testを実行する。通常menuは未公開。専用実行認可/CLI・production audit、要求をまたぐ排他、明示provisioning、PolicyKit/OS Gateは引き続き未完了。dialogを閉じた後の要求再選択・永続履歴一覧は今回の範囲外。

実設定・service・SSH・package・VM状態変更なし。既存変更を保持し、全変更は未コミット。保存済みdeb/SBOMは本変更後のartifact証拠ではない。


## Ubuntu Qt Gate追記（2026-09-06）

Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2でoffscreen関連52 testを実行、51成功・1 expected skip。新規GUI 2件（履歴照会の重複抑止、照会中close/遅延結果破棄）も成功。詳細: `docs/validation/phase6-root-status-qt-ubuntu2604-2026-09-06.md`。package追加なし、host/guest検証物cleanup済み、両VM shut off確認。実PolicyKit/installed deb/実display/Debian Qt Gateは未完了。次もPhase 6: 専用実行認可/CLI・production audit・要求間排他・provisioning・最終Gate。root mutation非公開、全変更未コミット。
