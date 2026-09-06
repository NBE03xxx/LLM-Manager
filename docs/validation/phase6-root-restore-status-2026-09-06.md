# Phase 6 root restore history reconciliation — 2026-09-06

## 実装

専用review CLIに`status request-id request-sha256`を追加した。既存review-system-restore PolicyKit actionで独立して解決したcaller UID/hostを使用し、root-owned reviewの要求hash・UID・hostを照合する。reviewとattempt/resultは一つのshared store lock下で読む。任意path、呼出元指定UID/host、復元実行やretry commandは受け付けない。

`RootRestoreStore.reconcile`は履歴照会専用。現在時刻に対するreview期限切れを理由に過去の結果を隠さず、保存当時の形式・hash・binding・時刻関係を従来のstrict readerで検査する。通常の`load_review`/`begin`の期限制限は変更していない。history用compositionはexecution storeだけを固定pathで開き、鍵・backup payload・現在のtarget・serviceへアクセスしない。取得したFDは終了時に閉じる。

応答は要求ID/hash、state、requires_attention、immutable attempt/resultをcanonical JSONで返す。review内容や設定平文は返さない。状態の意味は以下。

- `review_only`: この照会時点でattempt記録なし。実行認可や今後の未実行を保証しない。
- `unknown`でresultなし: attemptあり、terminal resultなし。進行中か中断済みかを推測せずattentionとする。
- `committed`/`failed`/`unknown`でresultあり: 保存済みの終端記録。現在のservice状態の証明ではない。
- store欠落・pending・破損・競合・binding不一致: エラー。未実行と推測しない。

statusのexit 0は履歴照会成功だけを意味し、復元成功を意味しない。manpageへ明記した。実行認可にはreview actionを流用しない。

## 検証

新規8 test。実一時root storeを使い、期限切れ後のreview-onlyとcommitted履歴、attempt-only unknown、UID/host/hash/型の不一致、missing/pending/tampered evidence、cancelとwriter lock競合、CLI引数/nonroot拒否、固定storeのみのcompositionとFD解放を検証した。照会前後のfile内容一致と、照会後もbegin/replayが拒否されることを確認した。

host全701 test: 672成功・29 skip。compileall、local/remote shell syntax、desktop-file-validate、git diff --check成功。PySide6不在等のskipあり。実PolicyKit・installed deb・VM/実display Gateとdeb rebuildは今回未実施。

## 残件

復元実行の専用認可/CLIとproduction audit composition、状態照会の非特権client/GUI接続、要求をまたぐ排他、明示provisioning、OS Gateは未完了。root mutation routeは非公開を維持する。履歴照会は再実行権限、request予約、cleanup権限として使わない。

既存の未コミット変更を保持した。実設定・service・SSH・package・VM状態は変更していない。全変更未コミット。現在・次ともPhase 6。
