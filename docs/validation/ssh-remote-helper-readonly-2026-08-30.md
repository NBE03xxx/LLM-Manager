# SSH Remote Helper Read-only Validation — 2026-08-30

## Scope

Phase 4の実OpenSSH transportとremote helper compatibility境界について、既知の2台へproduction `OpenSshHostAdapter`、system `ssh`、`BatchMode=yes`を使ってread-only probeを実行した。固定helper/metadata pathの`stat`だけを行い、remote staging、file upload、sudo、helper起動、backup、retention、deletion、journal取得は行っていない。Ollama、OpenCode、systemd、SSH設定を変更していない。

## Result

| Target | Compatibility status | Reason |
|---|---|---|
| SSH alias `development` | `missing` | `helper_not_installed` |
| `yoshimi@192.168.1.253` | `missing` | `helper_not_installed` |

両ホストとも次の固定pathだけを確認した。

- `/usr/bin/llm-manager-remote-helper`
- `/usr/share/llm-manager-remote-helper/helper-metadata.json`

helperまたはmetadata欠落時は2件の`stat`後に停止し、metadata内容のreadへ進まない。root apply、remote recovery copy、retention/deletion、root journal操作はfail-closedのままである。

## Remaining Gate

remote helper debを管理者が事前導入したdisposable SSH先で、root ownership/mode/content hash/package/protocolのpositive compatibility、user staging、外部端末またはpasswordless sudo、暗号化backup、result回収、切断後照合を検証する。LLM-Manager自身は実運用ホストへhelperをinstallしない。
