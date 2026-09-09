# Phase 6 `0.1.0` Ubuntu lifecycle Gate

## 結果

commit `4722cfa5238af507deee0831bdf8a0cbe517fe99` から再現buildしたlocal candidate
`llm-manager_0.1.0_all.deb`（SHA-256
`25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`）を、Ubuntu
26.04の一時snapshot内で検証した。

既存`llm-manager 0.1.0~dev0-1`からのupgrade、同一version reinstall、remove、fresh
install、purgeはすべて成功した。candidateの`dpkg -V`、隔離Python import、通常userの
offscreen Qt起動、主要installed fileのowner/modeも成功した。これは`UNRELEASED` candidate
のpre-final Gateであり、Wayland実display/menuと最終artifactのGateを完了扱いにはしない。

## 開始状態

- VM: `ubuntu26.04`、running、IP `192.168.122.48`
- 接続: hostの通常system SSH、UID 1000、BatchMode
- package: `llm-manager 0.1.0~dev0-1`
- package数: 1913
- sorted package set SHA-256:
  `b9d31c0708f9bba521ddae6afc272816fe53affb80291ad9665607412ea93008`
- local GUI launcherは未収録、旧`/usr/bin/llm-manager-helper`は収録
- 一時snapshot: `phase6-0.1.0-lifecycle-20260909`

既存のdpkg管理外backupは変更対象から除外し、内容を読まずroot guest agentでハッシュだけを
照合した。

| Evidence | 開始時SHA-256 |
|---|---|
| `receipt.json` | `8023e5e7ae96fa7d5f79c07110675dde1079e80b96b0dc0c967f4c879be90647` |
| `retention.json` | `d54c88b264b4b10ebf26be4b5e24a6cc454ac2d8ad35ad8d4d2f8e414fbb6337` |

## Lifecycle

1. candidateを通常user所有0644で`/tmp/llm-manager_0.1.0_all.deb`へ転送し、host artifactと
   SHA-256一致を確認した。
2. `apt-get install`で`0.1.0~dev0-1`から`0.1.0`へupgradeした。追加packageは0件。
3. `apt-get install --reinstall`で同一`0.1.0`を再導入した。
4. `apt-get remove`でpackageを削除した。全主要package-owned pathの不在、既存依存
   `python3-jeepney 0.9.0-2`と`python3-secretstorage 3.5.0-1`の保持を確認した。
5. package不在状態からcandidateをfresh installした。
6. `apt-get purge`でpackageを削除した。package数は旧packageを除いた期待値1912となり、
   package-owned pathは残らなかった。依存2件とdpkg管理外backupは保持された。

upgrade、reinstall、fresh installの各installed状態でpackage versionは`0.1.0`、`dpkg -V`は
無出力だった。fresh installでは`/usr/bin/python3 -I`による`llm_manager.__version__`が
`0.1.0`となり、`QT_QPA_PLATFORM=offscreen`のGUIは5秒間継続してtimeout 124で終了した。
logはPySide6の既知の`propagateSizeHints`警告だけだった。

launchersはroot:root 0755、desktop/icon/metadata/notices/SBOMはroot:root 0644だった。各
remove/purge境界で、利用者保全用backupの上記2ハッシュが開始値と一致した。

## 原状復帰

検証用debとoffscreen logを限定pathから削除後、一時snapshotへrevertした。次を開始状態と
照合した。

- `llm-manager 0.1.0~dev0-1`、`dpkg -V`無出力
- package数1913、sorted package set SHA-256完全一致
- 旧helperあり、candidateのGUI/review launcherなし
- 検証用deb/logなし
- dpkg管理外backupの両SHA-256完全一致

revert後、一時snapshotだけを削除した。既存`phase4-pre-local-deb-20260831` snapshotは保持し、
Ubuntu VMは開始時どおりrunningとした。host/guestのSSH設定、Secret Service、実設定、service、
backup/keyは変更していない。

現在・次ともPhase 6。次は同じcandidate setを使うDebian 13 lifecycle/実display、local/remote
resolved-environment SBOMとQt license reviewを進める。`UNRELEASED`解除後は最終commitから
artifactを再buildし、本Gateを最終artifactで再実行する。
