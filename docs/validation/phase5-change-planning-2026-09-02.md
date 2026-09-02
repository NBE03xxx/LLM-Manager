# Phase 5 ChangeSet Planning Validation — 2026-09-02

## Scope

Recommendationsで明示選択した項目から、実行可能なOpenCode ChangeSetを作る前のread-only再検証application境界を実装した。Apply、file write、SSH設定、Ollama、OpenCode、systemdの変更は行っていない。

## Contract

- OptimizationPlanのreport ID/hash/expiryとselected IDsをI/O前に検証する。
- selected recommendationはactionable、非conflict、診断時のactive OpenCode config対象に限定する。
- hostを再identifyし、reportのhost ID、kind、fingerprintと一致しなければconfigを読まない。
- configはHostPortから最大1 MiBでread-only再取得し、strict UTF-8、active path、baseline version、parse状態、既存scalar/current valueを再検証する。
- ChangeSetはsource span、再取得内容のbefore SHA-256、masked diffを持ち、選択IDを保持する。
- stale report/plan、identity変更、不正選択、target不一致、非UTF-8、空ChangeSetはfail closedとする。

## Results

fake HostPortと実OpenCode plannerを使い、compaction 2項目のChangeSet、read順序、before hash、selected ID保持を確認した。stale report、期限切れ、host fingerprint変更、未選択、非actionable、非UTF-8を拒否した。focused 17 testsは全件成功した。

Qt workerからの再接続・再読込とReview画面へのmasked diff表示は後続Phase 5 Gateとする。
