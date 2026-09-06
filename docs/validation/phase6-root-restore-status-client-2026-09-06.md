# Phase 6 root restore status client — 2026-09-06

## 実装

`RootRestoreReviewClient.status`を追加した。手元のexact `LocalRootRestoreRequest`のhash・caller UID・host・形式を検査し、固定pkexec/専用review entryのstatusだけを呼ぶ。履歴なので要求自身の作成時点でcodecを検証し、現在時刻に対する期限切れを理由に履歴照会を拒否しない。これは要求期限の延長や実行認可ではない。

既存transportの120秒timeout・32 KiB上限・canonical JSON・認証拒否/失敗の伏字・cancel前後確認を使用する。応答の全field、要求ID/hash、strict boolean、attemptのID/hash/review hash形式/開始時刻、resultのattempt digest・ID/hash・時刻順序・state/error codeを検証する。集約stateとrequires_attentionも実recordから再計算して照合する。未知field、orphan result、矛盾、非canonical日時を拒否する。

戻り値は`RootRestoreExecutionView`という履歴のみ。review-onlyは実行許可ではなく、attempt-onlyはunknown/attention。手動で照会してもmutationを送信・予約・retryしない。応答不正や通信失敗から未実行を推測しない。

## 検証

新規7 test。期限切れintentと固定status argv、review-only/attempt-only/failed、schema/ID/hash/type/time/attempt digestの偽装拒否、identity/cancel前のI/O拒否、oversize/noncanonical/timeout/認証拒否/伏字と単発transport、遅延cancel、実CLI＋実一時storeのunknown履歴照会を検証した。統合ではstore全fileの内容不変とreplay拒否を確認した。

host全708 test: 679成功・29 skip。compileall、local/remote shell syntax、desktop-file-validate、git diff --check成功。PySide6不在等のskipあり。実PolicyKit、installed deb、OS/実display Gate、deb rebuildは今回未実施。

## 残件

非特権status clientは完成したがGUI接続は未完了。root復元の専用実行認可/CLI・production audit、要求をまたぐ排他、明示provisioning、PolicyKit/OS Gateは残件。root mutation routeは非公開のまま。保存済みdeb/SBOMは本変更のartifact証拠ではない。

既存の未コミット変更を保持。実設定・service・SSH・package・VM状態変更なし。全変更未コミット。現在・次ともPhase 6。
