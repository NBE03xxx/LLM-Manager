# LLM-Manager Phase 4 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 4 Safe Apply Coreの実装を続行してください。

## 作業場所

- `/home/yoshimi/WorkSpace/LLM-Manager`
- GitHub: `git@github.com:NBE03xxx/LLM-Manager.git`
- branch: `main`
- 最新の実装commit: `c17644a Persist backup evidence retention executions`（この文書のcommitが後続する場合あり）
- `main`と`origin/main`は同期済み、作業ツリーはclean

## 確定済み要件

- 正式対象: Ubuntu 26.04、Debian 13
- Python検証基準: 3.14.4
- Ollama検証基準: 0.33.2
- OpenCode検証基準: 1.18.25
- UI言語: localeに基づく日本語・英語
- root必須systemd drop-in変更までMVP対象。GUI全体はrootにせず必要操作のみ昇格
- SSHはOpenSSH、`~/.ssh/config`、Agent、ProxyJump等を利用
- 秘密鍵・SSHパスワードを独自保存しない。対話認証は外部端末とControlMasterを利用
- バックアップはローカル正本＋SSH先復元用コピー
- 保持は30日かつホストごと直近10世代、手動保護は削除しない
- 一般配布は暗号化既定ON、開発モードは既定OFF

## 実機情報

- SSH alias `development`: 192.168.1.201、Ubuntu 26.04、OpenCode 1.18.18、Ollamaなし
- AI server: `yoshimi@192.168.1.253`、Ubuntu 26.04、Ollama 0.33.2 active、OpenCodeなし
- 実機のOllama/OpenCode/systemd/SSH設定を無断で変更しない
- パスワードをチャットで尋ねない

## 完了済み

- Phase 0〜3
- LocalBackupStore、AES-GCM、Secret Service provider abstraction
- AtomicFileExecutor、FileValidator、SafeApplyCoordinator
- rollback、`RECOVERY_REQUIRED`、operation journal、hash-chain audit
- Ollama/OpenCode Validator、local helper protocol、PolicyKit境界
- root専用Backup→Apply→Validate→Rollbackとhelper compatibility Gate
- SSH切断後のread-only照合core
- local正本＋remote recovery copyのdual backup Apply Gate
- remote request/receiptのcanonical schemaとidentity/hash/fingerprint/key reference束縛
- user-only SSH staging、system OpenSSH runner、private staging、固定helper identity
- 転送切断、暗号化失敗、receipt取得失敗、改ざんのsandbox/fake故障注入
- remote root-owned暗号化backend、専用key provider、production entrypoint
- remote helper専用Debian package境界とcompatibility Gate
- remote root journalのread-only取得とreconciliation接続
- remote retention（30日＋ホストごと直近10世代、protected除外）
- remote helper経由のcanonical一覧・削除request/receipt
- dual-copy deletion coordination、片側失敗の保持・再照合・表示状態
- 中断後のread-only recovery evidence。自動再削除はstaging cleanupだけに限定
- deletion result、manifest/recovery evidence、reconciliation resultの永続化と改ざん検証
- orphan判定はread-onlyで、自動変更しない
- backup evidence retention planner/executor
  - 実行直前に候補を再検証
  - reconciliation→manifest evidence→deletion resultの参照逆順削除
  - 各削除後にdirectory fsync
  - 途中故障・cancelは`PARTIAL`/`FAILED`として停止し、自動再試行しない
- backup evidence retention execution store
  - request、backup、host/fingerprint、deletion/reconciliation hash、完了時刻、状態を自己hashで束縛
  - canonical JSON、immutable、0700/0600、owner/mode、symlink、size、filename identityを再読込時に検証
  - 改ざん、unsafe metadata、filename不一致、重複保存を拒否
- 最新の全単体テストは306件成功

## `142e5a2`以降の実装commit

