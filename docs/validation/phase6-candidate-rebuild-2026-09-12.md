# Phase 6 修正後candidate再現build — 2026-09-12

## 結果

検証済みのSSH GUI/通信測定・可視性test・英日Apply表示修正を
`b15a98454ddf9e397333350d371b35cc2ed8fdd8` にローカルcommitした。
そのtracked sourceだけからlocal/remote debを独立2回buildし、双方のbyte完全一致を確認した。

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0_all.deb` | `292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `ee4930896f02e72d7097c58878e8900bdb0c11a495b90fd3c7b6e14b0af034bc` |

採用artifactは `/tmp/llm-manager-candidate-b15a984-20260912/` に0644で保持。
以前の `4722cfa` candidateは削除せず、別セットとして保持する。
versionは0.1.0だが、`debian/changelog` はUNRELEASEDのまま。署名・公開・pushは行っていない。

## Buildと検査

- 各sourceは `git -c tar.umask=0022 archive <commit>` から別の一時rootへ展開。
- localは `dpkg-buildpackage -us -uc -b`、remoteは `packaging/remote/build-deb.sh`。
- 各local build内で806 test（767成功・39 expected skip）が成功。
- 両回ともlocal/remote専用verifierが成功。
- 展開後にELF、共有library（`.so`）、bytecode/cacheがないことを検査。
- executableはlocalの固定launcher/helper 5本、remote helper 1本のみ。
- commit前のhost全806 test、shell構文、desktop-file-validate、Git空白検査成功。
- SSH GUI証拠のAPT生ログはCRを保持したgzipへ変換し、展開後hash一致と証拠checksumを確認した。

toolchain・両回hash・executable一覧は
`candidate-build-2026-09-12/build-evidence.json` に保存。
local build生ログ2本は同dirの`.log.gz`に保存した。
Python 3.14.4、dpkg 1.23.7ubuntu1、debhelper 13.31ubuntu1、dh-python 7.20260309。

## Cleanupと残件

一時source/build/展開rootは削除し、採用artifactとログだけをホストへ保持した。
VM、host package、実設定、service、key/backupは変更していない。

新candidateは旧セットとhashが異なる。旧candidateのOS lifecycle、実display、SSH GUI、
installed SBOM証拠を新artifactの検証済み根拠として扱わない。
次はこの修正後candidateのOS/実display Gate、残る機能・性能・accessibility Gateを進める。
UNRELEASED解除後の最終artifact反復、署名鍵の明示指定、署名・公開は引き続き残件。
