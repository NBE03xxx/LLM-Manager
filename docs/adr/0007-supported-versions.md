# ADR-0007: 診断対応と自動変更対応を分離する

- Status: Accepted
- Date: 2026-08-29

## Decision

Ubuntu 26.04、Debian 13、Python 3.14.4、PySide6 6.8.6以上、Ollama 0.33.2、OpenCode 1.18.25をbaselineとする。D（診断）とA（自動変更）をfixture gateで分け、未知versionはR/read-onlyとする。

Python 3.14.4は検証baselineとして維持する。一方、正式対象Debian 13のstock runtimeを配布対象に含めるため、applicationとdebのsupported minimumはPython 3.13、cryptography 43.0.0、SecretStorage 3.3.3とする。この下限はDebian 13 desktop実機Gateで全338単体テスト、AES-GCM、Secret Service、PolicyKit、local/remote helper runtimeを通過した組合せに束縛する。

## Consequences

近いversionを推測で変更しないため安全だが、releaseごとのschema/API fixture維持が必要になる。runtimeで取得した最新schemaからA対応を自動拡張しない。
