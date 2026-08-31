# Debian 13 desktop packaging Gate（2026-08-31）

## Scope

Debian 13.6 GNOME Liveのdisposable VMで、stock runtime差異、local/remote deb依存解決、Secret Service、PolicyKit action、privileged wrapper、remote helper lifecycleを確認した。Ollama、OpenCode、実SSH設定、既存systemd unitは変更していない。

## Environment

| Component | Observed |
|---|---|
| OS | Debian 13 `trixie` GNOME Live / Wayland |
| Python | 3.13.5 |
| cryptography | 43.0.0-3+deb13u1 |
| SecretStorage | 3.3.3-3 |
| PolicyKit | `polkitd` / `pkexec` 126-2。`policykit-1` candidateなし |
| OpenSSH client | Debian package 1:10.0p1-7+deb13u4 |

## Results

- 現行の旧dependency（Python 3.14、cryptography 46.0.5、SecretStorage 3.5）ではlocal/remote debのAPT simulationがexit 100となり、正式対象Debian 13 stockへinstallできなかった。
- Gate専用controlだけをstock下限へ変更したlocal debをinstallし、helper/metadata/PolicyKit actionのroot ownershipと0755/0644 modeを確認した。
- AES-GCMとproject backup cryptoをimportし、Secret Service default collectionへGate専用keyをcreate/reload/deleteした。silent plaintext fallbackは使っていない。
- current sourceをPython 3.13.5で実行し、全338単体テストが成功した。転送tarのumaskで実行fileが一時0775になったため、Git正本の0755へ補正して再実行したもので、runtime failureではない。
- local packageと別のremote helper debを共存installし、unknown commandが`invalid_remote_command`、exit 1でfail closedとなることを確認した。
- 初回remote wrapperはroot実行時にdpkg管理外の`__pycache__`を生成し、remove後にprivate runtimeを残した。import前に`sys.dont_write_bytecode = True`を設定する修正版ではcache生成なし、remove後のhelper/private runtime完全消去、purge、reinstallを確認した。
- 正式controlへsupported minimumを反映してbuild・artifact検証したlocal/remote debは、同じDebian 13 stock環境のAPT simulationでいずれもexit 0となった。localは`python3-cryptography (>= 43.0.0)`と`python3-secretstorage (>= 3.3.3)`、remoteは`python3 (>= 3.13)`と`python3-cryptography (>= 43.0.0)`を宣言し、Gate専用revisionから正式versionへのdowngrade planを依存競合なしで解決した。

## Decision

Python 3.14.4は初期検証baselineとして維持する。正式対象Debian 13をstock packageだけでinstall可能にするsupported minimumはPython 3.13、cryptography 43.0.0、SecretStorage 3.3.3とする。local/remote privileged wrapperはpackage管理外bytecodeを生成しない。

## Remaining boundary

このGateはLive overlayでのpackage/runtime確認である。正式controlを反映したartifactのbuild/verificationとAPT simulationまで完了した。Ollama/OpenCodeへの実Applyは行っていない。
