# Phase 6 release set SHA256SUMS（2026-09-17）

## Outcome

**成功。** Final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`から作成・検証済みの
release artifact directoryへ`SHA256SUMS`を作成し、対象9件を通常`sha256sum`と独立したPython
`hashlib.sha256`実装の両方で再hashした。全件一致し、対象名の重複、欠落、余分なrelease file、
symlinkはなかった。

Primary manifest:

`/tmp/llm-manager-final-5b7d4de-20260916/artifacts/SHA256SUMS`

- mode: `0644`
- size: 933 bytes
- SHA-256: `147dba88d28af1e64f27a51cf70774fee65b62f9749877de4d321a2c138c647d`
- 証拠copy: `release-set-sha256-2026-09-17/SHA256SUMS`

## 対象

| category | file | SHA-256 |
| --- | --- | --- |
| public key | `RELEASE_KEY.asc` | `ca9aa1f6cc747008d1133aa688e887fe31a10ce2de87ced5cb044e7f0736d9f8` |
| source | `llm-manager-0.1.0.tar.gz` | `6d569199110bdc155a14c0a6222353ccc92380b63b20cfebff083ace1c91fe18` |
| direct SBOM | `llm-manager-remote-helper.cdx.json` | `1878023f02c347018deb663b5b657d1a70b0b744f7997276598391bc35b2d09b` |
| remote deb | `llm-manager-remote-helper_0.1.0_all.deb` | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4` |
| resolved SBOM | `llm-manager-remote-helper_0.1.0_ubuntu-26.04_environment-sbom.tar.xz` | `0849f2a21c4eaca844e2abd1977606c6646fb1b54dc8b6aabeaf8ec8e6c651c1` |
| direct SBOM | `llm-manager.cdx.json` | `ed224935304652d6ac9bb613376f8f85c28462d15786059e3729ff9f332cf89a` |
| local deb | `llm-manager_0.1.0_all.deb` | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` |
| resolved SBOM | `llm-manager_0.1.0_debian-13_environment-sbom.tar.xz` | `c51602b536cc618acc2847666e13ef214e500578341291b0779c8ea8e9eea8b0` |
| resolved SBOM | `llm-manager_0.1.0_ubuntu-26.04_environment-sbom.tar.xz` | `e1ef61769f2c4db749353d1ebe34adc324858488b8e0c7e91df214572ec30eae` |

公開鍵もrelease notesで同じrelease setに含めるためchecksum対象にした。`SHA256SUMS`自身と、後続で
別承認により作る可能性がある`SHA256SUMS.asc`は自己参照を避けるため対象外。

## Verification

- artifact directoryで`sha256sum --check SHA256SUMS`: 9/9 `OK`。
- Python標準ライブラリでmanifestを独立parseし、9件を再hash: 全件一致。
- manifest entryは辞書順、重複なし、安全なbasenameのみ、全targetが通常file。
- directory内のmanifest以外のfile集合とentry集合が完全一致。
- `packaging/verify-deb.sh`と`packaging/remote/verify-deb.sh`: 成功。
- `packaging/verify-environment-evidence.py`を3 archiveへ再実行: integrity 3/3成功、package数は
  Ubuntu local 1,907、Debian local 2,248、Ubuntu remote helper 1,908。Ubuntuの既存非依存Brave
  2件とlicense verdictを自動完了しない境界は以前のreviewどおり。
- `RELEASE_KEY.asc`と直接依存SBOM 2件は、final source commit内の対応fileとbyte一致。
- source archive、両deb、resolved-environment archiveのhashは既存final build／SBOM証拠と一致。

機械可読結果は`release-set-sha256-2026-09-17/verification.json`へ保存し、証拠copyと合わせて
`EVIDENCE-SHA256SUMS`で整合性を固定した。

## `/tmp`揮発後の復元（2026-09-19）

作成・検証後に日付をまたいだ実行環境で`/tmp`のprimary release directoryが消失したため、同一byteの
release setを復元した。両debは記録済みraw source tar（SHA-256
`9306b61d23ecd02522a07405dcff08a317f5568bace68d8f32d72e97fbab099d`）から、元と同じ
`umask 0022`、`dpkg-buildpackage -us -uc -b`、`packaging/remote/build-deb.sh`で再現buildし、
元hashへ一致した。source archiveは同じprefix付き`git archive`と`gzip -n`で元hash／sizeへ一致した。
3つのresolved-environment archiveはtracked証拠copyから復元し、直接依存SBOM／公開鍵はfinal source
commitから復元した。

復元後に`sha256sum --check` 9/9、独立Python再hash、両deb verifier、3環境証拠verifierを再実行し、
全806 unit test（767成功・39 expected skip）も含めてすべて成功した。release artifact identityと
manifest内容は変更していない。

## Release状態

release checklistは40/44から41/44、**93.2%**へ更新する。残りは`SHA256SUMS`のdetached signature、
build source commitを指すsigned tag、公開先からの全artifact再取得検証の3項目。
今回、秘密鍵へのアクセス、署名、tag作成、公開は行っていない。
