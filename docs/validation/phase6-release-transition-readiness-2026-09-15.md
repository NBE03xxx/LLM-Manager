# Phase 6 release transition readiness audit (2026-09-15)

## Outcome

Phase 6 の pre-final candidate は再現build、installed UI、主要な機能・安全性Gateを
通過している。一方、公開用の最終source commitを確定するために必要なrelease metadataと
署名責任が未確定である。このため、`UNRELEASED`を解除せず、最終artifactのbuild、署名、
tag、公開は開始しない。

公開checklistの完了数は18/44、40.9%のまま。pre-final evidenceを最終artifact evidenceへ
読み替えない。

## Audited state

- local `HEAD`と`origin/main`: `c86f04da5fc4204000e387ec6b2b1e377351002f`
- product source commit: `7f846f5fb1134be7df06490f30a5216ab414ae0d`
  - `c86f04d`はinstalled UI Gateのscript、証拠、文書を追加した検証commitである。
- version: `0.1.0`
- Debian distribution: `UNRELEASED`
- changelog日時: `Sat, 29 Aug 2026 22:00:00 +0900`（release日時ではない）
- adopted pre-final candidate:
  - local deb: `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a`
  - remote helper deb: `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2`
- candidateの保存先: `/tmp/llm-manager-candidate-7f846f5-20260915/`
- GitHub repository: `NBE03xxx/LLM-Manager`、public、default branch `main`
- remote tag: 0件
- GitHub Release: 0件
- [release notes draft](../release-notes-0.1.0-draft.md): 必須sectionを作成済み。release dateと
  final source/artifact identityは未確定
- release用`SHA256SUMS`: 未作成
- planned distribution: `unstable`（changelogはrelease日時確定まで`UNRELEASED`）
- changelog signer/maintainer: `NBE03xxx <NBE03247@nifty.com>`
- release専用OpenPGP primary fingerprint:
  `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- signing subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
- key custodian: `Project owner (NBE03xxx)`
- publication destination: GitHub Releases

candidate 2 artifactのSHA-256は本監査時にも再計算し、上記採用値と一致した。
worktreeは監査開始時にcleanで、`HEAD`と`origin/main`も一致した。

## Decisions completed before the final source commit

### Target distribution

`debian/changelog`のtarget distributionは`unstable`と決定した。実際の置換はrelease日時と
最終変更点を確定するfinal source transitionで行う。

Maintainerとchangelog署名者は`NBE03xxx <NBE03247@nifty.com>`と決定し、placeholderを
package metadataから除去する。

### Signing identity and custody

利用者が[release専用鍵を作成・検証](phase6-release-signing-key-2026-09-15.md)した。保管責任者は
`Project owner (NBE03xxx)`。主鍵は5年、署名副鍵は1年の期限とし、後継者は指定しない。
秘密鍵をrepository、VM、artifact、build log、validation evidenceへ複製しない。

### Publication authorization

公開先は既存のpublic GitHub repositoryのGitHub Releasesと決定した。通常のcommit/push承認は
release作成、tag作成、artifact uploadの承認を兼ねないため、公開実行の直前確認は別途行う。

## Ordered final sequence

再buildやOS Gateをmetadata変更で無効にしないため、次の順序を固定する。

1. target distribution、release日時、changelog署名者表記、OpenPGP fingerprint／保管責任者、
   公開先を確定する。
2. `debian/changelog`とrelease notesを完成させ、全version surfaceとscope文書を検査して
   final source commitを作る。
3. clean sourceからlocal/remote両debを独立2回buildし、byte identity、両verifier、展開後の
   package identity・owner/mode・固定launcher・PolicyKit境界・収録文書を確認する。
4. 同じfinal artifactをUbuntu 26.04 local、Debian 13 local、Ubuntu 26.04 remote helperへ導入し、
   resolved-environment SBOM、license evidence、binary監査を採取する。
5. 同じartifactで全lifecycle、通常display/menu、local Apply/rollback/manual restore、SSH
   Apply/rollback/切断照合、最終security corpusを再実行し、各環境のcleanupを確認する。
6. 両deb、source archive、直接依存SBOM、resolved-environment SBOMからrelease setを固定し、
   `SHA256SUMS`を作る。
7. 指定fingerprintで`SHA256SUMS`とGit tagを署名し、別環境でfingerprint指定検証する。
8. 明示承認後にGitHub Releaseへ公開し、公開先から全artifactを再取得してchecksum、署名、
   package verifierを再実行する。

手順2以降にsourceまたはrelease metadataを変更した場合、それ以前のfinal artifact identityと
後続Gateを無効として、影響する手順から再実行する。

## Ready work versus blocked work

判断後すぐに実行できるbuild、verifier、SBOM collector、VM lifecycle／GUI Gateの手順と
pre-final baselineは整備済みである。release notesは必須sectionと検証手順をdraft化した。
最終artifactへ結び付くチェック項目は、final source commit確定前には完了扱いにしない。

未確定事項を既知制限へ移して公開すること、署名なしで公開すること、既存鍵を便宜的に選ぶことは
この監査の結論に含まれない。
