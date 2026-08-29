# LLM-Manager Phase 4 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 4 Safe Apply Coreの実装を続行してください。

## 作業場所

- `/home/yoshimi/WorkSpace/LLM-Manager`
- GitHub: `git@github.com:NBE03xxx/LLM-Manager.git`
- branch: `main`
- 最新の実装commit: `142e5a2 Document sandbox remote copy encryption`（この引き継ぎ文書のcommitが後続する場合あり）
- `main`と`origin/main`は同期済み、作業ツリーはclean

## 確定済み要件

- 正式対象: Ubuntu 26.04、Debian 13
- Python検証基準: 3.14.4
- Ollama検証基準: 0.33.2
- OpenCode検証基準: 1.18.25
- UI言語: localeに基づく日本語・英語
- root必須systemd drop-in変更までMVP対象
- GUI全体はrootにせず、必要操作のみ昇格
- SSHはOpenSSH、`~/.ssh/config`、Agent、ProxyJump等を利用
- 秘密鍵・SSHパスワードを独自保存しない
- SSH対話認証は外部端末とControlMasterを利用
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
- Ollama service/effective environment/APIとOpenCode再読込Validator
- helper protocol v1、固定path/unit/operation allowlist
- private helper staging、declared helper execution core
- fixed LocalSystemHelperBackend
- helper CLI、PolicyKit policy、root-only replay receipt
- LocalPolicyKitInvoker
- ApprovedHelperRequestFactory、LocalPrivilegedApplyService
- ApprovalRecordのplan期限検証
- root専用Backup→Apply→Validate→Rollback Coordinator
- 既存fileの`restore_file`、新規fileの`remove_created_file`による逆順rollback
- helper/write/daemon-reload/restart/runtime validation/rollback故障注入
- backup manifest、ApprovalRecord、helper request/receipt、journalのID/hash束縛
- Coordinator→staging→CLI→receipt→executor→sandbox backendの境界統合test
- Debian packaging先行Gateとartifact ownership/mode/isolated entrypoint検証
- helper metadata互換性診断とroot Plan Gate
- Backup前およびhelper起動直前のhelper互換性再検証
- SSH切断後のread-only照合core
  - journal/manifest/host identity/fingerprintを束縛
  - remote `stat`から`UNAPPLIED`/`APPLIED`/`UNKNOWN`を判定
  - 不一致、再切断、cancel時は自動変更しない
- dual backup境界
  - local正本＋remote recovery receiptの双方をApply前に検証
  - remote片側失敗でもlocal正本を保持し、Applyを停止
  - receiptへmanifest identity、item hash、fingerprint、固定保存先、独立key scopeを束縛
- remote recovery暗号化sandbox backend
  - 独立`remote_root`鍵によるAES-256-GCM
  - canonical receipt、再読込、AAD/plaintext hash検証
  - 0700/0600、symlink/path escape拒否
  - production modeは明示拒否
- 最新の全単体テストは207件成功

## この継続作業で追加されたcommit

- `24796a1 Gate root apply on helper compatibility`
- `91f383a Document helper compatibility gate`
- `31003c8 Enforce helper readiness before root planning`
- `c9fde28 Document root planning helper gate`
- `a164b6b Revalidate helper at privileged apply`
- `09f3b26 Document privileged apply readiness checks`
- `cc432ea Reconcile interrupted remote operations safely`
- `c36e21a Document remote recovery reconciliation`
- `04ef24a Require verified remote recovery copy`
- `fa2e35f Document dual backup apply gate`
- `d86723d Encrypt remote recovery copies in sandbox`
- `142e5a2 Document sandbox remote copy encryption`

## 次の推奨作業

1. remote recovery copyを限定remote helper protocolへ接続する
2. user-only SSH stagingとroot-only remote backendの境界をsandbox/fake runnerで実装する
3. remote request/receiptへlocal manifest hash、remote receipt hash、host fingerprint、key referenceを厳格に束縛する
4. 転送途中切断、remote暗号化失敗、receipt取得失敗、再接続時改ざんを注入する
5. remote root journal取得をread-only照合coreへ接続する
6. remote retentionを30日かつホストごと直近10世代、protected除外で実装する
7. local/remote片側削除失敗時の再照合と表示用状態を定義する
8. `docs/roadmap.md`、`docs/traceability.md`、必要に応じて`docs/safe-apply.md`を同期する

実SSH転送やremote helper protocolへの接続が一度に大きすぎる場合は、まずsandbox remote retention、remote receipt永続化のhardening、またはtransport Portとcanonical request schemaを独立した小さなcommitとして進めてください。仕様をmaterially変更しない範囲では質問せず、安全側の仮定で進めてください。

## 現在の重要な未完了Gate

- Secret Service実desktop Gate
- SSH transportと実remote helperへの接続
- remote root-owned backend、remote key生成・配置
- remote retentionとlocal/remote削除整合性
- remote root journal取得と実SSH切断integration
- PolicyKit実desktop認証
- debの実install/upgrade/remove/purge
- Debian 13実機差異確認
- 実PolicyKit/systemd操作を行うdisposable OS Gate
- GUI Phase 5

## 注意点

- 現在の`SandboxRemoteRecoveryStore`は一時root専用で、production modeを拒否する
- `DualCopyPrivilegedBackupStore`はlocal正本を保持し、remote receipt検証失敗をApply Gate failureにする
- remote copyのlogical保存先は`/var/lib/llm-manager/backups`配下へ固定されるが、実パスにはまだ書き込まない
- `RemoteJournalReconciler`はread-only判定だけを行い、自動再Apply/rollbackしない
- HelperReceiptStoreの`executing` receiptはクラッシュ後の照合対象であり、自動再実行しない
- 実debへのroot-owned配置とPolicyKit実desktop Gateは未実施
- 実機のOllama、OpenCode、systemd、SSH設定を変更しない

## 制約

- 最初にREADME、docs、`git status`、直近差分、関連ソースとテストを確認する
- ファイル編集は`apply_patch`を使う
- 仮想環境作成、`pip install`は行わない
- 実Ollama、OpenCode、systemd、SSH先を変更しない
- テストはsandbox/fakeだけで行う
- 既存変更を尊重する
- 実装後は必ず次を実行する:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
git diff --check
```

- 成功件数を報告する
- まとまりごとにcommitし、`origin/main`へpushする
- 仕様をmaterially変更する判断だけユーザーへ質問する

まず`README.md`、`docs/roadmap.md`、`docs/traceability.md`、`docs/safe-apply.md`、`src/llm_manager/infrastructure/remote_backup.py`、`src/llm_manager/infrastructure/journal.py`、関連テストを確認してから作業を開始してください。

---
