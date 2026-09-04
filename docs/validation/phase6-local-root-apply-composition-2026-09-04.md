# Phase 6 local root Apply composition (2026-09-04)

## Scope

local root Ollama ChangeSetを既存PolicyKit Safe Apply coreへ渡すproduction task factoryを構成した。実PolicyKit、systemd、Ollama設定は起動・変更していない。`local_root` availabilityは引き続き無効である。

## Boundary

- local hostかつ全changeがroot専用であることをtask生成前に検証する。
- private user state、Secret Service暗号化backup、固定`/etc/systemd/system` allowlist、user-owned helper staging、`/usr/bin/pkexec`だけのrunnerを束ねる。
- helper package/version/protocol/owner/modeをbackup前とhelper起動直前に再検証する。
- `ApprovedHelperRequestFactory`、PolicyKit invoker、runtime validator、immutable journal、redacted audit、rollback requestを同一coordinatorへ渡す。
- local user/root routingは全changeのprivilegeが一致するときだけ行い、混在を拒否する。

privileged coordinatorで未使用だったaudit portも接続し、approved、backup verified/failed、commit、rollback/recovery-requiredを記録する。commit前audit failureは成功と推測せずrollbackへ進む。

## Validation

sandbox compositionはfake backup/helper backendだけを使い、COMMITTED、private journal/audit、helper二重readiness、local/root/mixed route拒否を確認した。既存privileged coordinator、staging→CLI→receipt→backend integration、production entrypointを含むfocused 18件が成功した。

production `main()`はlocal user/root routing factoryを注入するが、availabilityは`local_user`だけのためroot実行buttonは無効のままである。次はUbuntu 26.04/PySide6 sandbox GUI Resultsでsuccess/rollback/recovery/deny/cancelを検証してから公開可否を判断する。

## Qt Gate status

一時private state、fake backup/helper、root route availabilityだけを使い、Qt workerから実`LocalRootApplyTaskFactory`へ到達してCOMMITTED、audit、journal、helper二重readinessを確認するruntime testを追加した。main hostはPySide6不在のためskipする。既存`ubuntu26.04` VMはrunningだがguest agentが応答せず、lease address `192.168.122.48`のSSHがconnection refusedだったため、このturnでは実行できなかった。VMやsystem policyを変更して到達性を作らず、Gate未完了として`local_root` availabilityを無効のまま維持する。
