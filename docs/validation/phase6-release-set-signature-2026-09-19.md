# Release set `SHA256SUMS` detached signature（2026-09-19）

## 結論

利用者が明示承認した範囲に従い、final release setの`SHA256SUMS`へASCII armored detached
OpenPGP signatureを作成した。署名副鍵fingerprintを完全指定し、公開鍵だけをimportした隔離GPG
homeで`GOODSIG`と`VALIDSIG`を確認した。manifestは変更されず、署名後も9対象すべての
`sha256sum --check`に成功した。

この作業ではGit tagを作成せず、artifactを公開していない。signed tagと公開後再取得検証には、
それぞれ後続の明示承認と実行が必要である。

## 対象

- build source commit: `5b7d4de03e495fe630deab952de043f945a22bd7`
- release directory: `/tmp/llm-manager-final-5b7d4de-20260916/artifacts`
- manifest: `SHA256SUMS`
- manifest SHA-256: `147dba88d28af1e64f27a51cf70774fee65b62f9749877de4d321a2c138c647d`
- manifest mode: `0644`
- manifest entries: 9
- signature: `SHA256SUMS.asc`
- signature SHA-256: `3581654c520ab5dac6890d1579a1fb875c766964dc3bcd753e3bdc566a906c90`
- signature size/mode: 228 bytes / `0644`
- signature time: `2026-09-19T12:55:16Z`

## 署名

事前のread-only key inventoryで、release専用主鍵と署名副鍵が利用可能であることを確認した。
署名時は別の鍵を暗黙選択しないよう、次の署名副鍵fingerprintへ`!`を付けて完全指定した。

- primary: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- signing subkey: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
- identity: `NBE03xxx <NBE03247@nifty.com>`

最初のpinentry試行は入力前にtimeoutし、signature fileが作られていないことを確認した。再試行で
利用者がpinentryへ入力し、署名に成功した。passphraseや秘密鍵materialは記録・出力・repositoryへ
保存していない。

## 隔離検証

新しい一時GPG homeへrepositoryの`RELEASE_KEY.asc`だけをimportした。このkeyringの列挙結果で
上記primary／subkey fingerprintが完全一致し、secret key entryがないことを確認した。その環境で
次を実行した。

```text
gpg --homedir <isolated-public-key-only-home> --batch --status-fd 1 \
  --verify SHA256SUMS.asc SHA256SUMS
```

主要statusは次のとおり。

```text
GOODSIG D8F253C086BE34C2 NBE03xxx <NBE03247@nifty.com>
VALIDSIG 034DA1601E14BE534254BA4DD8F253C086BE34C2 2026-09-19 1789822516 0 4 0 22 10 00 353F4D4F55175F537FBCD07C3E2532969B404FFD
TRUST_UNDEFINED 0 pgp
```

`TRUST_UNDEFINED`は新しいkeyringでowner trustを設定していないため期待どおりである。判定には
外部のtrust databaseではなく、release notesで固定済みのprimary／signing subkey fingerprintとの
完全一致と`VALIDSIG`を使用した。隔離環境ではsecret-key照会時にgpg-agent起動警告が出たが、
公開鍵の列挙とdetached signature検証は成功しており、秘密鍵は検証に使用していない。

## 署名後のrelease set検査

署名対象manifestのSHA-256が作成前の正本と同じであることを確認した。続けてrelease directoryで
`sha256sum --check SHA256SUMS`を実行し、公開鍵、source archive、直接依存SBOM 2件、両deb、
resolved-environment SBOM 3件の9/9が`OK`となった。detached signatureはmanifest自身へ追加せず、
`SHA256SUMS.asc`としてmanifestと対で配布する。

## 保存証拠

- `release-set-signature-2026-09-19/SHA256SUMS.asc`: 配布用signatureのbyte-identical copy
- `release-set-signature-2026-09-19/verification.json`: 検証結果とfingerprint
- `release-set-signature-2026-09-19/EVIDENCE-SHA256SUMS`: 上記2fileのhash

この完了で公開checklistは42/44、95.5%。残件はsigned tagと公開先からの全artifact再取得検証である。
