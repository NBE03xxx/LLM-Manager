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

## Qt worker / Review Gate

Localまたはstrict identity確認済みSSH hostへChangeSet生成workerから再接続するcompositionを追加した。診断と同じhost単位lock、CancellationToken、system OpenSSH、必要時だけの外部terminal ControlMasterを使い、成功・失敗を問わず一時SSH sessionを閉じる。生成中はhost/profile/selectionを固定する。

成功したChangeSetだけを保持し、Reviewへtarget、masked diff、root/restart要否を表示する。不正なworker result、plan/selection不一致、生成失敗、cancelではChangeSetを表示せずstable errorで停止する。Apply、承認、file writeは呼び出さない。

Ubuntu 26.04 VM、Python 3.14.4、PySide6 6.10.2、`QT_QPA_PLATFORM=offscreen`で次を実行した。

```text
python3 -m unittest tests.test_ui_qt_runtime tests.test_ui_composition tests.test_ui_workflow -v
Ran 25 tests in 0.121s
OK
```

main workstationでは全397件が成功し、PySide6不在によりruntime 4件だけを想定どおりskipした。明示承認とstale失効、Apply接続は後続Phase 5 Gateとする。
