# LLM-Manager Phase 5 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 5 PySide6 GUIのlocal production restore desktop Gate監査から続行してください。

## 作業場所

- `/home/yoshimi/WorkSpace/LLM-Manager`
- GitHub: `git@github.com:NBE03xxx/LLM-Manager.git`
- branch: `main`
- 最新実装/evidence commit: `da33477 Compose local production restore`（この引き継ぎ更新のcommitが後続する）
- `main`と`origin/main`は同期済み、作業ツリーはclean

## Phaseと確定済み要件

- Phase 0〜4は完了。現在はPhase 5 PySide6 GUI
- 正式対象: Ubuntu 26.04、Debian 13
- 初期検証baseline: Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25
- Debian 13 supported minimum: Python 3.13、cryptography 43.0.0、SecretStorage 3.3.3
- UIはlocaleに基づく日本語・英語
- root必須systemd drop-inまでMVP対象だがGUI全体はrootにしない
- SSHはsystem OpenSSHと既存`~/.ssh/config`、Agent、ProxyJump、外部terminal ControlMasterを利用
- 秘密鍵/passwordを独自保存しない
- backupはlocal正本＋SSH先復元用copy、30日かつhostごと直近10世代、manual protectionは削除しない
- 一般配布は暗号化既定ON、開発モード既定OFF

## 禁止事項

- 実Ollama/OpenCode設定、既存systemd unit、SSH設定を無断変更しない
- passwordをチャットで尋ねず、argv/stdin/logへ渡さない
- main workstationへdebやdependencyを無断installしない
- disposable OSでもmaterialなPolicyKit/sudoers/systemd変更は先に承認を得る
- venv作成、`pip install`禁止
- restore/delete/cleanupをinventoryやrestart状態から自動実行しない

## 実機・VM

- `development`: 192.168.1.201、Ubuntu 26.04、OpenCode 1.18.18、Ollamaなし
- AI server: `yoshimi@192.168.1.253`、Ubuntu 26.04、Ollama 0.33.2 active、OpenCodeなし
- disposable `llm-manager-gate`: Ubuntu 26.04。Gate専用artifactはcleanup済み、通常`sudo -n`拒否
- desktop VM `ubuntu26.04`: PySide6 6.10.2導入済み。Qt offscreen Gateに使用
- desktop VM `debian13`: Debian 13.6、password-backed GNOME、自動loginなし
- passwordはrepository/chat/artifactへ保存していない
- main hostにはPySide6がない。ユーザーは「PySide6 installが必要なら知らせる」よう依頼済み。現状はVMで足りるためinstall不要

## Phase 4完了要約

- Safe Apply、AES-GCM/Secret Service、atomic user apply、PolicyKit local root helper
- remote helper protocol、SSH user staging、root recovery copy、retention/deletion/reconciliation
- immutable audit/journal/evidence、strict restart loading、retention cleanup安全境界
- Ubuntu 26.04/Debian 13 package・Secret Service・PolicyKit・SSH実機Gate完了
- 実Ollama/OpenCode targetへのApply/rollbackは無断変更禁止のため意図的に未実施

## Phase 5完了済み

- PySide6 boundary、worker/QThreadPool、ja/en UI、host discovery
- Diagnose→Recommendations→Review→exact approval→Results workflow
- system OpenSSH診断、外部terminal ControlMaster auth fallback
- recommendation/change-set生成、秘密値redaction
- 明示承認checkbox、plan/host/profile/selection/expiryによるstale失効
- production Apply availabilityを4 routeでfail closed評価。local userのみ接続済み、他3 routeは未接続
- local user GUI Applyのsuccess/rollback/`RECOVERY_REQUIRED` vertical slice
- Backup/Rollback read-only inventory UIとstrict local manifest/journal restart loader
- SSH production inventoryはsafeなbackup列挙commandがないため未接続
- metadata-only restore preview、exact approval、5分expiry、host/refresh/selection/timer失効
- strict restore preflight: manifest/preview/approval/allowlist/current targetを直前再検証
- sandbox single-target restore executor: 復号前後再検証、atomic replaceまたはunlink+fsync。複数target拒否
- immutable restore attempt/result、authorization一回消費、開始/完了audit
- commit後audit失敗は`UNKNOWN`、result保存失敗は生成済み`COMMITTED` evidenceを公開
- restore restart inventory: attempt-onlyをattention表示、自動retryなし、unknown/orphan/tamper拒否
- local user production restore compositionは接続済み。GUI実行buttonは未接続

## 最新commit

