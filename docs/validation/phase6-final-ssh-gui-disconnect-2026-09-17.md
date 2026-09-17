# Phase 6 final artifact SSH user GUI disconnect Gate（2026-09-17）

## 判定

**成功。** Final local debを導入したDebian 13通常userの通常GUIから、final remote helperを導入した
Ubuntu 26.04のSSH userへ、正常commitとproduction validatorによる自然rollbackを独立したoperationで実行した。
両caseともhelperの成功markerを観測した後にUbuntuのlive NICを実際にdown/upし、実SSH processがexit 255に
なった後、復旧した接続でimmutable resultを読み直した。正常系は`committed`、自然障害系は`rolled_back`で、
mutationの再送はなかった。

これによりrelease checklistの「最終artifactでSSH user Apply/rollbackと切断後immutable result照合」と、
それを最後の未完条件としていたperformance／長時間Agent／accessibility／完成GUI経路のSSH切断親項目を完了とする。

## Artifact identity

- source commit: `5b7d4de03e495fe630deab952de043f945a22bd7`
- local deb SHA-256: `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1`
- remote helper deb SHA-256: `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4`
- source archive SHA-256: `6d569199110bdc155a14c0a6222353ccc92380b63b20cfebff083ace1c91fe18`
- 保存元: `/tmp/llm-manager-final-5b7d4de-20260916/artifacts/`
- 状態: 未署名・未tag・未公開

## 正常commit case

採用証拠は`final-ssh-gui-commit-disconnect-2026-09-17-attempt2/`。

- Debian通常userのinstalled final GUIを通常`qt_app.main`経路で起動し、SSH診断、Agent推奨2件、
  review、明示承認、Run Applyを通常画面操作した。plan／approval注入なし。
- `user-apply` helperは1回だけ実行されexit 0。`opencode.installed=installed`と
  `opencode.config.parse=valid`はともにpassed。
- helper成功応答を試験relayで保留し、Ubuntu live NICを`up -> down -> up`へ変更した。
  down時間は4.021082秒、watchdog exit 0。
- 実`ssh.user_apply.invoke`はexit 255、timeout flag false。link復旧後のimmutable result照合は
  `committed`で、GUIも`Apply result: committed.`を表示した。
- transport relayと短いkeepaliveは応答中に実NIC断を成立させる観測条件だけに使用した。
  plan、approval、validation、result、mutation outcomeは注入していない。

## 自然障害rollback case

採用証拠は`final-ssh-gui-rollback-disconnect-2026-09-17/`。

- 正常系とは別namespace、別snapshot、別operationで、同じ通常GUI経路を操作した。
- Apply直後だけ実`/usr/local/bin/opencode`を一時退避した。production validator自身が
  `opencode.installed=not_installed`と`opencode.config.parse=not_found`を検出し、
  `runtime validation failed`から自動rollbackへ進んだ。validation結果注入なし。
- `ssh.user_apply.invoke`は1回、exit 0。`user-rollback` helperは1回だけ実行されexit 0、
  configを開始hash `fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`へ復元した。
- rollback成功応答を試験relayで保留中にlive NICを`up -> down -> up`へ変更した。
  down時間は4.020347秒、watchdog exit 0。
- 実`ssh.user_rollback.invoke`はexit 255、timeout flag false。link復旧後のimmutable result照合は
  `rolled_back`で、GUIも`Apply result: rolled_back; runtime validation failed`を表示した。
- runtime watcherはexit 0。OpenCode 1.18.25 binaryの開始hash、mode 0755、config開始hashを復元し、
  一時退避fileが残っていないことを確認した。

## 認証時間とGate境界

通常製品値120秒の先行試行では、外部ターミナルでの人のsudo認証とremote backup検証完了が
要求作成から約143秒となり、Apply invoke前に製品deadlineへ達した。このoperationは再送せず、target開始hash不変、
Apply invoke 0を確認して清掃した。採用2 caseは、製品が対応する上限内でvalidation harnessの
`OpenSshRemoteSudoInvoker`待機だけを600秒へ延長した。証拠JSONでは
`remote_sudo_timeout_seconds=600`、`remote_sudo_timeout_injected=true`として明示している。
これは人の認証turnを待つGate allowanceであり、製品のplan／approval／validation／resultを置換していない。

## 非採用試行

- `final-ssh-gui-commit-disconnect-2026-09-16/`: GUI Applyは`committed`まで完了したが、foreground watcherが
  helper marker観測まで存続せずNICを切断できなかった。完了operationは再送せず非採用とした。
- `final-ssh-gui-commit-disconnect-2026-09-16-attempt2/`: 認証deadlineまでにApplyへ到達せず、Apply invoke 0、
  target不変を確認して清掃した。
- `final-ssh-gui-commit-disconnect-2026-09-17/`: remote backup検証は完了したが通常120秒deadline後で、
  Apply invoke 0、target不変、NIC未切断を確認して清掃した。

各試行は新しいnamespace／snapshotを使い、保存済みoperationを再送していない。rollback採用caseの初回collectorは
実NIC断用relayを使用する本Gateに対し、旧natural rollback用の`transport_injected=false`条件を誤適用して停止した。
operationは再実行せず、保存済み証拠に対するcollector契約だけを補正して再収集した。

## Cleanupと証拠整合性

- 採用2 caseともUbuntu／Debian package、manual path、sessionを開始baselineへ完全復元した。
- 一時snapshot `phase6-final-ssh-commit-net4-20260917`と
  `phase6-final-ssh-rollback-net2-20260917`を復元後に削除した。両VMはrunning。
- Gateが作成したDebian Secret Serviceの`local-master-v1` 1件は、開始時不在と今回属性を監査したうえで
  正確な1件だけ削除し、cleanup後の一覧が空であることを保存した。秘密値は読んでいない。
- 関連GUI、watcher、relay、runtime watcher、認証待ちprocessは残っていない。
- snapshot復元後はNTP設定を変えずsystem clockだけを同期した。hwclockは利用できない。
- 両採用directoryで`sha256sum -c SHA256SUMS`が全件成功した。
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests`は806件中
  767成功・39 expected skip。Gate script 6本のAST parseと`git diff --check`も成功した。

主な証拠:

- 正常系: `commit-result.json`、`commit-transport-events.json`、`network.json`、
  `operation-evidence.json`、`commit-results.png`、`cleanup-result.json`
- rollback系: `rollback-result.json`、`rollback-transport-events.json`、`network.json`、
  `runtime-watcher-result.json`、`operation-evidence.json`、`rollback-results.png`、
  `production-key-after-cleanup-audit.json`、`cleanup-result.json`

## Release状態

公開チェックリストは38/44から40/44、**90.9%**へ更新した。残る4項目はrelease set `SHA256SUMS`、
artifact署名、signed tag、公開先からの再取得検証。今回、署名、tag、公開は行っていない。
