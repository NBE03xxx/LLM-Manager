# Phase 6 local root planning boundary (2026-09-04)

## Scope

local root production Apply監査の最初のsliceとして、GUIからPolicyKitを起動する前に必要なOllama専用ChangeSet生成境界を追加した。実Ollama設定、systemd、PolicyKit、backupは変更していない。

## Result

`BuildSelectedOllamaChangePlan`はplan/report hashと期限、選択ID、actionable/root/`ollama.systemd` target、host identityをI/O前または直前に再検証する。さらに互換local helperをread-onlyで再probeし、固定`/etc/systemd/system/ollama.service.d/90-llm-manager.conf`だけをstatする。symlinkを拒否し、既存時だけbounded strict UTF-8 readを行ってbefore hash付きChangeSetを生成する。

focused 4件で既存drop-in、未作成drop-in、host変更、helper unavailable、symlink、非root selectionを検証した。失敗時にPolicyKit、backup、mutationへ進む経路は存在しない。

## Remaining boundary

production診断compositionへのlocal helper probe、OpenCode/Ollamaを選択targetで分岐するGUI planning factory、local root Apply task factory、PolicyKit sandbox GUI Results Gateの順に接続する。これらが揃うまで`local_root` availabilityはfail closedを維持する。

