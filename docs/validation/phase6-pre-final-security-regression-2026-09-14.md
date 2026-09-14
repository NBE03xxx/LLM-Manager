# Phase 6 pre-final security regression — 2026-09-14

## 結果

現行 `main` の `7c5dbef` で、公開前に再確認するsecurity境界をfocused
regressionとして実行した。製品source、test、packaging、version surfaceは採用candidateの
source commit `ff7913bb97e896f7992720b9a43c2382970a5fc8` から差分がない。

- 全回帰: 806件、767成功、39 expected skip
- focused security回帰: 159件、158成功、1 expected skip
- local/remote candidate deb verifier: 両方成功
- compileall、packaging shell構文、desktop validation、直接依存SBOM 2件のJSON parse、
  `git diff --check`: すべて成功
- candidate local deb SHA-256:
  `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`
- candidate remote helper deb SHA-256:
  `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`

focused regressionは次の境界を明示的に含む。

| 境界 | 主な検査 |
| --- | --- |
| secret corpus / redaction | common secret形式、分離argv値、環境変数、quoted assignment、stderr、audit/UI errorのredactionと出力上限 |
| symlink / path traversal | local backup、root evidence、helper staging/backend、application root、environment evidence archiveのsymlink・hardlink・FIFO・traversal・unsafe ancestor拒否 |
| owner / mode | private state/staging/backup、root evidence、helper、PolicyKit callerのowner/mode不一致拒否 |
| stale approval / hash | plan/report/change set/backup policy/target/request/review/evidence hashの再照合とmutation前拒否 |
| PolicyKit deny / cancel | denyをpre-execution終端として扱いrollback helperを起動しないこと、timeout/late cancel/pre-cancelで成功を推測せずone-shotを維持すること |
| SSH fingerprint変更 | host key failure、fingerprint欠落・曖昧・形式不正、診断後のfingerprint変更をI/Oまたはcomposition前に拒否すること |

実行したfocused moduleは以下。

```text
tests.test_redaction_and_process
tests.test_safe_apply
tests.test_approval
tests.test_helper_backend
tests.test_helper_cli
tests.test_helper_staging
tests.test_local_user_apply_composition
tests.test_root_backup_capture
tests.test_root_backup_evidence
tests.test_local_root_restore_preflight
tests.test_root_restore_execute_client
tests.test_openssh_identity
tests.test_ssh_auth
tests.test_ssh_user_apply_composition
tests.test_policykit
tests.test_privileged_apply
tests.test_environment_evidence
```

expected skipは明示opt-inが必要な実Secret Service desktop Gate 1件である。この実境界は
[local user manual restore通常GUI Gate](phase6-local-user-restore-gui-2026-09-14.md)で
現candidateの実Secret Serviceと結合済みである。active desktopのPolicyKit cancel/authは
[interactive PolicyKit Gate](phase6-root-restore-interactive-policykit-2026-09-08.md)と
[local root manual restore通常GUI Gate](phase6-local-root-restore-gui-2026-09-14.md)に分離して
保存済みで、今回それらのoperationを再実行していない。

## 判定と限界

現candidate sourceに対するpre-final security回帰は成功した。今回の実行は
`UNRELEASED` candidateを対象とし、最終release artifact、最終OS lifecycle、署名・tag・公開の
代替ではない。そのためrelease checklistの「最終commitで再実行」は未完了のままとする。
`UNRELEASED`解除後にsource identityを再確認し、同じfocused/full回帰と必要なdesktop Gateを
最終artifactに対して反復する。