- `0ec0491 Add remote recovery helper transport boundary`
- `8050f1b Add user-only SSH recovery staging`
- `8cb6467 Add sandbox remote backup retention`
- `6033524 Reconcile dual-copy deletion outcomes`
- `c88a74b Verify remote root journal before reconciliation`
- `ae7df68 Add system OpenSSH staging runner`
- `96f0fe0 Add remote sudo helper invocation`
- `29c4aec Execute remote recovery requests safely`
- `760119b Add remote recovery helper CLI core`
- `fa999a0 Add remote root backup key provider`
- `e68de83 Enable fixed remote root backup backend`
- `eb8979e Add remote helper production entrypoint`
- `f81ed6d Package remote recovery helper separately`
- `7d46cf9 Gate remote staging on helper compatibility`
- `51898ad Fetch remote root journal evidence safely`
- `d4917a4 Expose remote retention through helper`
- `c69518f Coordinate dual backup deletion safely`
- `e4ac007 Connect remote backup deletion helper`
- `12f7dc8 Recover interrupted backup deletion safely`
- `23ff276 Aggregate backup retention status safely`
- `6dd7bc6 Persist retention recovery evidence`
- `7f580cb Reload persistent backup evidence safely`
- `288d308 Limit backup retries to staging cleanup`
- `2e46a29 Persist read-only backup reconciliation`
- `7a272f0 Dispatch read-only backup reconciliation`
- `a72d35d Preserve manifest evidence before deletion`
- `1a4cfbf Plan backup evidence retention safely`
- `3cc6aac Execute backup evidence retention safely`
- `c17644a Persist backup evidence retention executions`

## 次の推奨作業（Phase 4 Safe Apply Core）

1. `BackupEvidenceRetentionExecutor`から`BackupEvidenceRetentionExecutionStore`への保存を接続する
2. `COMPLETED`/`PARTIAL`/`FAILED`の全終了経路で、返却前にexecution evidenceを永続化する
3. execution保存失敗時は削除済み状態を隠さず、stable errorとread-only再照合可能な境界を定義する
4. 再起動後にexecutionをhost/fingerprint単位でstrict列挙し、改ざんや未知entryを拒否する
5. 保存失敗、途中削除後の保存失敗、cancel、既存execution衝突をsandboxで故障注入する
6. `PARTIAL`/`FAILED`からの再開は明示的cleanup requestだけに限定し、orphanの自動再判定・自動削除を禁止する
7. local/remote証跡の片側欠落を表示用状態へ反映し、README、roadmap、traceability、safe-applyを同期する

まず小さなcommitとして「executor→execution store保存接続＋保存失敗の故障注入」を実装し、その後に再起動後のstrict一覧・明示的cleanup再開境界へ進めてください。仕様をmaterially変更しない範囲では質問せず、安全側の仮定で進めてください。

## 現在の重要な未完了Gate

- backup evidence retention executorからexecution storeへの保存接続
- executionの再起動後strict一覧と明示的cleanup再開境界
- Secret Service実desktop Gate
- 実SSH transportとremote helperの実機integration Gate
- remote root-owned backend、remote key生成・配置、retentionの実機Gate
- remote root journal取得と実SSH切断integration
- PolicyKit実desktop認証
- debの実install/upgrade/remove/purge
- Debian 13実機差異確認
- 実PolicyKit/systemd操作を行うdisposable OS Gate
- GUI Phase 5

## 注意点

- `BackupEvidenceRetentionExecutionStore`は実装済みだが、executorからの保存接続とproduction配置は未実装
- execution storeは内容を永続化できるが、現時点のexecutorはexecutionを返すだけで自動保存しない
- evidence削除は候補を実行直前に再検証し、参照逆順で行う
- `PARTIAL`/`FAILED`後に自動再削除しない
- journal/backup reconciliationはread-onlyで、自動再Apply/rollbackしない
- HelperReceiptStoreの`executing` receiptは自動再実行しない
- local正本はremote側失敗時も保持する
- 実機のOllama、OpenCode、systemd、SSH設定を変更しない

## 制約

- 作業開始時と完了報告時に、現在および次の作業がPhaseの何であるかを明示する
- 最初にREADME、docs、`git status`、直近差分、関連ソースとテストを確認する
- ファイル編集は`apply_patch`を使う
- 仮想環境作成、`pip install`は行わない
- 実Ollama、OpenCode、systemd、SSH先を変更しない
- テストはsandbox/fakeだけで行い、既存変更を尊重する
- 実装後は必ず次を実行する:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh
git diff --check
```

- 成功件数を報告する
- まとまりごとにcommitし、`origin/main`へpushする
- 仕様をmaterially変更する判断だけユーザーへ質問する

まず`README.md`、`docs/roadmap.md`、`docs/traceability.md`、`docs/safe-apply.md`、`src/llm_manager/infrastructure/backup_evidence_retention.py`、`src/llm_manager/infrastructure/backup_deletion.py`、`src/llm_manager/infrastructure/backup_manifest_evidence.py`、`src/llm_manager/infrastructure/backup_reconciliation.py`、`tests/test_backup_evidence_retention.py`を確認してから作業を開始してください。

---
