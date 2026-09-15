# Phase 6 authentication context candidate build（2026-09-15）

認証コンテキストUI改善を含むcommit
`7f846f5fb1134be7df06490f30a5216ab414ae0d`のtracked sourceのみを、
`git -c tar.umask=0022 archive`で独立した2つの一時treeへ展開した。
localは`dpkg-buildpackage -us -uc -b`、remoteは
`packaging/remote/build-deb.sh`で各2回buildし、各artifactのbyte列が一致した。

| artifact | SHA-256 |
|---|---|
| `llm-manager_0.1.0_all.deb` | `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2` |

採用candidateは`/tmp/llm-manager-candidate-7f846f5-20260915/`へ0644で保持する。
versionは0.1.0、distributionは`UNRELEASED`のままであり公開artifactではない。

## 検査

- 各local build内806 test成功（767成功・39 expected skip）。
- local/remote専用package verifierを両runと採用copyへ実行し成功。
- local package内に3つの`LOCAL` PolicyKit文言、`REMOTE SSH login`、
  `REMOTE sudo`が収録されていることを展開後に確認。
- package内の実行fileはlocal固定launcher/helper 5本とremote helper 1本だけ。
  ELF/shared object、`__pycache__`、`.pyc`は存在しない。
- build hostはLinux 7.0.0-31-generic x86_64、dpkg 1.23.7ubuntu1、
  debhelper 13.31ubuntu1、dh-python 7.20260309、Python 3.14.3。

このcandidateに対するDebian通常desktopの認証表示目視Gateは別記録で行う。
最終release時は`UNRELEASED`解除後の同一commitから再build・再検証する。
