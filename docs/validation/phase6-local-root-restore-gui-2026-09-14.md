# ff7913b local root manual restore通常GUI＋PolicyKit Gate — 2026-09-14

Debian 13の通常userがinstalled candidateの通常`qt_app.main`を使い、Backup / Rollbackから
root-owned encrypted backupを選択し、inventory、review、review保存、最終同意、restoreを
それぞれ専用PolicyKit境界で操作した（1 sample）。restoreは1回だけ実行され、固定Ollama
drop-inは開始内容へ戻り、systemd restartとloopback API validation後に`committed`となった。

## 結果

| 検査 | 結果 |
| --- | --- |
| 実行主体 / composition | Debian Wayland session 2、UID 1000、installed `qt_app.main` |
| backup | `root-gui-backup-20260914`、root-owned AES-256-GCM origin |
| GUI経路 | Backup / Rollback→System backup inventory→選択→review→review保存→final consent→restore |
| PolicyKit | active desktopの実promptでinventory/review/save/executeを管理者認証 |
| restore | review/attempt/result各1件、result `committed`、再実行button disabled |
| 復元後 | target開始SHA-256へ一致、root/root 0644、Ollama fixture service active、API正常 |
| audit | `root_restore.started`→`root_restore.finished(committed)`の2-event strict chain |
| cleanup | 専用root key/state/unit/target/pathと追加12 packageを削除、baseline/session完全一致、snapshot削除 |

targetは`/etc/systemd/system/ollama.service.d/90-llm-manager.conf`。変更後hashは
`a75e365026814256f2df824962f3f82599677c2af36a267dbb7913b657f1cc89`、復元した開始hashは
`391a06e89a7a33b0402ca88d85541d8d12dad8a22c24ed238a4246a5b183bde1`。
成功requestは`review-24b5d8f3e5f242ad93a6df791df09950`、request SHA-256は
`4c9b66d647a269f8728725585ee01c33303d2cc66471869d99d02c42465ef154`。

## 構成と境界

source commitは`ff7913bb97e896f7992720b9a43c2382970a5fc8`。開始前にVM、snapshot、
candidate/archive、installed package、専用path、固定target/unit、root restore state、session、
worktreeをread-onlyで再確認した。

| artifact | SHA-256 |
| --- | --- |
| local deb | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| remote helper deb（identity確認のみ、未使用） | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |
| OpenCode 1.18.25 archive（identity確認のみ、root Gateでは未使用） | `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |

専用guest pathとexternal disk-only snapshotは
`phase6-local-root-restore-gui-20260914`。`XDG_CONFIG_HOME`、`XDG_STATE_HOME`、
`XDG_CACHE_HOME`、`HOME`を隔離した。pflashのためinternal snapshotは使わず、guest変更前に
external snapshotを作成した。

local root Applyはactionable Ollama rule待ちでrelease scope外のため、このGateではroot backupを
前提fixtureとしてproduction capture APIから1回だけ作成した。capture requestは固定target、
before/after hash、`source_apply_request_hash`、`source_manifest_hash`へbindingした。capture後の
記録保存だけが一度中断した際はcaptureを再実行せず、既存ciphertextのproduction復号、変更後
target、execution/audit空を検証してfixture記録だけを再開した。inventory以降はinstalled production
GUIと専用PolicyKit helperをそのまま使用し、fixtureやobserverからrequest、review、approval、
GUI stateを注入していない。

observer subclassは可視widgetのstateと画面を保存するだけである。最初のQGA `runuser`起動は
logind manager sessionに入り、PolicyKit inactive policyがpromptなしで拒否した。restore stateが
空であることを確認して通常終了し、active desktopのGNOME Terminal scopeから同じinstalled
`qt_app.main`を再起動した。以降は実PolicyKit promptが表示された。

## unconfirmed reviewとno-retry

最初のactive-session review保存は認証期限を越え、GUIが「保存済みか推測せず同じ要求を再送しない」
状態へ移行した。保存済み履歴照会も期限切れで確認不能となったため、同一save要求を再送しなかった。
root-owned stateを直接read-only検査し、backup/key以外、review/attempt/result/auditが0件であることを
確認した後、ダイアログを閉じて新しいinventory/reviewを作成した。

新しいreviewは期限内に保存され、`executions/`には正確に1 reviewだけが現れた。そのreviewから
final consentを開き、target、current/backup metadata、expiry、request hashを画面確認した。
明示checkbox後のexecute要求は1回だけ送信した。完了後、GUIは
`The saved result reports that restore and validation completed.`を表示し、executeとstatus再照合buttonは
無効だった。最終root stateもreview/attempt/result各1件であり、restoreの二重実行はない。

## 証拠の結合検査

installed production reader/store/audit adapterを使い、次を機械照合した。

- root backup record/ciphertext/key referenceとproduction AES-GCM復号後の開始hash
- fixtureのsource Apply request/manifest hash、origin record hash、review evidence
- approved requestのbackup/target/current/restore state、caller UID、host、manifest、request hash
- immutable review→attempt→resultのrequest/review/attempt hashと`committed` terminal state
- strict auditの連番、previous/event hash、correlation ID、request hash、terminal state
- targetのcontent/hash/root ownership/0644、systemd active/running、effective environment
- `/api/version`の`0.33.2`と`/api/tags`の空model inventory

暗号化payload SHA-256は
`3f3b7206f0012b78eb5047a4037ee97fd2d498f331236aa39dc68d3b2400d085`、origin record hashは
`3c020ba559ff02db11d357e670d973c94677be42ff1c94042e15eb6811e36827`。鍵本体は証拠へ保存せず、
専用root key fileの存在・mode境界とcleanup前hash inventoryだけを記録した。

## cleanupと回帰

GUI終了後に証拠を回収し、専用fixture serviceを停止、unit/drop-in、root backup/key/execution/audit、
isolated guest pathとdebを削除した。APT simulationで追加12 packageだけを固定して明示purgeした。
setupが作った空の`/var/lib/llm-manager`をroot/root 0700・空と確認して`rmdir`した後、package/manual/
保全pathとWayland sessionがbaselineへ完全一致した。

external snapshotはactive blockcommit/pivot後にmetadataを削除。Debian/Ubuntuはrunning、Debian base
diskへ復帰し、Ubuntuの既存`phase4-pre-local-deb-20260831` snapshotを保持した。

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`は
806件成功（767 pass、39 expected skip）。証拠`SHA256SUMS`と`git diff --check`も成功。

これは現`UNRELEASED` candidateのlocal root manual restore 1 sampleであり、公開用final artifactの
再検証ではない。release checklistは18/44件（40.9%）を維持する。version 0.1.0 / UNRELEASEDを
維持し、署名鍵生成、tag、release公開は行っていない。
