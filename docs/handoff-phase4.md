# LLM-Manager Phase 4 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 4 Safe Apply Coreのclosure auditを続行してください。

## 作業場所

- `/home/yoshimi/WorkSpace/LLM-Manager`
- GitHub: `git@github.com:NBE03xxx/LLM-Manager.git`
- branch: `main`
- 最新の実装・evidence commit: `a1962d3 Complete Debian PolicyKit dismiss gate`（この引き継ぎ文書のcommitが後続する）
- `main`と`origin/main`は同期済み、作業ツリーはclean

## 確定済み要件

- 正式対象: Ubuntu 26.04、Debian 13
- Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25を初期検証baselineとする
- Debian 13 stockを正式対象へ含めるsupported minimum:
  - Python 3.13
  - cryptography 43.0.0
  - SecretStorage 3.3.3
- UIはlocaleに基づく日本語・英語
- root必須systemd drop-in変更までMVP対象。GUI全体はrootにしない
- SSHはsystem OpenSSH、`~/.ssh/config`、Agent、ProxyJump等を利用
- 秘密鍵・passwordを独自保存しない。対話認証は外部端末とControlMasterを利用
- backupはlocal正本＋SSH先復元用copy
- 保持は30日かつhostごと直近10世代、manual protectionは削除しない
- 一般配布は暗号化既定ON、開発モード既定OFF

## 実機・VM情報

- `development`: 192.168.1.201、Ubuntu 26.04、OpenCode 1.18.18、Ollamaなし
- AI server: `yoshimi@192.168.1.253`、Ubuntu 26.04、Ollama 0.33.2 active、OpenCodeなし
- disposable VM `llm-manager-gate`: Ubuntu 26.04、user `user`、remote helper 0.1.0~dev0導入済み
  - Gate専用sudoers、root journal evidence、user `/tmp` artifactはcleanup済み
  - 通常の`sudo -n`は拒否状態
- desktop VM `ubuntu26.04`: T16上のUbuntu 26.04。local deb/Secret Service/PolicyKit positive Gateに使用
  - snapshot `phase4-pre-local-deb-20260831`を保持
- desktop VM `debian13`: Debian 13.6を32 GiB qcow2へ通常install済み
  - VM user `user`、password-backed GNOME session、自動loginなし
  - ISOはeject済み、disk boot、autostart disabled
  - 2026-09-01時点では稼働中
  - passwordはチャット・repository・artifactへ保存していない
  - Gate専用helper/action/unit/deny rule/`/run` artifactはcleanup済み

## 禁止事項

- Ollama、OpenCode、既存systemd unit、SSH設定を無断変更しない
- passwordをチャットで尋ねず、argv/stdin/logへ渡さない。sudo/PolicyKit認証は外部terminal/GUIだけで行う
- main workstationへdebやdependencyを無断installしない
- disposable OSでもmaterialなPolicyKit/sudoers/systemd変更は先に承認を得る
- venv作成、`pip install`禁止

## Phase 0〜3とPhase 4 coreの完了済み実装

- Phase 0〜3
- LocalBackupStore、AES-GCM、Secret Service provider abstraction
- AtomicFileExecutor、FileValidator、SafeApplyCoordinator
- rollback、`RECOVERY_REQUIRED`、operation journal、hash-chain audit
- Ollama/OpenCode runtime Validator
- local helper protocol、PolicyKit境界、root専用Backup→Apply→Validate→Rollback
- local/remote helper分離deb、helper compatibility Gate
- local正本＋remote encrypted recovery copyのdual backup Apply Gate
- remote request/receipt canonical schemaとidentity/hash/fingerprint/key binding
- user-only SSH staging、request-last publication、固定helper identity
- remote root AES-GCM backend、root key provider、production entrypoint
- remote retention、canonical deletion、dual-copy deletion coordination
- deletion/manifest/reconciliation evidenceのimmutable永続化と改ざん検証
- backup evidence retention planner/executor/execution store
  - 実行直前candidate再検証、参照逆順削除、各削除後directory fsync
  - 全終了経路のexecution保存、保存失敗時も生成済みexecutionを公開
  - restart後host/fingerprint単位strict一覧、未知entry・改ざん・重複拒否
- `PARTIAL`/`FAILED`再開はimmutableな明示cleanup requestだけ
- inventory表示はread-onlyで、自動orphan再判定・自動削除を行わない
- remote request/receiptのlocal immutable保存とrestart回収
- privileged local/remote wrapperはimport前にbytecode生成を無効化し、dpkg管理外root `__pycache__`を作らない

## 完了済み実機Gate

- Secret Service desktop negative Gate
  - source checkoutのsystem Pythonにbindingなし
  - stable `secret_service_unavailable`、secret mutationなし
- PolicyKit desktop negative Gate
  - authority到達可能、action/helper未install、mutationなし
- remote helper未導入hostのnegative compatibility Gate
- `llm-manager-gate` positive recovery transport
  - compatibility、user staging、外部端末sudo、root key/AES-GCM copy、receipt、cleanup
- 別processでhelperを再実行しないrestart receipt recovery
- 実remote retention（3件残存、削除0）
- 実remote deletion（専用copyのみ削除、local正本保持、既存3件不変）
- remote helper deb reinstall/remove/purge/reinstall
  - package不在時`missing`、dpkg管理外root backup/key保持
