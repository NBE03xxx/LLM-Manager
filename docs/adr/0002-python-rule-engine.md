# ADR-0002: MVP Rule Engineは型付きPython定義とする

- Status: Accepted
- Date: 2026-08-29

## Decision

predicate、bounded calculator、metadataを型付きPython objectとして定義し、評価器はpure/deterministicにする。YAML内の任意式・Python・template code実行を禁止する。

## Consequences

型検査と境界testが容易になる。非開発者更新は弱いが、rule modelをserialize可能にし、将来は制約付きdata catalogへ移行できる。
