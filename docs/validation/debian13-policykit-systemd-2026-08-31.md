# Debian 13 PolicyKit / systemd Gate（2026-08-31）

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
| dismiss | 未成立。success直後だけでなく新規action ID/helper pathでも認証UIなしにexit 0となった |
| explicit deny | user `user`を限定した一時ruleで`Not authorized`、exit 127。unit inactive、markerなし |
| cleanup | 一時rule、両helper、両action、unit、`/run` artifactを削除し、両action不在を確認 |

## Interpretation

GNOME Live userはpasswordless/admin sessionであり、新規`auth_admin` actionでも認証UIを表示せず許可した。このためdismiss UI経路はこのLive imageでは再現できない。Ubuntu 26.04 installed desktopではdismiss exit 126を確認済みだが、Debian 13については通常installされたpassword-backed desktop sessionでのdismiss確認を未完了Gateとして残す。success、明示deny、固定Gate unit操作、cleanupのDebian 13差異は確認済みである。
