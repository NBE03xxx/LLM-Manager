# ADR-0006: 日本語・英語をUI境界で解決する

- Status: Accepted
- Date: 2026-08-29

## Decision

ja/en catalogを提供し、初回はOS/Qt locale、明示設定を優先、未対応localeは英語へfallbackする。domain/applicationはmessage keyとtyped argumentsを返す。

## Consequences

永続modelと監査がlocale非依存になる。翻訳key完全性、英語fallback、日本語/英語layout、安全警告の意味一致をtestする必要がある。
