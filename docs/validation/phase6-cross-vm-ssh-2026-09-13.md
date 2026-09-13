# ff7913b Debian GUI → Ubuntu SSH — 2026-09-13

## 対象と境界

Debian 13のUID 1000 Wayland GUIからUbuntu 26.04へ、別VM間のSSH user Applyを実行した。
source `ff7913bb97e896f7992720b9a43c2382970a5fc8` の現candidateを使用。

| package | SHA-256 |
| --- | --- |
| Debian local `llm-manager_0.1.0_all.deb` | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| Ubuntu remote helper `llm-manager-remote-helper_0.1.0_all.deb` | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |

OpenCodeは従来と同じ公式1.18.30 archiveを再取得し、既存記録のSHA-256
`60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063`
と一致。単一regular binaryを確認し、Ubuntuで一般ユーザーのversion出力を照合した。

Debianに試験専用鍵・aliasと、Ubuntu公開host keyを固定したknown_hostsを作成。
通常system SSH設定を読み、StrictHostKeyChecking=yes、UpdateHostKeys=noを維持した。
ホストの秘密鍵をVMへコピーしていない。Ubuntuへの公開鍵追加は一時snapshot内のみ。

installed製品module、production診断・Apply factory・runtime validator、実Secret Serviceと
remote root backupを使用。GUI全体は一般ユーザーで起動した。
ただし旧Gate同様、plan/approvalをGUIへ注入し、helper成功後に応答喪失例外を注入する。
このGate中にネットワークを切断してはいない。モデル推論も行わない。

## 結果

### 正常Apply：成功

- `opencode.installed` / `opencode.config.parse` はpassed。
- `committed`、エラーなし。Resultsページの可視表示と画像を確認した。
- `apply.invoke` / `apply.server_completed` / `result.read` が各1回。
  mutation再送なしで、応答喪失注入後のimmutable result照合が成功。
- 正常設定のSHA-256は
  `b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088`。

### rollback予定ケース：Apply前で停止（未検証）

Debian画面でsudo認証待ちを目視確認したが、認証待ち時間内に完了せず停止した。
製品最終表示は `approved; both SSH backup copies must verify`、Gate exit 1。
`events`と`validations`は空で、Apply/rollback呼出しはともに0回。
対象hashは正常Apply後と一致。したがってrollbackの成功証拠ではない。
同operationの再送はしていない。残存する専用SSH/sudo processは両VMとも不在。

認証画面表示の通知が遅くならないよう、次回は利用者の入力準備が整ってから
新規operationを開始する。既存の失敗operationを再利用しない。

## 証拠と復元

`cross-vm-ssh-2026-09-13.py` がホスト側の操作script、
`cross-vm-ssh-2026-09-13/gate.py` が実行したGUI harness。
同directoryに両caseのresult JSON、画像、guest-exec終了情報、APT記録、baseline/restoredを保存。
collectの最初の呼出しはrollback実行中で終了file未生成のため停止した。
mutationなしで終了後に再collectし、scriptも実行中を明示して戻るように修正した。

Debianの専用Secret Service item、試験SSH鍵・alias、暗号化試験backup・runtimeを削除。
今回APT simulationで固定した新規12 packageのみ明示purgeし、package/manual/保全pathと
Wayland sessionが開始時と一致。dpkg audit、APT check成功。
Ubuntuは一時snapshotをrunningへ復元し、package/manual/保全path完全一致を確認してから
その一時snapshotのみ削除。既存snapshotは保持し、両VMはrunning。

これはUNRELEASED candidateの部分Gate。別VM間rollback、実通信切断中のApply・照合、
通常の診断→推奨→人手review操作全体、最終release artifact Gateは未完了。
