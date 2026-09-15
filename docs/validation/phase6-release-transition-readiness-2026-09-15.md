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
- [release notes draft](../release-notes-0.1.0-draft.md): 必須sectionを作成済みだが、
  release date、distribution、fingerprint、final source/artifact identityは未確定
- release用`SHA256SUMS`: 未作成
- release専用OpenPGP key: fingerprint・保管責任者とも未指定

candidate 2 artifactのSHA-256は本監査時にも再計算し、上記採用値と一致した。
worktreeは監査開始時にcleanで、`HEAD`と`origin/main`も一致した。

## Decisions required before the final source commit

### Target distribution

`debian/changelog`の`UNRELEASED`を置き換える値を指定する必要がある。Debian packageの
通常の開発・一般配布用metadataとしては`unstable`が第一候補だが、これは自動決定しない。
選択と同時にrelease日時、最終変更点、changelog署名者表記を確定する。

現在のMaintainerとchangelog署名者は
`LLM-Manager contributors <noreply@example.invalid>`である。package metadataとしてこの
placeholderを維持するか、公開連絡先へ変更するかも同じrelease metadata判断に含める。

### Signing identity and custody

次の2点を利用者が明示する必要がある。

1. release専用OpenPGP keyの完全fingerprint
2. 秘密鍵の保管責任者

既存の個人鍵を列挙・推測選択せず、新しい鍵を自動生成しない。秘密鍵をrepository、VM、
artifact、build log、validation evidenceへ複製しない。

### Publication authorization

公開候補先は既存のpublic GitHub repositoryのGitHub Releasesだが、通常のcommit/push承認は
release作成、tag作成、artifact uploadの承認を兼ねない。公開先と公開実行の承認を別途得る。

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
