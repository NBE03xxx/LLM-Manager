# Phase 5 Local User Apply Composition Sandbox Gate — 2026-09-04

## 結論

local userのOpenCode設定変更に限定したproduction compositionを実装し、一時directoryだけを使うsandbox Gateに成功した。production GUIにはまだ接続せず、実ホームと実OpenCode設定は変更していない。

## 束縛した境界

- local host、non-root change、`$XDG_CONFIG_HOME/opencode`（fallback `~/.config/opencode`）配下だけを許可する。
- SSH host、root change、範囲外target、symlink application rootをtask実行前に拒否する。
- 実行直前にconfig rootを再検証し、private state rootは現在user所有かつgroup/other権限なしでなければ拒否する。新規rootは0700で作る。
- 暗号化backupの場合だけSecret Service backend/key providerを遅延生成し、AES-256-GCMから平文へfallbackしない。
- `LocalBackupStore`、`AtomicFileExecutor`、`FileValidator`、`ProductRuntimeValidator`、`LocalAuditLog`、`LocalOperationJournal`、`SafeApplyCoordinator`を同じ許可rootへ束縛する。
- executorはApply直前にもbefore hash、absolute path、symlink、operation種別を再検証する。

## Sandbox evidence

`LocalUserApplyTaskFactoryTests`で次を確認した。

- encrypted backup、Apply、file validation、commitが成功する。
- backup envelope、hash-chain audit HEAD、terminal operation journalがprivate state rootへ永続化される。
- state rootは0700である。
- remote host、root change、OpenCode root外targetをmutation前に拒否する。
- symlink化されたOpenCode rootと既存0755 state rootを拒否する。

## Ubuntu 26.04 desktop Gate

Ubuntu 26.04 desktop VMのpassword-backed GNOME session、PySide6 6.10.2環境で、`LLM_MANAGER_SECRET_SERVICE_GATE=1`を明示した専用testを実行した。`/tmp`内の一時config/state rootだけを対象に、実Secret Serviceへ一意なGate専用keyを作成し、AES-GCM backup、Apply、validation、commit、暗号文への平文非包含を確認した。終了時には成功・失敗共通の`finally` cleanupで専用keyを削除し、同じattributesの再検索結果が空であることを確認した。1件成功、skipなし、実行時間0.057秒だった。

## 未実施

production GUIへのfactory接続と実OpenCode設定へのApplyは未実施である。次はlocal user routeだけを選択的に有効化し、local root/SSH routeのfail-closed表示を維持する接続設計を行う。
