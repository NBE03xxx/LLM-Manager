# SSH AI Server Read-only Integration Validation — 2026-08-29

## Scope

`yoshimi@192.168.1.253`へPtyxis上のOpenSSHで対話認証し、一時ControlMaster socket経由でPhase 2 Adapterをread-only統合確認した。パスワードは端末/OpenSSHだけが扱い、LLM-Manager process、引数、ログ、文書には渡していない。sudo、設定変更、service操作、model実行、model downloadは行っていない。

## Environment and result

| Item | Observed result |
|---|---|
| Report | `complete` |
| Host | `ai` |
| OS | Ubuntu 26.04 |
| Kernel | Linux 7.0.0-30-generic、x86_64 |
| CPU | AMD Ryzen 7 9700X、16 logical / 8 physical cores |
| RAM | 63,580,004,352 bytes total、61,562,474,496 bytes available at observation |
| GPU | AMD Radeon RX 9060 XT 2基 + AMD Radeon Graphics 1基をPCI検出 |
| GPU telemetry | `rocm-smi` 4.0.0 / ROCM-SMI-LIB 7.8.0で取得成功。外部GPUは各17,095,983,104 bytes、内蔵GPUは2,147,483,648 bytes |
| Ollama | 0.33.2、systemd active、loopback API `ok` |
| Ollama models | installed 16、loaded 0。model名は本記録に保存しない |
| OpenCode | 未検出 |
| SSH identity | known_hostsにED25519/RSA/ECDSA SHA256 fingerprintを確認（値は本記録では非表示） |
| Session cleanup | 診断後にOpenSSH control `exit`を送信済み |

## Findings and changes driven by validation

1. 公開鍵認証なしでも、Ptyxis内でパスワードをOpenSSHへ直接入力し、一時ControlMasterを確立できた。
2. remote localeが日本語の場合、`lscpu -J`のfield名が翻訳されparserが失敗した。OpenSshHostAdapterが許可済みcommandを`env LC_ALL=C LANG=C`で実行するよう修正した。
3. `rocm-smi --json`はlow-power warningと`libdrm_amdgpu.so`不足警告があってもJSONを返した。警告と欠損temperatureを許容し、VRAM、使用量、使用率、temperature、driver、GFX architectureを構造化するparserを追加した。
4. 対話認証sessionは診断後に明示的に閉じた。passwordや秘密情報はアプリへ返さない。

## Remaining gates

- ControlMaster session作成・監視・終了のGUI統合
- terminal終了、認証失敗、timeout、socket消失、SSH切断のfault injection
- SSH sudo用の外部端末 + 限定remote helper protocol
- Debian 13
