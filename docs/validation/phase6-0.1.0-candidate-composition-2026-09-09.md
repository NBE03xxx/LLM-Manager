# Phase 6 `0.1.0` candidate composition

## 結果

version freeze commit `4722cfa5238af507deee0831bdf8a0cbe517fe99`のtracked sourceから、local debとremote helper debを独立に2回ずbuildした。両artifactとも各2回のbyte列が一致し、専用verifierが成功した。

| Artifact | Package / version / arch | SHA-256 |
|---|---|---|
| `llm-manager_0.1.0_all.deb` | `llm-manager` / `0.1.0` / `all` | `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `llm-manager-remote-helper` / `0.1.0` / `all` | `45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1` |

採用copyは`/tmp/llm-manager-release-candidate-4722cfa/`に0644で保持した。これはOS lifecycle/SBOM Gate用のcandidateであり、`debian/changelog` が`UNRELEASED`のため公開artifactではない。

## Build sourceとtoolchain

- OS/kernel: Linux 7.0.0-31-generic x86_64
- Python: 3.14.4
- dpkg/dpkg-deb: 1.23.7
- debhelper: 13.31ubuntu1
- dh-python: 7.20260309
- python3-setuptools: 78.1.1-0.1build1
- local build: `dpkg-buildpackage -us -uc -b`
- remote build: `packaging/remote/build-deb.sh`

## Archive modeのnegative Gate

初回の作業copyは単なる`git archive` を使い、Git tarの既定`tar.umask=0002`によりtracked executableが0775になった。build内の全791 testはlauncher/helper/`debian/rules`のmode不一致を5件で拒否し、local debは生成されなかった。初回結果は採用していない。

再実行は`set -eu`を必須とし、`git -c tar.umask=0022 archive`でtracked executableを0755とした。これは`docs/packaging.md`の既存境界と一致する。

## 展開監査

- local executable: `/usr/bin/llm-manager`、`llm-manager-helper`、`llm-manager-restore-review`、`llm-manager-restore-execute`、`llm-manager-restore-setup`の5本、全0755
- remote executable: `/usr/bin/llm-manager-remote-helper`の1本、0755
- ELF/shared object: なし
- `__pycache__` / `*.pyc`: なし
- third-party vendored module: なし
- non-Python asset: package metadata、egg-info、desktop entry、SVG icon、PolicyKit policy、manpage、copyright、notices、SBOMに限定

local/remoteのpackage name/version/architecture/dependency、root owner/mode、isolated launcher、PolicyKit fixed helper、desktop/icon、copyright/notices/SBOMは各verifierで検査済み。

## Cleanupと残件

失敗build root、重複build root、展開監査rootは限定pathから削除し、採用2 artifactだけを保持した。VM、host package、実設定、service、backup/keyは変更していない。

`UNRELEASED`解除とrelease note更新は後続commitになるため、公開用の最終artifact setはそのcommitから再buildする。Ubuntu local candidateのpre-final lifecycle Gateは[別記録](phase6-0.1.0-ubuntu-lifecycle-2026-09-09.md)で完了した。現在・次ともPhase 6。次はこのcandidateを使いDebian lifecycle、resolved-environment SBOM、Qt license reviewのGateを進める。
