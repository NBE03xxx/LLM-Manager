# Phase 5 ControlMaster Integration Validation — 2026-09-02

## Scope

PySide6 Hosts/Diagnose workerから、公開鍵・Agentだけでは認証できないOpenSSH aliasを外部terminalの一時ControlMasterへ安全に接続するproduction composition境界を実装した。password、秘密鍵、SSH設定、known_hosts、remote host、Ollama、OpenCode、systemdは変更・保存していない。

## Contract

- 直接のstrict known_hosts probeが`host_identity_unverified`の場合だけ対話認証へfallbackする。config failure、timeout、cancelではterminalを起動しない。
- masterは選択済みOpenSSH aliasをそのまま使い、User、Port、IdentityFile、Agent、ProxyJumpをsystem OpenSSHへ委譲する。
- `StrictHostKeyChecking=yes`、`UpdateHostKeys=no`でknown_hostsを変更せず、password promptは外部terminal/OpenSSHだけが扱う。
- user専用0700 runtime directoryへランダムsocketと0600 debug logを作り、logはowner、regular file、非symlink、mode、1 MiB上限をdescriptorで検証する。
- control check成功かつmaster接続の一意なSHA-256 server host-key fingerprintを検証できた場合だけ、同じsocketとfingerprintをread-only診断へ渡す。
- 診断成功、失敗、cancelではcontrol `exit`し、debug logはidentity確認直後に削除する。identity検証失敗時もmasterを閉じる。

## Results

fake process/terminal境界でalias argv分離、strict option、password非保持、private bounded fingerprint log、曖昧/public log拒否、認証fallback条件、socket/fingerprint binding、診断失敗時closeを確認した。関連focused testは34件成功した。

実hostへの対話認証とGUI read-only diagnosis positive Gateは未実施であり、後続Phase 5 Gateとする。
