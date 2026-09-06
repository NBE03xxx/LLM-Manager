# Phase 6 root restore persistent review/attempt/result — 2026-09-05

現在・次ともPhase 6。`RootRestoreStore`を追加し、レビュー、実行開始、結果の不変レコードを実filesystemで検証した。root restore executorやproduction dispatchはまだ未接続。

## 保存と読取

固定directoryは`/var/lib/llm-manager/local-root-restore/executions`（root:root 0700）。openerは全ancestorをroot-owned/non-writable/no-followで確認し、directoryを作成・修復しない。各要求は`<request_id>.review.json`、`.attempt.json`、`.result.json`（root:root 0600、単一hardlink）を使用する。

canonical recordはkind/payload/hashを持ち、kindもhash対象にする。reviewはapproved requestとorigin/source hash・承認/期限、attemptはrequest/review hashと開始時刻、resultはrequest/attempt hash・状態・完了時刻・bounded error codeを束縛する。最大16 KiB。type/未知field/canonical/filename bindingを再確認する。

独立open descriptionのnonblocking shared/exclusive lock、O_EXCL pending、file fsync、非上書きlink/unlink、directory fsyncで永続化する。pending/未知entry、symlink、不正metadata、改変、orphan resultを検出したnamespaceは「未使用」と返さない。単一directoryは10000 entryを上限としてfail closedにし、retention/scalingは後続課題とする。

## 状態と再実行防止

`begin`は独立caller/host/hash、fresh request、保存reviewとの完全一致、review期限を検証し、既存attempt/resultがない場合だけattemptを保存する。既存IDへ別hashを割り当てたり、attempt-only/failed/unknownを新規要求として再試行したりしない。

`finish`は保存済みattemptとのcanonical一致を確認し、committed/failed/unknownの結果を1回だけ保存する。committedではerrorなし、failed/unknownでは短い識別codeを必須とし、free textを結果へ保存しない。resultを上書き・昇格するAPIはない。

review期限後のbeginは拒否するが、過去のattempt/resultは期限と分離して構造検証し、読み取りや遅れて返った結果の保存ができる。attempt-onlyとfailed/unknownはattention、正常committedはattentionなし。途中recordの場合は明示例外で停止し、UIが成功やunusedへ推測変換してはならない。

書込み/fsync失敗は不確定として例外を返す。pendingを自動削除しない。directory fsync失敗後にattemptが見えている場合も、再実行は拒否する。

## 統合と検証

新規14 test（store 13＋preflight統合1）を追加。実fileの再読込、全result状態、期限と履歴、別hash同ID、改ざん/symlink/orphan、pending、attempt/result保存失敗、公開後directory fsync失敗、cancel、result binding、競合lock、rehash済み別review参照を確認した。

従来の統合testのin-memory review/unused-attemptを実storeへ置換し、明示key provisioning→capture→AES-GCM→origin verifier→実target observation→保存review/attemptを使うpreflightまで確認した。attempt永続化後の再preflightは拒否し、対象fileは変更していない。

全614 test完走（591成功・23 skip）。compileall、packaging shell syntax、desktop validation、diff check成功。実root/PolicyKit/VM Gateではなく、owner UID/GIDはsandboxへ明示注入した。実設定、backup/key、SSH、VMは操作していない。

## 残るtrust boundary

`save_review`は将来のtrusted review producer向けAPIであり、user reviewのimportや、root-owned fileにコピーするだけの承認生成へ使わない。今回の統合testも明示承認を確立するproduction UI/PolicyKit経路の検証ではない。

`begin`は永続attemptを作るが、それだけでmutation authorityにはならない。preflightからbeginまで、および対象の最終照合〜mutationの排他区間、開始audit、復号後照合、単一target executor、service検証、crash/reconciliationを構築する必要がある。store lockは個々のrecord処理だけを保護し、異なる要求による同じtargetの同時mutationをまだ防止しない。

次もPhase 6。専用実行coordinatorと最終照合/lock/audit境界を実装し、sandboxでfault injectionを進める。root routeは非公開、全変更は未コミット。保存済みdeb/SBOMを今回codeの証拠とは扱わない。
