# Phase 0 Traceability Matrix

| Requirement | Design artifact | Planned verification | Gate |
|---|---|---|---|
| FR-HOST-01 | architecture, ADR-0001 | `OpenSshHostAdapterTests`完了、ProxyJump/host-key実環境統合待ち | Phase 2一部完了 |
| FR-DIAG-01..03 | diagnostics, version matrix | `LinuxParserTests`, `LinuxProbeTests`, partial report完了、実環境待ち | Phase 2一部完了 |
| FR-OLLAMA-01 | version matrix, allowlist | `OllamaAdapterTests` fixture完了、0.33.2実環境待ち | Phase 2/3 |
| FR-OPENCODE-01 | version matrix, allowlist | `OpenCodeAdapterTests` JSONC fixture完了、1.18.25探索統合待ち | Phase 2/3 |
| FR-PROFILE-01 | optimization, rule fixtures | `ProfileGoldenTests`、3 profile定義 | Phase 3完了 |
| FR-REC-01..02 | optimization, ADR-0002 | `RuleEngineTests`, `ConflictTests` | Phase 3完了 |
| FR-PLAN-01..02 | allowlist, safe-apply | `OpenCodePlannerTests`, `OllamaDropInPlannerTests` | Phase 3完了 |
| FR-APPROVE-01 | data-model, safe-apply | `ApprovalTests`, `CoordinatorTests`（plan/report/change hash・期限・apply統合） | Phase 4 core完了 |
| FR-BACKUP-01 | ADR-0005, threat model | `LocalBackupStoreTests`（local integrity/permission/restart reload/retention/protection）、dual copy/encryption待ち | Phase 4一部完了 |
| FR-APPLY-01 | ADR-0004, allowlist | `AtomicExecutorTests`, `CoordinatorTests`, `HelperProtocolTests`, `HelperStagingTests`, `DeclaredHelperExecutorTests`, `LocalSystemHelperBackendTests`, `HelperCliTests`, `HelperReceiptStoreTests`, `LocalPolicyKitInvokerTests`, `ApprovedHelperRequestFactoryTests`, `PrivilegedSafeApplyCoordinatorTests`, `PrivilegedBoundaryIntegrationTests`, `DebianPackagingTests`（path/symlink/stale/write failure、canonical request/hash/expiry/operation/path/unit/metadata allowlist、derived staging/owner/mode/mutation、before hash再検証、固定順序、fail-stop、atomic root file backend、固定systemctl argv、固定request導出、root/invoking UID、PolicyKit action静的検査、atomic replay claim/terminal receipt、固定pkexec argv/result/deny/timeout、Approval/Plan/ChangeSet/backup manifest/helper request/journal束縛、root workflow故障注入、Coordinator→staging→CLI→receipt→executor→sandbox backend境界統合、deb build/artifact ownership/mode/isolated entrypoint）、実install/PolicyKit desktop Gate待ち | Phase 4一部完了 |
| FR-VALIDATE-01 | allowlist, version matrix | `FileValidatorTests`, `ProductRuntimeValidatorTests`, `OllamaAdapterTests`, `OpenCodeAdapterTests`, `CoordinatorTests`（file hash/JSONC/systemd drop-in構文、service/API/effective environment、再読込、失敗時rollback） | Phase 4一部完了（実systemd/helper integration Gate待ち） |
| FR-ROLLBACK-01 | ADR-0005, threat model | `CoordinatorTests`, `PrivilegedSafeApplyCoordinatorTests`（逆順restore/remove-created、reload/restart、各段階の故障とrecovery required）、disconnect待ち | Phase 4一部完了 |
| FR-AUDIT-01 | threat model | `LocalAuditLogTests`, `CoordinatorTests`, `LocalOperationJournalTests`（redaction、hash-chain永続化、tamper/deletion/replay/state reconciliation） | Phase 4 core完了 |
| FR-I18N-01..02 | ADR-0006, gui | ja/en/fallback/key completeness/layout | Phase 5 |
| AC-09/10 | ADR-0003, architecture | `ArchitectureTests`（domain依存境界）、Phase 5でQt event-loop | Phase 1完了/5 |
| AC-13/14 | allowlist, ADR-0004/0005 | unknown version denial、`LocalOperationJournalTests`（before/after/unknown）、remote統合待ち | Phase 4一部完了 |
| SSH helper prerequisite | ADR-0008, version matrix | absent/incompatible/owner-mode/package tests | Phase 2/4 |
| Backup crypto/recovery | ADR-0009, threat model | `BackupCryptoTests`, `SecretServiceKeyProviderTests`, `BackupSettingsTests`, `LocalBackupStoreTests`, `CoordinatorTests`（AES-GCM/AAD/nonce/tamper/key scope/size/key create-reuse/cancel/build default/user persistence/plaintext acknowledgement/restore/approval invalidation）、desktop keyring Gate・remote統合待ち | Phase 4一部完了 |
| Endpoint confinement | ADR-0010, setting allowlist | loopback allow、external/redirect/userinfo deny | Phase 3/4 |
| OpenCode safe edit | ADR-0011, setting allowlist | scalar span、comment、escape、byte-diff fixtures | Phase 3/4 |

Release checklistでは各行を具体的なtest IDへ置換する。設計artifactだけで受け入れ条件を完了扱いにしない。
