# ADR-0008: SSH先helperは別debで事前導入する

- Status: Accepted
- Date: 2026-08-29

## Decision

Local helperは本体debに同梱し、remote helperは同じsource/protocolから別debとして配布する。SSH先の管理者が事前導入する。GUIは固定path、package/version、protocol、root owner/modeを診断し、欠落・非互換時はread-onlyへ縮退する。自動install/upgradeはしない。

## Consequences

初回利用手順は増えるが、未review binaryを接続時にroot導入せずに済む。app/helper versionが異なってもprotocol compatibility tableで判定できる。
