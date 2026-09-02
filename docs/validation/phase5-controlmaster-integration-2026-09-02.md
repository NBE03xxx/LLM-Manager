# Phase 5 ControlMaster Integration Validation — 2026-09-02

## Scope

PySide6 Hosts/Diagnose workerから、公開鍵・Agentだけでは認証できないOpenSSH aliasを外部terminalの一時ControlMasterへ安全に接続するproduction composition境界を実装した。password、秘密鍵、SSH設定、known_hosts、remote host、Ollama、OpenCode、systemdは変更・保存していない。

## Contract

- 直接のstrict known_hosts probeがidentityを検証し、認証だけ未完了と判定した場合だけ対話認証へfallbackする。config failure、timeout、cancelではterminalを起動しない。
- 直接probeで一意なSHA-256 fingerprintとOpenSSHのknown-host一致を確認でき、認証だけ未完了の場合に限ってfallbackする。host-key変更や未知keyではterminalを起動しない。
- masterは選択済みOpenSSH aliasをそのまま使い、User、Port、IdentityFile、Agent、ProxyJumpをsystem OpenSSHへ委譲する。
- `StrictHostKeyChecking=yes`、`UpdateHostKeys=no`でknown_hostsを変更せず、password promptは外部terminal/OpenSSHだけが扱う。
- user専用0700 runtime directoryへランダムsocketを作り、control check成功後だけ事前検証済みfingerprintと同じsocketをread-only診断へ渡す。
- 診断成功、失敗、cancelではcontrol `exit`する。

## Results

fake process/terminal境界でalias argv分離、strict option、password非保持、known-host一致、認証だけ未完了の判別、認証fallback条件、socket/fingerprint binding、診断失敗時closeを確認した。

既知alias `llm-manager-gate`で外部Ptyxisから実ControlMasterを確立し、事前検証したfingerprintと一時socketをproduction `OpenSshHostAdapter`へ渡した。read-only diagnosisは`complete`、host ID一致、fingerprint binding成功、failed probe 0となった。control `exit`後にsocket/file artifactが0であることを確認した。公開鍵認証が利用されたためpassword promptは発生していない。SSH設定、remote state、Ollama、OpenCode、systemdは変更していない。

実Gateにより、OpenSSH stderrがCRLFであること、およびPtyxis側からapplication作成済み`-E` logへ依存できないことを確認した。identity境界をCRLF対応とし、terminal共有log方式を廃止して、terminal起動前のstrict known-host一致へfingerprintを束縛した。
