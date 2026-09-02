# Phase 5 OpenSSH Identity Validation — 2026-09-02

## Scope

Hosts/Diagnose GUI compositionへ渡すSSH identityを、alias文字列や未検証known_hosts entryから推測せず、system OpenSSHのeffective configと実接続結果から確定する境界を実装・検証した。SSH設定、known_hosts、Agent、remote host、Ollama、OpenCode、systemdは変更していない。

## Contract

- `ssh -G -- <alias>`でeffective hostname、port、HostKeyAliasを取得する。
- identity probeは`BatchMode=yes`、`StrictHostKeyChecking=yes`、`UpdateHostKeys=no`、`RemoteCommand=none`、`RequestTTY=no`と固定remote `true`だけを使う。
- probeがexit 0で完了し、OpenSSH debug outputに一意で正規形のserver host-key SHA-256 fingerprintがある場合だけ成功する。
- nonzero、timeout、host-key変更、認証失敗、fingerprint欠落/複数/不正、alias/config不正はreport生成前にfail closedとする。
- fingerprint値はvalidation outputと文書へ保存しない。

## Results

fake runnerではeffective destination、HostKeyAlias、ED25519 fingerprint binding、固定argv、alias injection、invalid port、config failure、timeout、nonzero、missing/ambiguous/malformed fingerprintを検証した。production compositionは成功時だけ検証済みfingerprintを`OpenSshHostAdapter`へ注入する。

既存alias `development`へのread-only実Gateはidentity probeが10秒でtimeoutした。fingerprintを公開・保存せず、diagnosisとreport生成へ進まなかった。到達可能hostでのpositive Gateと、password認証が必要なhostで既存external-terminal ControlMasterを利用する統合は後続Phase 5 Gateとする。
