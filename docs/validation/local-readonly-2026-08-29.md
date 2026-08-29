# Local Read-only Integration Validation — 2026-08-29

## Scope

Phase 2 AdapterをローカルPCへread-onlyで接続した。sudo、設定変更、service restart、model実行、model downloadは行っていない。credential値、設定本文、base URL、model名は本記録に保存しない。

## Environment and result

| Item | Observed result |
|---|---|
| Report | `complete` |
| OS | Ubuntu 26.04.1 LTS |
| Kernel | Linux 7.0.0-30-generic、x86_64 |
| CPU | AMD Ryzen AI 7 PRO 350、16 logical / 8 physical cores |
| RAM | 28,504,010,752 bytes total |
| Root filesystem | 864,253,648,896 bytes total、714,260,643,840 bytes free |
| GPU | AMD Radeon 840M / 860M、PCI検出成功。専用VRAM値は取得不能のため推測せず `None` |
| Ollama | 0.33.2、systemd active/running/enabled、loopback API `ok` |
| Ollama models | installed 0、loaded 0 |
| OpenCode | 1.18.25、JSONC parse warning 0 |
| OpenCode schema | provider 2、model 6、base URL 2、Ollama互換接続を検出 |
| OpenCode settings | context/compaction関連11、timeout関連0 |

## Findings and changes driven by validation

1. Ollama CLI version照会は短いtimeoutを超える場合があった。`GET /api/version`を第一source、CLIをfallbackへ変更した。
2. OpenCodeの実設定は複数provider schemaだった。active値を推測せず、provider/model/base URL一覧を保持するmodelへ拡張した。
3. OpenCode binaryはユーザー専用directoryにあった。任意PATH探索へ依存せず、検証済み絶対pathをAdapterへ注入できる契約にした。
4. AMD iGPUの専用VRAMはPCI情報だけでは確定できないため、現段階ではunknownのままとした。

## Remaining gates

- Debian 13 local
- OpenSSH接続先
- SSH host-key fingerprint取得とhost identity固定
- AMD ROCm/runtime memory詳細（対応toolが存在する環境のみ）
