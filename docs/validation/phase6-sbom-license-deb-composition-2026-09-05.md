# Phase 6 SBOM/license deb composition — 2026-09-05

## 結論

未コミットのPhase 6 review対象を新しい`/tmp` copyへ複製し、local debとremote helper debをbuildした。両packageへMIT copyright、third-party notices、package別CycloneDX 1.6直接依存SBOMを収録し、verifierとarchive inspectionに成功した。artifactは`0.1.0~dev0` / `UNRELEASED`であり、VM lifecycle、resolved dependency SBOM、署名を完了していないためrelease候補ではない。

## 変更したdistribution境界

- `LICENSE`のholderに合わせ、`debian/copyright`を`2026 NBE03xxx`へ統一した。
- local deb: `/usr/share/doc/llm-manager/{copyright,THIRD_PARTY_NOTICES.md,llm-manager.cdx.json}`。
- remote helper deb: `/usr/share/doc/llm-manager-remote-helper/{copyright,THIRD_PARTY_NOTICES.md,sbom.cdx.json}`。
- Python source dependencyと一致するよう、両debのcryptographyを`>= 43.0.0, << 47`に制約した。local SecretStorageも`>= 3.3.3, << 4`とした。
- remote helper buildは`debian/changelog`のtimestampを`SOURCE_DATE_EPOCH`として使用する。

直接依存SBOMはAPT runtime dependencyが別packageであり、debへvendoringされないことを前提とする。APTが解決する推移依存の正確なversion/licenseは最終artifactのclean install後に別のresolved-environment SBOMとして採取する。

## Composition artifact

| Package | Version / arch | SHA-256 | Rebuild |
|---|---|---|---|
| `llm-manager` | `0.1.0~dev0` / `all` | `5c286c874b979aaa680fce4778a1b37e45fd0b2d96a97d728ab1307dec79def2` | 同一snapshotから2回一致 |
| `llm-manager-remote-helper` | `0.1.0~dev0` / `all` | `d6fcbe5b7ef9639c70dc565b80d626271c462515e92b0208afd14298a3d04ab2` | `SOURCE_DATE_EPOCH`修正後2回一致 |

remote helperは修正前、同一sourceから異なるhashになる問題を実際に検出した。timestamp固定後の2 artifactを`cmp`し、bit-for-bit一致を確認した。

## 検証

- `packaging/verify-deb.sh`: 成功。
- `packaging/remote/verify-deb.sh`: 成功。
- archive内のcopyright/notices/SBOM、launcher、helper、desktop/icon、private runtimeのroot owner/mode: verifierで成功。
- 全522 test実行、504成功・18 skip。失敗なし。
- compileall、shell syntax、desktop-file-validate、両SBOM JSON parse、git diff check成功。
- build時にhost service manager由来の`Failed to create stream fd: Operation not permitted`が出たが、build/test/verifierはexit 0で完了した。artifact結果の代替根拠にはしていない。

## 残件

- 最終versionとrelease commitのfreeze。
- Ubuntu 26.04 / Debian 13の最終artifact lifecycleとresolved dependency/license SBOM。
- Debian 13の通常login desktop menu実display Gate。
- release scopeの未完成root/restore route判断。
- release signing key fingerprint、`SHA256SUMS`署名、signed tag、公開後再検証。

次の作業もPhase 6。performance、長時間Agent、長文layout/accessibilityのうちhostだけで進められる検査を先行し、desktop実displayとfinal lifecycleはrelease候補artifact確定後に行う。
