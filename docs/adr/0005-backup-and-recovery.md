# ADR-0005: Local正本とRemote復旧用copyを保持する

- Status: Accepted
- Date: 2026-08-29

## Decision

SSH対象はlocal正本とremote copyの双方を検証してからApplyする。30日かつ10世代、保護backupは自動削除しない。一般配布は暗号化ON、開発モードはOFF、ユーザー変更可。operation journalとbefore/after hashで切断後を照合する。

## Consequences

復旧経路は増えるが秘密情報のcopyも増える。権限制限、AEAD、Secret Service、retention、両copyの削除整合性が必要になる。片側backup失敗時はApplyしない。
