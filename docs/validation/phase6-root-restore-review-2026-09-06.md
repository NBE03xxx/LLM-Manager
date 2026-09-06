# Phase 6 root restore review producer — 2026-09-06

`ProduceRootRestoreReview`を追加した。production未接続の部品であり、専用PolicyKit認可の完了を意味しない。

## レビューの照合

previewはtargetの排他lock下でroot-owned originを読み、元host、現在の対象、復号したbackup、originと対象の再読込を確認する。元状態と同一なら拒否する。設定本文は返さず、選択したoriginのsnapshot hashとpreview hashを生成する。inventory hashは全backup一覧ではなく選択originのsnapshotを表す。

approveはcaller UID/hostを独立に取得して専用requestをdecodeし、同じ選択内容をroot側で再計算する。全request一致、5分期限、cancelを確認して不変reviewを保存する。request ID/approval IDは相関用であり、hashやID自体を認可の証明にはしない。保存後は既存preflightがorigin/target/期限/未実行を再検証する。

`resolve_restore_caller`は実効UID 0と厳密な非root PKEXEC_UIDを要求し、hostは既存local形式に合わせてlocal:hostnameとする。これは将来の専用PolicyKit entryから使うresolverであり、環境変数だけでPolicyKit認証を実装したものではない。既存Apply用action/helperにはdispatchを追加していない。専用action、entrypointの環境境界、GUIでの内容確認と同意の接続は未完了。

## Origin契約

元の承認済みApply requestのmanifest hashをsource_manifest_hashとしてroot backup originとAEAD contextへ束縛し、restore verifierでも照合する。originのinspectは安全な読取りだけで、既存readのexpected hash必須条件は緩和しない。

これは未公開開発schemaの変更である。source_manifest_hashのない以前の開発record/envelopeは拒否される。既存backupの自動移行やhash補完は行わず、実環境backup/keyは変更していない。公開前に最終schemaと移行方針を確定する必要がある。

## 検証

新規14 test。実一時file/key/origin/storeを使ったpreview→review保存→preflight成功、再hash済み要求改変、manifestのAEAD改変、preview後と読取り中の対象変更、payload変更、host/UID不一致、no-op、期限、cancel、重複保存、旧schema拒否を確認した。失敗時のreview不在と成功時の対象不変も確認した。

全653 test（630成功・23 skip）、compileall、packaging shell syntax、desktop-file-validate、git diff --check成功。skipは既存の環境依存test。実設定・service・VM・SSHの操作なし。変更は未コミット。

次もPhase 6。専用PolicyKit認可/CLI compositionとGUI consent、全製品mutatorの対象lock統合、その後のPolicyKit/OS/Qt Gateが必要。root routeは非公開を維持し、保存済みdeb/SBOMを今回のコードの検証証拠にはしない。
