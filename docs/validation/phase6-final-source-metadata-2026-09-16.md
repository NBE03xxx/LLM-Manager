# Phase 6 final source metadata transition (2026-09-16)

## Outcome

確定済みのrelease判断をsource metadataへ反映した。`debian/changelog`のdistributionを
`UNRELEASED`から`unstable`へ変更し、release日時を`Wed, 16 Sep 2026 18:49:47 +0900`、
署名者を`NBE03xxx <NBE03247@nifty.com>`へ固定した。release notesは2026-09-16、signed tag
`v0.1.0`、source archive `llm-manager-0.1.0.tar.gz`を記載し、build後に確定するartifact identityは
同じrelease setの`SHA256SUMS`を正本とする。

これは公開許可ではない。final source commitからの再現build、resolved-environment SBOM、binary／
license監査、OS／GUI／security Gate、checksum署名、signed tag、GitHub Release公開後再検証は
引き続き必要である。通常のcommit／push承認を署名、tag、公開の承認へ読み替えない。

## Input state

- branch: `main`
- transition前HEAD／`origin/main`: `9832cebc85c35095b8301a37988ac6d847d99433`
- product source commit: `7f846f5fb1134be7df06490f30a5216ab414ae0d`
- pre-final local artifact SHA-256:
  `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a`
- pre-final remote artifact SHA-256:
  `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2`
- OpenPGP primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- signing subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
- publication destination: GitHub Releases（実行は別承認）

pre-final artifactのhashはtransition開始時に再計算して上記と一致した。final artifactへは読み替えない。

## Source identity rule

tracked release notesへfinal commit IDを埋め込むと自己参照になりcommit IDが変化する。このためsource
identityは固定名のsigned tag `v0.1.0`で表し、署名検証時にtag targetの完全commit IDとbuild記録の
source commit IDを一致させる。artifactの完全SHA-256は署名対象の`SHA256SUMS`へ一元化する。

## Validation and next boundary

metadata変更後に全unit test、compileall、shell syntax、desktop entry、両直接依存SBOM JSON、
version surface、OpenPGP公開鍵、whitespaceを検査する。成功後にfinal source commitを作り、その
clean sourceからlocal／remote artifactを独立2回buildする。build以降にsourceまたはrelease metadataを
変更した場合は、影響するfinal Gateを新しいsource commitからやり直す。

検査結果:

- unit test: 806件（767 pass、39 expected skip）
- `dpkg-parsechangelog`: version `0.1.0`、distribution `unstable`、上記release日時
- shell syntax、desktop entry、両CycloneDX JSON: 成功
- repository公開鍵: primary／signing subkeyの完全fingerprint一致、秘密packetなし
- `git diff --check`: 成功
