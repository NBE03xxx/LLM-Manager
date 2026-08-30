# PolicyKit Desktop Validation — 2026-08-30

## Scope

Phase 4のlocal privileged helper境界について、GNOME desktop sessionでPolicyKit authorityと必要CLIのavailabilityをread-only確認した。`pkexec`、認証prompt、LLM-Manager helper、systemd操作は起動していない。PolicyKit action、Ollama、OpenCode、SSH先を変更していない。

## Environment and result

| Item | Observed result |
|---|---|
| Desktop/session | GNOME、Wayland |
| `/usr/bin/pkexec` | 導入済み |
| `/usr/bin/pkaction` | 導入済み |
| `/usr/bin/pkcheck` | 導入済み |
| PolicyKit authority | sandbox外read-only `pkaction`で到達可能 |
| LLM-Manager action | 未登録 |
| `/usr/bin/llm-manager-helper` | 未install |
| Authentication prompt | 未起動 |
| Privileged/systemd mutation | なし |

## Assessment

これはdeb未install状態のnegative availability Gateである。対象actionが存在しないことをauthorityから確認でき、実装境界では`pkexec` exit 127をstable `helper_launch_failed`として扱う。

PolicyKit actionとroot-owned helperの実install、active desktop sessionでの認証成功・dismiss・deny、実systemd操作はdisposable OS上のdeb install Gateまで未完了とする。通常の開発PCでは実helperを起動しない。
