# LLM-Manager Phase 4 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 4 Safe Apply Coreを続行してください。

## 作業場所

- `/home/yoshimi/WorkSpace/LLM-Manager`
- GitHub: `git@github.com:NBE03xxx/LLM-Manager.git`
- branch: `main`
- 最新の実装commit: `363a5b4 Validate remote journal reconciliation`（この引き継ぎ文書のcommitが後続する）
- `main`と`origin/main`は同期済み、作業ツリーはclean

## 確定済み要件

- 正式対象: Ubuntu 26.04、Debian 13
- Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25を検証基準とする
- UIはlocaleに基づく日本語・英語
- root必須systemd drop-in変更までMVP対象。GUI全体はrootにしない
- SSHはsystem OpenSSH、`~/.ssh/config`、Agent、ProxyJump等を利用
- 秘密鍵・passwordを独自保存しない。対話認証は外部端末とControlMasterを利用
- backupはlocal正本＋SSH先復元用copy
- 保持は30日かつhostごと直近10世代、manual protectionは削除しない
- 一般配布は暗号化既定ON、開発モード既定OFF

## 実機情報と禁止事項

- `development`: 192.168.1.201、Ubuntu 26.04、OpenCode 1.18.18、Ollamaなし
- AI server: `yoshimi@192.168.1.253`、Ubuntu 26.04、Ollama 0.33.2 active、OpenCodeなし
- disposable VM `llm-manager-gate`: Ubuntu 26.04、user `user`、remote helper 0.1.0~dev0導入済み
- Gate専用sudoers、root journal evidence、user `/tmp` artifactはcleanup済み。通常の`sudo -n`は拒否状態
- Ollama、OpenCode、systemd、SSH設定を無断変更しない
- passwordをチャットで尋ねず、argv/stdin/logへ渡さない。sudo認証は外部端末だけで行う
- main workstationへdebやdependencyを無断installしない
- disposable OSでもmaterialなPolicyKit/sudoers/systemd変更は先に承認を得る

## 完了済み

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

## 完了済み実機Gate

- Secret Service desktop negative Gate
  - GNOME/Wayland/session bus/keyring daemonあり
  - source checkoutのsystem Pythonに`secretstorage`なし
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
  - production compatibility Gateと`OpenSshRemoteJournalPort`
  - canonical evidence 928 bytesのbinding検証
  - remote targetを`unapplied`と照合、Apply/rollbackなし
  - Gate artifact全cleanup、cleanup後`remote_journal_failed`と`sudo -n`拒否
- 実Gateで発見したevidence `status` binding漏れを修正。不一致はtarget観測前にfail closed
- 最新の全単体テストは338件成功

## `c17644a`以降のcommit

- `939f113 Update Phase 4 execution handoff`
- `a6abb51 Persist evidence retention executor outcomes`
- `01d519f Reload retention executions strictly`
- `36d39e8 Gate retention cleanup with explicit requests`
- `f4e47cf Persist retention cleanup requests`
- `2d307e0 Execute explicit retention cleanup safely`
- `ae1b352 Display retention execution evidence safely`
- `da0a2e8 Compose retention evidence user state`
- `3393056 Record Secret Service desktop availability gate`
- `e874891 Record PolicyKit desktop availability gate`
- `c6ec6b2 Validate remote helper absence safely`
- `33ce298 Validate positive remote recovery transport`
- `b4a5283 Persist remote recovery request identity`
- `1b7684f Record restart receipt recovery gate`
- `42a31f9 Authorize remote retention interactively`
- `a469803 Persist verified remote recovery receipts`
- `6f20287 Validate remote deletion transport`
- `69fc4a9 Validate remote helper deb lifecycle`
- `4f2b012 Validate live SSH transfer disconnect`
- `363a5b4 Validate remote journal reconciliation`

## 次の推奨作業（Phase 4）

残る大きなGateはdesktop positiveとDebian 13/local package lifecycleである。

1. local `llm-manager` debのbuild/artifactとinstall/upgrade/remove/purge手順をread-only確認
2. main workstationを変更せず実行できるdisposable desktop OSの有無を確認
3. 利用可能ならlocal deb lifecycleを実施
4. deb導入後のSecret Service positive Gate
   - `python3-secretstorage`、default collectionへのGate専用key create/reload/delete
   - 暗号化のsilent fallbackなし
5. PolicyKit positive Gate
   - action/helper owner/mode/package検証
   - active desktop sessionで認証成功・dismiss/deny
   - systemd操作はGate専用unit/pathのみ。Ollama/OpenCodeには触れない
6. Debian 13でremote/local package、OpenSSH、PolicyKit、Secret Service差異を確認

disposable desktop OSがなければmain workstationへのinstallを仮定せず、必要条件と構築手順を提示して止める。

## 重要な未完了Gate

- Secret Service実desktop positive
- PolicyKit実desktop positive認証、dismiss、deny
- local `llm-manager` deb install/upgrade/remove/purge
- Debian 13実機差異
- Gate専用path/unitを使う実PolicyKit/systemd操作
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

## 制約

- 開始時と完了時に現在・次の作業が何Phaseか明示する
- 最初にREADME、roadmap、traceability、safe-apply、validation、`git status`、直近差分、関連source/testを確認
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
- `docs/validation/secret-service-desktop-2026-08-30.md`
- `docs/validation/policykit-desktop-2026-08-30.md`
- `docs/validation/remote-helper-deb-lifecycle-2026-08-30.md`
- `packaging/`
- Secret Service、PolicyKit、local packagingの関連source/test

---
