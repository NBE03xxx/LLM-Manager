# ADR-0007: 診断対応と自動変更対応を分離する

- Status: Accepted
- Date: 2026-08-29

## Decision

Ubuntu 26.04、Debian 13、Python 3.14.4、PySide6 6.8.6以上、Ollama 0.33.2、OpenCode 1.18.25をbaselineとする。D（診断）とA（自動変更）をfixture gateで分け、未知versionはR/read-onlyとする。

## Consequences

近いversionを推測で変更しないため安全だが、releaseごとのschema/API fixture維持が必要になる。runtimeで取得した最新schemaからA対応を自動拡張しない。
