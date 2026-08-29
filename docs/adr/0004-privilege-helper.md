# ADR-0004: 特権操作は限定helperへ委譲する

- Status: Accepted
- Date: 2026-08-29

## Decision

debがroot-owned固定pathへhelperとPolicyKit actionをinstallする。Localはpkexec、SSHはsudoで同じhelper protocolを使う。helperは期限付き宣言request、allowlist、before/content hash、owner/modeを検証し、任意commandを受け取らない。

## Consequences

GUIをrootで動かさずroot変更が可能になる。pkexecは引数を検証しないためhelperのschema/allowlist検証がsecurity boundaryとなる。helper protocolとpackage upgradeの互換管理が必要になる。
