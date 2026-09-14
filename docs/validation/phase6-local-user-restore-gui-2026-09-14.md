# ff7913b local user manual restore通常GUI Gate — 2026-09-14

Debian 13の通常userがinstalled candidateの通常`qt_app.main`を操作し、Local診断から
実Applyと暗号化backupを作成後、同じGUIのBackup / Rollbackで明示Refresh、backup選択、
preview、正確な最終同意、Run Restore、restore後の明示Refreshまで完了した（1 sample）。

## 結果

| 検査 | 結果 |
| --- | --- |
| 実行主体 / composition | Debian Wayland session 2、UID 1000、installed `qt_app.main` |
| OpenCode | 1.18.25、専用PATHとisolated HOME内の製品探索先、archive hash一致 |
| 初期設定 | `compaction.auto=false`、`compaction.prune=false` |
| GUI Apply経路 | Local→Diagnose→Agent推奨2件→Review→承認→Prepare Apply→Run Apply |
| Apply | 1回、`committed`、Run Applyは完了後disabled |
| backup | 1件、complete、AES-256-GCM、Secret Service `local-master-v1` |
| GUI restore経路 | Backup / Rollback→Refresh→選択→preview→正確な同意→Run Restore |
| restore | attempt 1件、result 1件、`committed`、Run Restoreは完了後disabled |
| 復元後 | 初期config SHA-256へ一致、明示Refresh後inventoryに`restore: committed` |
| cleanup | 専用key/state/path/packageを削除、baseline/session完全一致、snapshot削除 |

開始・復元後configのSHA-256は
`fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`、
Apply後hashはjournal上
`682128216e9141bd32169fd999804f3992827cbc902aaf6d4057fd4eecdac0ea`。
GUIの最終表示は`Restore evidence: committed; error: none; persisted: true`で、
さらに明示Refresh後のinventoryが`restore: committed · restore attention: false`を示した。

## 構成と操作境界

source commitは`ff7913bb97e896f7992720b9a43c2382970a5fc8`。開始前にVM、snapshot、
candidate/archive、guest専用path、session、worktreeをread-onlyで再確認した。

| artifact | SHA-256 |
| --- | --- |
| local deb | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| remote helper deb（identity確認のみ、未使用） | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |
| OpenCode 1.18.25 archive | `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |

専用rootは`/tmp/phase6-local-user-restore-gui-20260914`、snapshotは同名。
`XDG_CONFIG_HOME`、`XDG_STATE_HOME`、`XDG_CACHE_HOME`、`HOME`を隔離した。
製品のOpenCode探索順に固定user pathがPATHより優先されることを事前起動で確認したため、
隔離HOMEの`.opencode/bin/opencode`にも同一のhash確認済みbinaryを配置した。
通常HOMEや既存OpenCode binaryは変更していない。

observer subclassは100 msごとに可視stateをJSONと画像へ保存するだけで、plan、approval、
選択、GUI stateを注入しない。操作は独立AT-SPI clientとQEMUの実keyboard/tablet入力で行った。
GUI履歴16件と16画像を保存した。Apply/restoreの各mutationはそれぞれ1回だけで、完了後の
disabled表示も確認した。保存済みoperationを再送していない。

最初の内部snapshot要求はpflash NVRAMがqcow2でないためguest変更前に安全に拒否された。
外部disk-only snapshotへ切り替えた。成功前の2回のGUI事前起動はOpenCode探索条件の確認だけで
Apply前に通常終了し、専用backup、key、journal、restore executionを作成していない。
成功経路とは別のexit記録として保持した。

## 証拠の結合検査

`binding-verification.json`でcanonical SHA-256を再計算し、次を機械照合した。

- journalのoperation/plan/host/change setとmanifestのbackup/plan/host/change set
- journal before hash、manifest item hash、restore後target hash
- manifestのcomplete、AES-256-GCM、`.enc` content reference、Secret Service key reference
- restore attempt/resultのauthorization、attempt、backup、manifest、host、target
- `apply.approved`→`backup.verified`→`apply.committed`→`restore.started`→
  `restore.committed`の5 event、連番、previous hash、event hash、correlation

setup時に専用Secret Service itemが0件、cleanup直前に正確に1件であることをassertし、削除後0件を
確認した。manifestに鍵本体はなく`local_secret_service`の`local-master-v1`参照だけを保持する。

## cleanupと回帰

追加12 packageだけをAPT simulation後に明示purgeし、専用Secret Service key、isolated
state/config/cache/home、guest deb/archiveを削除した。製品探索が作った空の通常
`/home/user/.config/opencode` directoryだけを空であることを確認して削除し、package/manual/
保全pathのbaselineとWayland sessionを完全一致させた。external snapshotはactive
blockcommit/pivot後にmetadataを削除し、Debianはrunningを維持した。

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`は
806件成功（767 pass、39 expected skip）。証拠`SHA256SUMS`と`git diff --check`も成功。

これは現`UNRELEASED` candidateのlocal user manual restore 1 sampleである。最終artifactの
再実行項目は完了にせず、release checklistは18/44件（40.9%）を維持する。local root restoreは
通常GUIとPolicyKitを使う別Gateとして分離する。
