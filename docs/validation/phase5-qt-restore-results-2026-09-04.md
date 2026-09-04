# Phase 5 Qt restore result evidence validation (2026-09-04)

## Decision

Qtは例外文言からmutation結果を推測しない。production worker taskはcoordinatorが返す、永続storeからstrict再読込した、または専用persistence errorが公開する`RestoreExecutionEvidence`だけをbounded resultへ変換する。

## Result contract

- 許可stateは`committed`、`failed`、`unknown`だけである。
- error codeとresultの永続化有無をstateと別に表示する。
- executorがFAILED evidenceを保存後に元例外を再送出しても、worker taskはstrict再読込したevidenceを返す。
- persistence errorでは例外に付随するevidenceを返し、storeから再読込できたかを`persisted`へ記録する。
- evidenceがないpreflight/start-audit/attempt-only failureは通常のworker errorとし、stateを推測しない。
- 未知state、persisted flag欠落、不正resultは`invalid_restore_result`として拒否する。
- どの結果でもpreview/approvalを消費し、次の明示inventory refreshまでrunを無効にする。

## Validation

sandbox compositionで復号中の外部target変更を注入し、内容を変更せず永続済みFAILED evidenceと`stale_restore_target`をworker resultとして取得した。

Ubuntu 26.04、PySide6 6.10.2、Qt offscreenでworker lock testとresult rendering testの2件が成功した。初回Gateで文字列stateが`none`表示になる正規化不具合を検出し、enumと文字列の両方を同じ明示値へ正規化して再Gateした。COMMITTED、FAILED、UNKNOWN、`persisted=false`、未知state拒否を確認した。最終artifact SHA-256は`d7782043595075bde2530601c5d93c171f4be55461c7334856692e13dc65a072`で一致し、VMの一時Gate directoryは削除した。

実OpenCode/Ollama設定、systemd、SSH設定は変更していない。production `main()`へのrestore task注入も行っていない。

main hostの全448件は0.518秒で成功し、PySide6依存12件と明示Secret Service Gate 2件の計14件をskipした。compileall、local/remote packaging shell構文、`git diff --check`も成功した。

## Next

明示inventory refresh後に最新execution evidenceが一覧へ反映されるend-to-end sandbox Gateを行い、local user production restore公開可否を判定する。
