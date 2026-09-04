# Phase 5 local restore production composition validation (2026-09-04)

## Decision

local userの単一OpenCode config targetに限り、既存restore coreをproduction factoryへ安全にcompositionできる。materialな仕様変更は不要である。GUIの実行controlと実ユーザー設定へのmutationは接続しない。

## Composition boundary

- local host以外をstate/Secret Service access前に拒否する。
- XDG config/stateの絶対application rootと非symlink境界を再検証する。
- metadata-only prepareではSecret Serviceやbackup本文を読まない。
- execution時だけ既存`SecretServiceKeyProvider`とAES-256-GCM cipherを構築する。暗号化backupに平文fallbackはない。
- preview/approval/preflight authorizationの最短expiryと、manifest/allowlist/current targetをmutation直前に再検証する。
- `restore-executions`と`audit`をprivate state root配下で分離し、directory 0700、record 0600とする。
- attempt保存と開始audit成功前にmutationしない。authorizationはattemptで一回消費し、FAILED、attempt-only、UNKNOWNを自動retryしない。
- executorは単一targetだけを許可する。複数targetはfail closedである。

## Sandbox Gate

`LocalUserRestoreTaskFactoryTests` 3件を追加した。暗号化backupのprepareからatomic restore、COMMITTED evidence、audit、0700/0600 metadataを確認した。preflight後の外部変更は内容を保持したまま`stale_restore_target`となり、FAILED evidenceを保存して同じauthorizationの再利用を拒否した。SSH hostはstate作成・鍵provider access前に拒否した。

restore/preflight/execution/inventoryを合わせたfocused 20件が0.023秒で成功した。実`~/.config/opencode`、Ollama、systemd、SSH設定は変更していない。

main hostの全443件は0.508秒で成功し、PySide6依存11件は未導入のためskipした。compileall、local/remote packaging shell構文、`git diff --check`も成功した。

既存`ubuntu26.04` VMは稼働中だがQEMU guest agentが応答せず、DHCP leaseの`192.168.122.48`ではSSH serviceがlistenしていなかった。このためdesktop session内のSecret Service Gateは今回未実施であり、sandbox結果を実desktop evidenceとは扱わない。

## Next

GUI execution controlはまだ追加しない。次はGate専用一時XDG rootと既存Ubuntu desktop VMのSecret Serviceを使い、production factoryの暗号化restore compositionを実desktopで検証する。
