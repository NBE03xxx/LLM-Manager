# Phase 6 production診断 performance Gate（2026-09-05）

## 目的と範囲

Ubuntu 26.04 VMで、`DiagnosticTaskFactory.production`が構成する実local read-only診断を`QtTaskRunner`から実行し、UI event loop、終端、CPU、memoryを測定した。実Ollama/OpenCode設定、systemd unit、SSH設定へのmutationは行っていない。

このGateは単一sampleであり、対応hardware全体の性能保証や長時間Agent workloadの代替ではない。VMには診断対象runtime/clientが揃っていないため、期待どおり`partial`へ縮退した。

## 条件

- VM: Ubuntu 26.04、通常user `yoshimi`
- Qt: VM導入済みPySide6、`QT_QPA_PLATFORM=offscreen`
- artifact SHA-256: `6cc0197d107d8b06330507d9f836b545499bbe05a4b9181236775584976d21e3`
- task: production local host diagnosis
- event sentinel: 10 ms `QTimer`
- Gate: structured result、2 ticks以上、最大event gap 250 ms未満、完了後worker非active

## 結果

| 指標 | 結果 |
|---|---:|
| Report | `partial` |
| Worker elapsed | 25.234 ms |
| Process CPU | 3.923 ms |
| Qt event ticks | 2 |
| Maximum event gap | 10.383 ms |
| Process内 `ru_maxrss` | 67,352 KiB |
| `/usr/bin/time -v` elapsed | 0.24 s |
| `/usr/bin/time -v` user / system | 0.19 s / 0.03 s |
| `/usr/bin/time -v` maximum RSS | 69,392 KiB |
| Worker active after finish | false |
| Exit | 0 |

250 msはこのGateのfreeze検出上限であり、製品全経路の確定SLOではない。短いrunのためevent tick数とCPU/RSSは基準値としてのみ扱う。

## Cleanup

guest/hostのscriptとartifact、転送HTTP serverを削除した。`ubuntu26.04`と`debian13`はGate後に`shut off`であることを確認した。

## 残件

- Ollama/OpenCode導入済みの対応環境でcomplete診断を複数sample測定する。
- SSH診断、Apply/validation/rollback、長時間Agent相当の実production backendでevent gap、cancel到達、RSSを測定する。
- hardware基準とsample数を定めてrelease性能判定値を固定する。
