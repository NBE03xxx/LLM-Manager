# ADR-0001: System OpenSSHを利用する

- Status: Accepted
- Date: 2026-08-29

## Decision

SSH transportはsystem `ssh`をargvで起動し、`~/.ssh/config`、agent、known_hosts、ProxyJumpへ委譲する。秘密鍵やpasswordを保存しない。対話sudoはexternal terminalの`ssh -t`からremote helperを実行する。

## Consequences

既存運用との互換性が高い一方、結果parse、timeout、cancel、safe remote argv encodingが必要になる。Paramiko等への置換はHostPort内部に限定できる。