- 実SSH転送切断
  - 16 MiB転送中に専用ControlMaster終了
  - `remote_staging_failed`、request/result未公開、root helper 0回
  - local正本検証成功、user staging cleanup
- 実remote root journal evidence取得とread-only reconciliation
  - canonical evidenceのidentity/hash/status binding検証
  - remote targetを`unapplied`と照合、Apply/rollbackなし
  - Gate artifact全cleanup、cleanup後`remote_journal_failed`と`sudo -n`拒否
- Ubuntu 26.04 local deb desktop positive Gate
  - install/reinstall/remove/purge相当/reinstall/upgrade
  - `policykit-1`ではなく`polkitd`+`pkexec`へdependency修正
  - Secret Service default collectionへGate専用key create/reload/delete
  - PolicyKit success、dismiss exit 126、explicit deny exit 127
  - Gate専用path/unitだけを使うsystemd操作と完全cleanup
- Debian 13 desktop/package Gate
  - stock Python 3.13.5、cryptography 43.0.0、SecretStorage 3.3.3
  - stock runtimeで全338単体テスト成功
  - AES-GCM、Secret Service create/reload/delete、PolicyKit action確認
  - local/remote Gate deb installとremote helper remove/purge/reinstall
  - remote helper未知command fail closed、bytecode非生成、remove後private runtime完全消去
  - 正式local/remote artifactをbuild/verifyし、APT simulationはいずれもexit 0
  - Live desktopでPolicyKit success、explicit deny、Gate専用systemd操作、cleanup
  - 通常installしたpassword-backed GNOME sessionで認証dialogをCancel
    - `Request dismissed`、exit 126
    - Gate unit inactive、markerなし
    - helper/action/unit/`/run` artifact完全cleanup

## 最新commit

- `5074cdb Update Phase 4 handoff after SSH gates`
- `5c25852 Validate local deb desktop gates`
- `ca6a346 Validate Debian 13 packaging compatibility`
- `cfb1ab2 Record Debian PolicyKit systemd gate`
- `a1962d3 Complete Debian PolicyKit dismiss gate`

それ以前のPhase 4 commit一覧は`git log`と旧引き継ぎ履歴を参照する。

## 主要validation evidence

- `docs/validation/local-deb-desktop-positive-2026-08-31.md`
- `docs/validation/debian13-desktop-packaging-2026-08-31.md`
- `docs/validation/debian13-policykit-systemd-2026-08-31.md`
- `docs/validation/remote-helper-deb-lifecycle-2026-08-30.md`
- `docs/validation/remote-journal-reconciliation-2026-08-30.md`
- `docs/validation/ssh-transfer-disconnect-2026-08-30.md`

## 次の推奨作業

まずPhase 4 closure auditを行う。

1. `README.md`、roadmap、traceability、safe-apply、packaging、全validation evidenceとPhase 4 test/sourceを照合
2. roadmap/traceability内の古い「Debian 13差異待ち」「desktop positive待ち」「実PolicyKit未実施」記述を分類
   - 完了済みなら更新
   - 実Ollama/OpenCode targetへのApplyを意図する項目は、禁止境界のため未実施であることを明記し、Gate専用unit成功と混同しない
3. Phase 4 Exit条件と重要な未完了Gateを再判定
4. safe boundaryを拡張せず完了できる文書・test整合性修正を行う
5. 全必須検査を実行し、closure auditをcommit/push
6. Phase 4 Exitを満たすなら、次をPhase 5 PySide6 GUI開始として明示する

## 現時点で意図的に未実施または次Phase

- 実Ollama/OpenCode設定へのApply/rollback（無断変更禁止。Gate専用unitで特権/systemd境界だけ検証済み）
- Debian 13 installed desktopへの正式deb実install lifecycle
  - Gate-only control packageでruntime/lifecycle実施、正式artifactはbuild/verify/APT simulationまで完了
  - closure auditで追加実installがPhase 4 Exitに必要か、安全境界とevidenceから判断する
- GUI Phase 5

## 安全境界

- evidence削除は実行直前再検証＋参照逆順。`PARTIAL`/`FAILED`後は自動再削除しない
- journal/backup reconciliationはread-onlyで、自動Apply/rollbackしない
- `executing` receiptを自動再実行しない
- local正本はremote失敗時も保持する
- staging cleanup以外のmutation retryは明示requestなしに行わない
- remote journal取得は固定`read-journal-evidence <operation-id> <request-hash>`だけ
- remote evidenceはstatusを含めlocal journalへbindingする
- passwordless read権限がない場合、sudo timestamp共有へ依存しない

## 作業制約

- 開始時と完了時に現在・次の作業が何Phaseか明示する
- 最初にREADME、roadmap、traceability、safe-apply、packaging、validation、`git status`、直近差分、関連source/testを確認
- 編集は`apply_patch`
- venv作成、`pip install`禁止
- 実Ollama/OpenCode/systemd/SSH設定を変更しない
- sandbox/fakeを実機より先に使い、既存変更を尊重する
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
- `docs/validation/local-deb-desktop-positive-2026-08-31.md`
- `docs/validation/debian13-desktop-packaging-2026-08-31.md`
- `docs/validation/debian13-policykit-systemd-2026-08-31.md`
- `packaging/`
- Secret Service、PolicyKit、local/remote packagingの関連source/test

---
