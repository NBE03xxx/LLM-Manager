# ADR-0003: GUIの短期taskはQThreadPoolを使う

- Status: Accepted
- Date: 2026-08-29

## Decision

同期PortをQThreadPool/QRunnable上で実行し、signalでprogress/result/error/cancelledをUI threadへ返す。Apply workflowはhost lock下で直列化する。asyncio全面採用はしない。

## Consequences

Qt event loopとの統合が単純になる。長寿命helper監視が必要なら専用QThreadを限定利用し、多数hostが必要になった時点でasyncio統合を再評価する。
