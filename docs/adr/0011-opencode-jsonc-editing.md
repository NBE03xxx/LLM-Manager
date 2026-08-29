# ADR-0011: OpenCode Configは既存ScalarのSource Spanだけ置換する

- Status: Accepted
- Date: 2026-08-29

## Decision

MVPの自動変更は、既存global JSON/JSONC内のallowlist scalar valueをtoken scannerで特定し、そのsource spanだけを置換する。構造追加・削除、ファイル新規作成、全体再serializeはしない。変更後は再parse、tag schema、expected path/value、byte diff scopeを検証する。

## Consequences

コメント、並び、空白、未知fieldを保持しやすく、既知のJSONC insertion問題を避けられる。一方、keyが存在しない設定は手動手順になる。scanner fixtureと文字列escape/number/boolean境界testが必要になる。
