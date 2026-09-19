# LLM-Manager 0.1.0 release notes

Release date: 2026-09-16

このreleaseはPhase 6の最終artifact Gate、release set checksum／署名、signed tagの検証を
完了しています。download後は下記手順でchecksumと署名を確認してください。

- Debian changelog distribution: `unstable`
- release OpenPGP primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- source identity: signed tag `v0.1.0`（tag targetの完全commit IDを検証する）
- artifact identity: release setの`SHA256SUMS`を正本とする

## Overview

LLM-Manager 0.1.0は、ローカルLinux PCまたは既存のOpenSSH接続先にあるOllamaと
OpenCodeを診断し、用途別の推奨をレビューしてから安全に適用する最初のMVP releaseです。
Backup、明示承認、Apply、runtime validation、失敗時rollbackを分離し、GUI自体をrootで
起動しません。

## Supported systems

- Ubuntu 26.04
- Debian 13
- Python 3.13以上（検証baseline: Python 3.14.4、Debian 13 system Python 3.13）
- Ollama 0.33.2、OpenCode 1.18.25を初期検証baselineとする

上記以外のOSや周辺ソフトウェアversionは検出できても、このreleaseの正式対応範囲では
ありません。

## Public mutation routes

- local userのOpenCode設定: Apply、自動rollback、単一targetの手動restore
- SSH userのOpenCode設定: Apply、自動rollback、切断後のimmutable result照合
- local rootのOllama設定: 事前にLLM-Managerが採取した互換backupからの手動restore

SSH先には別artifactの`llm-manager-remote-helper`を管理者が事前導入します。local packageが
SSH先のhelperを自動installまたはupgradeすることはありません。

認証画面ではlocal PolicyKitを`LOCAL`、SSH loginとSSH先sudoを`REMOTE`および接続先付きで
表示します。passwordはOSのPolicyKit画面または外部terminalだけへ入力し、LLM-ManagerのGUI、
引数、標準入力へ渡さないでください。

## Artifacts

最終release setは次の11 fileです。

- `llm-manager_0.1.0_all.deb`
- `llm-manager-remote-helper_0.1.0_all.deb`
- `llm-manager-0.1.0.tar.gz`
- `llm-manager.cdx.json`
- `llm-manager-remote-helper.cdx.json`
- `llm-manager_0.1.0_ubuntu-26.04_environment-sbom.tar.xz`
- `llm-manager_0.1.0_debian-13_environment-sbom.tar.xz`
- `llm-manager-remote-helper_0.1.0_ubuntu-26.04_environment-sbom.tar.xz`
- `SHA256SUMS`
- `SHA256SUMS.asc`
- `RELEASE_KEY.asc`

## Install and upgrade

downloadしたdirectoryで、local GUI packageは次のようにAPTへ渡します。

```bash
sudo apt install ./llm-manager_0.1.0_all.deb
```

SSH先では、そのhost上でremote helper packageを導入します。

```bash
sudo apt install ./llm-manager-remote-helper_0.1.0_all.deb
```

同じコマンドで検証済み旧版からupgradeできます。導入前に下記のchecksumと署名を確認して
ください。

## Verify downloads

すべてのrelease artifactを同じdirectoryへ置き、まずchecksumを検証します。

```bash
sha256sum --check SHA256SUMS
```

続いて署名を検証します。

```bash
gpg --status-fd 1 --verify SHA256SUMS.asc SHA256SUMS
```

出力の`VALIDSIG`に含まれるprimary fingerprintが、公開済みrelease fingerprint
`353F4D4F55175F537FBCD07C3E2532969B404FFD`と完全一致することを別経路で確認してください。
署名副鍵fingerprintは`034DA1601E14BE534254BA4DD8F253C086BE34C2`です。key IDの短縮表示だけでは
判定しません。

## Remove or purge

local packageまたはremote helperを削除する場合は、対象hostでAPTを使用します。

```bash
sudo apt remove llm-manager
sudo apt purge llm-manager
```

```bash
sudo apt remove llm-manager-remote-helper
sudo apt purge llm-manager-remote-helper
```

upgrade、remove、purgeはpackage管理対象fileを扱います。user state、Secret Service鍵、
SSH先のroot-owned recovery copyや鍵を復旧目的で自動削除しません。OSやhome directoryを
廃棄する前に、backupと鍵を一貫した別の検証済み手段で保全してください。

## Recovery

Apply結果が`recovery_required`、restore結果が`failed`または`unknown`の場合、同じmutationを
再送しないでください。host identity、fingerprint、Plan/backup ID、target、error codeを記録し、
設定本文やsecretは共有しないでください。詳しい手順は
[Backup・Rollback・Recoveryガイド](https://github.com/NBE03xxx/LLM-Manager/blob/v0.1.0/docs/recovery-guide.md)を参照してください。

## Known limitations

- local root Applyは、根拠あるactionable Ollama recommendationと公開Gateが揃うまでI/O前に
  fail closedとなります。
- local root manual restoreには事前初期化と互換root backupが必要です。任意backupのimportや
  鍵の自動再作成は行いません。
- SSH userおよびSSH rootのmanual restoreは利用できません。
- SSH切断後のresult照合はread-onlyです。mutation requestを自動retryしません。
- audit hash chainは偶発的な改変検出用であり、同じuser権限を完全に侵害した攻撃者に対する
  外部署名ではありません。
- 未知のsecret形式を自動redactionで完全に検出する保証はありません。診断・復旧情報を共有する
  前に利用者自身でも確認してください。

## License and source

project-owned sourceとassetはMIT Licenseです。third-party notices、直接依存SBOM、最終OSで
解決した依存のSBOMをrelease setへ含めます。source repository:
`https://github.com/NBE03xxx/LLM-Manager`

## Release identity

- signed tag `v0.1.0` target: `5b7d4de03e495fe630deab952de043f945a22bd7`
- `SHA256SUMS` SHA-256: `147dba88d28af1e64f27a51cf70774fee65b62f9749877de4d321a2c138c647d`
- OpenPGP primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- OpenPGP signing-subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