- `da33477 Compose local production restore`
- `823d7c9 Show strict restore execution inventory`
- `3a2049e Persist local restore execution evidence`
- `b6c6797 Add sandbox single-target restore executor`
- `78d1b5a Add strict local restore preflight`
- `f6546ba Validate restore preview expiry`
- `95328bb Add restore preview approval UI`
- `7c9b1a3 Add bound local restore preview`
- `92a88f1 Audit SSH backup inventory boundary`
- `46beabe Connect strict local backup inventory`
- `d662d4b Add read-only backup inventory UI`
- `85ee6e5 Validate GUI Apply failure outcomes`
- `abeb517 Validate local user GUI Apply path`
- `39645eb Enable local user production Apply route`

## 最新validation

- main host全test: 444件成功、PySide6依存11件と明示desktop Gate 1件の計12件skip
- Ubuntu 26.04 desktop Secret Service restore Gate: 1件、0.080秒、成功。Gate keyと一時directoryはcleanup済み
- Ubuntu 26.04/PySide6 restore restart inventory Gate: 12件、0.091秒、全成功
- 直前artifact SHA-256: `11fe7441870b0f259c56d10132224f03339e52e68ed39f3bda49865c71b7539b`
- ユーザー側`/tmp/llm-manager-ui-gate`は未cleanupの可能性あり

主要evidence:

- `docs/validation/phase5-local-restore-preview-2026-09-04.md`
- `docs/validation/phase5-local-restore-composition-2026-09-04.md`
- `docs/validation/phase5-backup-inventory-ui-2026-09-04.md`
- `docs/validation/phase5-local-user-apply-sandbox-2026-09-04.md`
- `docs/validation/phase5-production-apply-audit-2026-09-04.md`
- `docs/validation/phase5-approval-invalidation-2026-09-03.md`
- `docs/validation/phase5-change-planning-2026-09-02.md`
- `docs/validation/phase5-controlmaster-integration-2026-09-02.md`
- `docs/validation/phase5-qt-runtime-2026-09-01.md`

## 次の作業

まずlocal production restoreのQt実行境界を監査する。

1. preview/approval/preflight authorizationとQt host lock、worker、expiry timerを照合
2. host/refresh/selection/timer失効後にauthorizationを生成・実行できないことを判定
3. double click、worker中のhost変更、完了後replayをfail closedにする契約を設計
4. GUI実行buttonを接続する場合もsandbox factoryから先にGateし、production既定は監査完了まで公開しない
5. materialな仕様変更が不要なら実装し、全必須検査、commit/push

## 重要な安全境界

- local restore executorは単一target限定。複数targetはfail closed
- previewはmetadata-only。content/鍵をUIへ渡さない
- authorizationはattempt保存で一回消費。attempt-onlyは自動再実行しない
- commit後evidence失敗を未変更と推測しない
- inventory/reconciliationはread-onlyでmutation authorityにしない
- remote inventoryはsafeな固定列挙protocolがない限り未接続
- `PARTIAL`/`FAILED`/`UNKNOWN`後のmutation retryには新しい明示requestが必要
- local正本はremote失敗時も保持
- remote journal取得は固定`read-journal-evidence <operation-id> <request-hash>`だけ

## 作業制約

- 開始時と完了時に現在・次の作業が何Phaseか明示する
- 最初にREADME、roadmap、traceability、safe-apply、packaging、validation、`git status`、直近差分、関連source/testを確認
- 編集は`apply_patch`
- venv作成、`pip install`禁止
- 実Ollama/OpenCode/systemd/SSH設定を変更しない
- sandbox/fakeを実機より先に使い、既存変更を尊重する
- PySide6 runtime Gateは既存Ubuntu VMを使う。installが本当に必要になった場合だけユーザーへ知らせる
- 実装後は必ず実行:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh
git diff --check
```

- 成功件数を報告する
- まとまりごとにcommitし`origin/main`へpushする
- 仕様または実system policyのmaterialな変更だけ質問する

まず次を確認してください。

- `README.md`
- `docs/roadmap.md`
- `docs/traceability.md`
- `docs/safe-apply.md`
- `docs/packaging.md`
- `docs/version-matrix.md`
- `docs/validation/phase5-local-restore-preview-2026-09-04.md`
- `src/llm_manager/application/restore_preview.py`
- `src/llm_manager/application/restore_preflight.py`
- `src/llm_manager/infrastructure/local_restore.py`
- `src/llm_manager/infrastructure/restore_execution.py`
- `src/llm_manager/infrastructure/local_apply_inventory.py`
- `src/llm_manager/ui/composition.py`
- restore/inventory/Qt関連test

---
