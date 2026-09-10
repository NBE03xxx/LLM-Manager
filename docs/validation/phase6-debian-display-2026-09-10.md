# Phase 6 Debian desktop/menu candidate Gate

## 結果

Debian 13の通常ログイン済みWayland desktopで、commit `4722cfa`由来の
`llm-manager_0.1.0_all.deb`をアプリケーションメニューから起動できた。
candidate SHA-256は`25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`。
GNOMEの検索で`llm`を入力し、表示されたLLM-ManagerをEnterで起動した。
PID 3161はUID/GID 1000で、argvは`/usr/bin/python3 -I /usr/bin/llm-manager`。
英語のHosts画面、Tabによるhost selectorからlanguage selectorへの移動、
Downによる日本語切替と日本語のナビゲーション描画を確認した。
Alt+F4で通常終了し、`pgrep -a -f /usr/bin/llm-manager`のexit 1でプロセス不在を確認した。

これはUNRELEASED candidateの実display/menu Gateである。最終artifactでの再実行、
screen reader、長時間負荷、SSH Apply切断照合は別の残件。

## 証拠と復元

[証拠directory](debian-display-2026-09-10/)に以下を保存した。

- `menu-search.png`: メニュー内のLLM-Managerとicon
- `menu-launched.png`: メニューから起動した英語画面
- `keyboard-language.png`: host selectorのkeyboard focus
- `japanese.png`: 日本語切替後の実画面
- `baseline.json`、`installed.json`、`cleaned.json`: package版・architecture・状態とAPT manual一覧
- `apt-simulation.txt`、`apt-install.txt.gz`、`apt-purge-simulation.txt`、`apt-purge.txt.gz`

APT実行logは進捗表示のCRを含む原文byteを保持するためgzipで保存した。

導入前にbaselineをホストへ保存し、candidate転送後のhashを照合した。
APT simulationはcandidateと依存11件だけを選択し、既存packageの削除・更新はなかった。
install後の差分と固定12件の一致、既存package不変、`dpkg -V llm-manager`無出力を確認した。
終了後はpurgeのsimulationも固定12件との一致を検査し、その12件のみを明示purgeした。
`baseline.json`と`cleaned.json`は完全一致。`apt-get check`成功、`dpkg --audit`無出力。
転送した`/tmp/llm-manager-display-20260910.deb`を削除した。

今回の開始時は両VMともrunning。電源・snapshot操作は行わず、終了時も両VMがrunningである。
Debianのsession 2はType=wayland、Active=yes、State=active、LockedHint=no。
最初のscreenshotは`Display output is not active`だったが、ユーザーがビューアーで
デスクトップを表示した後に検証を実施した。

## SSHとセッション判定の訂正

前回記録した「SSH設定が再び不正になり管理者修復が必要」という結論は取り下げる。
前回の所有者表示とSSH失敗はサンドボックス内で観測され、実ホスト側での再確認が不足していた。
今回、サンドボックス外でsymlinkはUID/GID 0、参照先はUID/GID 0・0644、
`ssh -G github.com`成功、通常system SSHでUbuntu UID 1000への接続成功を確認した。
SSH設定変更や`-F /dev/null`は使用していない。SSH GUI Gateは続行可能。

`guest-get-users`は両VMとも空だったが、loginctlでは通常desktop sessionが存在した。
以後はguest-agentの一覧だけでログイン不在と判定せず、loginctlのsession class/type/activeと
実画面を併せて確認する。

## SBOM evidenceの再検証

`packaging/verify-environment-evidence.py`を追加した。archiveを展開・実行せずに
外側・内側checksumの全file coverage、指定candidate hash、summary、installed TSV、
inventory、BOMのdpkg metadata、copyright hash、review件数、collector exit、dpkg auditを照合する。
path traversal、link、重複path、過大archiveを拒否する。CycloneDX schema検証や
license obligationの完了判定、collector観測の真正性保証は含まない。
前回の3 archiveは全て成功。改ざん・別candidate・一覧不一致などの6 regression testも成功。

host全797 test（759成功・38 expected skip）、compileall、packaging shell syntax、
desktop-file validation、両直接依存SBOM JSON parse、`git diff --check`が成功した。

再実行例（repository rootから）:

```bash
python3 packaging/verify-environment-evidence.py \
  --archive docs/validation/sbom-2026-09-09/debian13-local-0.1.0-evidence.tar.xz \
  --artifact /tmp/llm-manager-release-candidate-4722cfa/llm-manager_0.1.0_all.deb \
  --package llm-manager --version 0.1.0
```

現在・次ともPhase 6。次は通常system SSHを使うGUI Apply切断/immutable result照合、
残るlicense reviewと最終release setの確定。署名鍵は未指定。
