# Phase 5 local restore explicit refresh validation (2026-09-04)

## Decision

local userの単一OpenCode config restoreは、明示inventory refreshまで含むproduction公開条件を満たす。`LocalUserRestoreTaskFactory.task`だけをproduction `main()`へ接続する。local root、SSH user、SSH root restoreは接続しない。

## End-to-end boundary

sandboxの一時config/stateへ実`LocalBackupStore`、terminal journal、`LocalBackupInventoryTaskFactory`、`LocalUserRestoreTaskFactory`、Qt workerを接続した。

1. 明示refreshでbackup/journal inventoryを取得する。
2. backup選択からmetadata-only previewを生成し、exact approvalを作る。
3. 単一worker内でstrict preflightとrestoreを実行する。
4. COMMITTED result後も画面上の旧inventoryを自動で書き換えず、approval/runを消費する。
5. 次の明示refreshでだけstrict execution storeを再読込し、`restore: committed`とattention falseを表示する。

refresh結果は次のmutation authorityではない。新しいrestoreには新しいpreviewとapprovalが必要である。

## Ubuntu Qt Gate

Ubuntu 26.04、PySide6 6.10.2、Qt offscreenで1件が0.143秒で成功した。復元内容、完了直後の旧inventory維持、run無効、明示refresh後のCOMMITTED/attention falseを確認した。artifact SHA-256は`9f84f09a6018d1d0b4d7442a032ce2deeca2a1b5a8b78ae02b96769a424f929c`で一致し、VMの一時Gate directoryは削除した。

実`~/.config/opencode`、Ollama、systemd、SSH設定は変更していない。

production接続後のmain host全449件は0.559秒で成功し、PySide6依存13件と明示Secret Service Gate 2件の計15件をskipした。compileall、local/remote packaging shell構文、`git diff --check`も成功した。

## Production publication

production `main()`はlocal user restore factoryのworker taskをQtへ渡す。remote hostはpreview/inventory段階からfail closedであり、factoryもlocal host以外をstate/Secret Service access前に拒否する。単一target、短命approval、Secret Service、attempt/audit、immutable result、host lock、strict result表示の制約は変更しない。

## Next

Phase 5の残存restore範囲とBackup/Rollback画面全体をclosure auditし、local root・SSH経路をMVP内で進めるかfail-closed残存として明記する。
