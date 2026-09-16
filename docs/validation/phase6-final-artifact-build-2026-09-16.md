# Phase 6 final artifact reproducible build (2026-09-16)

## Outcome

final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`のtracked sourceだけを
`git -c tar.umask=0022 archive`で独立した2つのtreeへ展開し、local binary debを
`dpkg-buildpackage -us -uc -b`、remote helper debを`packaging/remote/build-deb.sh`で各2回buildした。
両runのartifact、`.buildinfo`、`.changes`はbyte完全一致した。

| artifact | SHA-256 | size |
| --- | --- | ---: |
| `llm-manager_0.1.0_all.deb` | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` | 151,784 bytes |
| `llm-manager-remote-helper_0.1.0_all.deb` | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4` | 137,958 bytes |
| `llm-manager-0.1.0.tar.gz` | `6d569199110bdc155a14c0a6222353ccc92380b63b20cfebff083ace1c91fe18` | 37,075,955 bytes |

採用artifactとsource archiveは
`/tmp/llm-manager-final-5b7d4de-20260916/artifacts/`へmode 0644で保持する。
pre-final candidateとはdirectoryとhashを分離し、後続Gateで混用しない。

## Reproducibility and source boundary

- build開始時の`HEAD`と`origin/main`は上記commitで一致し、worktreeはcleanだった。
- 独立2回のsource tar SHA-256はともに
  `9306b61d23ecd02522a07405dcff08a317f5568bace68d8f32d72e97fbab099d`。
- release source archiveのfile一覧は`git ls-files`の1,575 fileと完全一致し、未追跡file、`.git`、
  build生成物は混入しない。
- local `.buildinfo` SHA-256は両runとも
  `13aab491c9a48b36bdee2c89ee29a8141c22ea16b88fe0a1e5e16f2d9f2de168`。
- local `.changes` SHA-256は両runとも
  `6b94da3742561aa557442101710bd31c3e9d8efafb34b3cee0c4e9b72ae2a4f7`。

## Tests and package audit

- 各local build内806 test: 767 pass、39 expected skip。
- local verifierを両runへ実行: 成功。
- remote verifierを両runへ実行: 成功。
- package identity: `llm-manager 0.1.0 all`、`llm-manager-remote-helper 0.1.0 all`。
- Maintainer: `NBE03xxx <NBE03247@nifty.com>`。
- local dependency、remote dependency、isolated launcher、PolicyKit固定path、desktop/icon、
  helper metadata、copyright、third-party notices、直接依存SBOM、root owner/modeをverifierで確認。
- 展開後の実行fileはlocalの固定launcher/helper 5本とremote helper 1本だけ。
- ELF、shared object、`__pycache__`、`.pyc`、third-party vendored moduleは存在しない。
- package contentsとfile type一覧を採用artifactから再採取した。

実行時に表示された`Failed to create stream fd: Operation not permitted`はテスト環境のログ出力先に
関する既知の非致命的warningであり、各buildとverifierのexit statusは0、unit testも成功した。

## Build host and toolchain

- host: Linux `7.0.0-31-generic` x86_64
- `dpkg-dev`: `1.23.7ubuntu1`
- `debhelper`: `13.31ubuntu1`
- `dh-python`: `7.20260309`
- `python3` package: `3.14.3-0ubuntu2`
- runtime: Python `3.14.4`

## Remaining boundary

これはfinal sourceからのartifact identityとstatic package compositionを確定したGateである。
Ubuntu 26.04／Debian 13のresolved-environment SBOM、license review、OS lifecycle、通常GUI、SSH、
security corpus、release `SHA256SUMS`、OpenPGP署名、signed tag、GitHub Release公開後再検証は未実施。
署名、tag、公開には別の明示承認が必要である。
