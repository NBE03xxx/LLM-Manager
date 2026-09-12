# Phase 6: long-running Agent Gate definition and preflight

## 時間と合格条件

MVP releaseの長時間Agent Gateは、**60分（3600秒）連続**のAgent相当workloadを
production Qt workerと`SubprocessRunner`境界で実行し、その後GUIの取消buttonから
cancelする試験と定義する。4時間soakは任意の追加耐久試験で、60分Gateの代替や
必須条件にはしない。

60分中と取消後に以下を満たすことを必須とする。

- Qt event loopの最大gapが250 ms未満。
- GUIが`running`を表示し、実行中は開始button無効・取消button有効。
- 取消要求後は`cancel_requested`、終端は`operation_cancelled`と明示される。
- cancelからworkerとchildの回収まで1000 ms未満。
- 親processのRSS増加が64 MiB以下、CPU平均が1 coreの25%以下。
- child RSSが128 MiB以下、周期的heartbeatが10秒以上途切れない。
- watchdogを使わずworkerがinactiveとなり、childがreapされる。

## 測定実装

再実行用に`packaging/measure-long-running-agent.py`を追加した。既定時間は3600秒。
短い`--duration-seconds`は測定器のpreflight専用で、結果JSONの
`gate=preflight`と`release_duration_met=false`によりrelease Gateと区別する。

workloadは32 MiBの固定working set、SHA-256計算、約4秒ごとのbounded JSON progressを
持つ合成Agent相当processである。利用者設定、network API、モデル推論、package、serviceを
変更しない。実モデル推論を含む長時間試験ではないため、モデル接続条件が揃った場合は
別の追加Gateとして扱う。

## Ubuntu 26.04 preflight

commit `b15a98454ddf9e397333350d371b35cc2ed8fdd8`のtracked `src`と追加した測定scriptを
archive化し、Ubuntuの`/tmp`だけへ転送した。archive SHA-256は
`85ee5b3f9de316ab240602bf9adb91f3a53a09850a37da232cc57f30737f097c`。
通常user UID 1000、Python 3.14.4、PySide6 6.10.2、offscreen Qtで15秒preflightを実行。

- 最大event gap: 55.976 ms
- cancelから回収: 6.198 ms
- 親RSS増加: 2,640 KiB
- 親CPU比率: 0.005453
- child peak RSS: 50,316 KiB
- `running → cancel_requested → failed / operation_cancelled`
- child reap、worker inactive、watchdog不使用を確認

[測定JSON](phase6-long-running-agent-preflight-2026-09-12.json)の全preflight必須checkは
true。`release_duration_met`は意図どおりfalseであり、60分Gateは未完了。
guestの一時treeは削除し、package、設定、service、VM電源状態、snapshotを変更していない。

## 残件

同じ測定器を既定3600秒で完走し、結果を保存・reviewする。これは約60分を要するため、
中断せず監視できる実行枠で行う。最終artifact確定後にも必要に応じて再実行する。
