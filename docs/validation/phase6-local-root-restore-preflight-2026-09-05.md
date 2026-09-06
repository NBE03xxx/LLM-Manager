# Phase 6 local root restore read-only preflight — 2026-09-05

## 実装

現在・次ともPhase 6。専用intent codecに続き、`CheckLocalRootRestore`と`RootRestorePreflightPort`を追加した。独立caller/host、request hash、承認済みrequest全体、backup/current metadata、要求/review期限、requestの未使用状態を確認する。backup検証後にもreview/current/attemptを再読込する。戻り値は確認結果であり、mutation authorityや予約ではない。

codecによる形の検証を、信頼できるbackupの証明とは扱わない。root-owned記録のproduction producer/reader、実target observer/decryptor、lock/attempt/audit/executorは未接続。GUI availability、既存helper、実設定、VMは変更していない。

## 検証

新規10 testで以下をsandboxの注入portから検証した。

- replace/create/remove intentについて、backup検証の前後の再照合と最短期限を確認
- caller/host/hash不一致と事前cancelではI/Oなし
- hashを再生成した別backup/manifest/inventory/preview/approval/request/復元状態を拒否
- evidence欠落、不正型、未来の承認、過大/失効期限を拒否
- used/unknown attempt、不正または変更済みcurrent/backupを拒否。boolと整数の混同も拒否
- backup検証中のreview変更、target変更、新しいattemptを後続照合で拒否
- 全7 readの各直後でcancel・request期限切れ・review期限切れを注入し、次のI/Oへ進まないことを確認
- 各readの例外を成功へ変換せず停止

初回testでNoneのreview evidenceが未検証のまま後続readへ進む問題を検出し、最初/再読込の両方で必ずreview型・内容を検証するよう修正した。

全563 test完走（540成功・23 skip）。compileall、local/remote packaging shell syntax、desktop-file validation、diff check成功。実filesystemでの特権owner/no-symlink/復号・競合の検証ではない。

## 次

[専用契約](../local-root-restore-protocol.md)へ実装範囲と限界を追記した。次もPhase 6: 特権側が採取したbackup origin証拠のproducer/保存形式を確定し、strict read-only adapterを作る。user-owned manifestをコピー・rehashするだけでroot authorityを作らない。旧backupの取扱い、鍵/retention、immutable attempt/result、PolicyKit/Qt/両OS Gateが揃うまでroot restoreは公開しない。

既存変更と今回の変更はすべて未コミットで保持。保存済みdeb/SBOMには本preflightが収録済みとは扱わない。
