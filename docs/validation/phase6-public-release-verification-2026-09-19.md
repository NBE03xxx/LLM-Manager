# GitHub Release公開後再取得検証（2026-09-19）

## 結論

利用者の明示承認に基づき、署名タグ`v0.1.0`へGitHub Release
[LLM Manager 0.1.0](https://github.com/NBE03xxx/LLM-Manager/releases/tag/v0.1.0)を公開した。
final release setの11 fileをassetとしてuploadし、GitHub APIのasset集合、size、state、SHA-256 digestを
正本と照合した。

さらに認証情報を使わない公開download URLから11 fileすべてを新しいdirectoryへ再取得した。
公開先由来のfileだけを使い、manifest checksum 9/9、隔離GPG環境でのmanifest signature、両deb
verifier、3 resolved-environment evidence verifier、署名タグとsource commitの結合を再検証した。
すべて成功し、MVP release checklistは44/44、100.0%となった。

## 公開identity

- release URL: `https://github.com/NBE03xxx/LLM-Manager/releases/tag/v0.1.0`
- published at: `2026-09-19T13:07:34Z`
- draft: false
- prerelease: false
- release asset: 11 file、全件`uploaded`
- signed tag object: `e766d2041e83fedffb5fd3180aabadbc8696345e`
- tag peeled target: `5b7d4de03e495fe630deab952de043f945a22bd7`
- final artifact build source: `5b7d4de03e495fe630deab952de043f945a22bd7`

GitHub Release APIの`target_commitish`表示は`main`だが、既存tagを指定したReleaseのsource identityは
tag objectとそのpeeled targetで判定した。remote `refs/tags/v0.1.0^{}`は上記build source commitと
一致し、公開後も隔離GPG環境でtag signatureの`GOODSIG`／`VALIDSIG`に成功した。

## 公開asset集合

| asset | bytes | SHA-256 |
| --- | ---: | --- |
| `RELEASE_KEY.asc` | 807 | `ca9aa1f6cc747008d1133aa688e887fe31a10ce2de87ced5cb044e7f0736d9f8` |
| `SHA256SUMS` | 933 | `147dba88d28af1e64f27a51cf70774fee65b62f9749877de4d321a2c138c647d` |
| `SHA256SUMS.asc` | 228 | `3581654c520ab5dac6890d1579a1fb875c766964dc3bcd753e3bdc566a906c90` |
| `llm-manager-0.1.0.tar.gz` | 37,075,955 | `6d569199110bdc155a14c0a6222353ccc92380b63b20cfebff083ace1c91fe18` |
| `llm-manager-remote-helper.cdx.json` | 1,413 | `1878023f02c347018deb663b5b657d1a70b0b744f7997276598391bc35b2d09b` |
| `llm-manager-remote-helper_0.1.0_all.deb` | 137,958 | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4` |
| `llm-manager-remote-helper_0.1.0_ubuntu-26.04_environment-sbom.tar.xz` | 1,835,720 | `0849f2a21c4eaca844e2abd1977606c6646fb1b54dc8b6aabeaf8ec8e6c651c1` |
| `llm-manager.cdx.json` | 2,708 | `ed224935304652d6ac9bb613376f8f85c28462d15786059e3729ff9f332cf89a` |
| `llm-manager_0.1.0_all.deb` | 151,784 | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` |
| `llm-manager_0.1.0_debian-13_environment-sbom.tar.xz` | 1,974,996 | `c51602b536cc618acc2847666e13ef214e500578341291b0779c8ea8e9eea8b0` |
| `llm-manager_0.1.0_ubuntu-26.04_environment-sbom.tar.xz` | 1,835,384 | `e1ef61769f2c4db749353d1ebe34adc324858488b8e0c7e91df214572ec30eae` |

GitHub APIが返した11 digestは上記と全件一致した。asset名は過不足・重複なしで、公開後download
directoryの11 entryはすべて通常fileかつsymlinkなしだった。

## 認証なし再取得

GitHub CLIによる初回再取得とは別に、`GH_TOKEN`等を渡さない`curl`で各
`https://github.com/NBE03xxx/LLM-Manager/releases/download/v0.1.0/<asset>`から取得した。
最終検証directoryは`/tmp/llm-manager-v0.1.0-public-unauth-20260919`。元artifact directoryからの
copyやhardlinkは使用していない。

## Checksumと署名

公開downloadの`SHA256SUMS`に対する通常`sha256sum --check`は9/9成功した。このmanifestは
公開鍵、source archive、直接依存SBOM 2件、両deb、resolved-environment SBOM 3件をcoverする。

公開downloadの`RELEASE_KEY.asc`だけを新しい一時GPG homeへimportした。primary fingerprint
`353F4D4F55175F537FBCD07C3E2532969B404FFD`と署名副鍵fingerprint
`034DA1601E14BE534254BA4DD8F253C086BE34C2`を完全一致で確認し、secret key fileがない状態で
`SHA256SUMS.asc`を検証した。`GOODSIG`と`VALIDSIG`に成功し、`TRUST_UNDEFINED`はowner trustを
設定しない新規keyringなので期待どおりだった。一時GPG homeは検証後に削除した。

## Package／environment検証

- `packaging/verify-deb.sh`: 公開downloadのlocal debに成功
- `packaging/remote/verify-deb.sh`: 公開downloadのremote helper debに成功
- Ubuntu 26.04 local evidence: integrity成功、1,907 package
- Debian 13 local evidence: integrity成功、2,248 package
- Ubuntu 26.04 remote helper evidence: integrity成功、1,908 package

Ubuntu evidenceに記録済みの既存Brave 2 packageのcopyright metadata欠落は従来の既知観測と一致する。
environment verifierの`license_review_complete: false`は、このintegrity verifierがlicense判定を
代替しない設計上の表示であり、公開assetの不一致ではない。

## Release本文

tracked release notesを公開本文に使用した。準備中の公開禁止文言を確定状態へ更新し、11 asset名、
manifest hash、OpenPGP fingerprint、signed tag targetを明記した。Recovery guideは署名タグ内の
固定文書へ絶対URLで結び、公開後に本文とtracked notesが末尾改行を除いて一致することを確認した。

## 保存証拠

- `public-release-verification-2026-09-19/verification.json`: release metadata、11 asset、全検証結果
- `public-release-verification-2026-09-19/EVIDENCE-SHA256SUMS`: verification JSONのhash

これによりPhase 6 MVP releaseの公開checklist 44項目はすべて完了した。
