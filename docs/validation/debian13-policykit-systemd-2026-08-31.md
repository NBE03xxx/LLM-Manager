# Debian 13 PolicyKit / systemd Gate（2026-08-31〜2026-09-01）

## Scope

Debian 13.6 GNOME Liveのactive Wayland sessionで、Gate専用PolicyKit action、root-owned helper、systemd oneshot unitだけを使い、認証success、明示deny、systemd操作、cleanupを確認した。Ollama、OpenCode、LLM-Managerの実target、既存SSH設定は変更していない。

## Gate boundary

- action: `io.github.nbe03xxx.llm-manager.phase4-gate`およびdismiss再試験専用action
- helper: `/usr/local/libexec/llm-manager-phase4-*-gate-helper`
- unit: `llm-manager-phase4-gate.service`
- artifact: `/run/llm-manager-phase4-gate/marker`
- deny rule: `/etc/polkit-1/rules.d/49-llm-manager-debian13-gate-deny.rules`（試験直後に削除）

## Results

| Gate | Result |
|---|---|
| ownership/mode | helper root:root 0755、policy/unit root:root 0644 |
| action discovery | `auth_admin`、active session限定、固定helper pathを確認 |
| success | `pkexec` exit 0、Gate unit `active`、marker作成 |
| dismiss（Live） | success直後だけでなく新規action ID/helper pathでも認証UIなしにexit 0となった |
| dismiss（installed desktop） | password-backed userのactive GNOME sessionで認証dialogをCancelし、`Request dismissed`、exit 126。unit inactive、markerなし |
| explicit deny | user `user`を限定した一時ruleで`Not authorized`、exit 127。unit inactive、markerなし |
| cleanup | Liveでは一時rule、両helper、両action、unit、`/run` artifactを削除した。installed desktopでもdismiss専用helper/action/unit/`/run` artifactを削除し、action不在を確認 |

## Interpretation

GNOME Live userはpasswordless/admin sessionであり、新規`auth_admin` actionでも認証UIを表示せず許可したため、Live imageだけではdismiss UI経路を検証できなかった。そこで同じVMの32 GiB専用diskへDebian 13を通常installし、自動loginを無効にしたpassword-backed userのactive GNOME sessionで再試験した。新規dismiss actionは認証dialogを表示し、Cancelがexit 126へ写像され、Gate unitとmarkerを変更しなかった。これによりDebian 13のsuccess、dismiss、明示deny、固定Gate unit操作、cleanup Gateを完了した。
