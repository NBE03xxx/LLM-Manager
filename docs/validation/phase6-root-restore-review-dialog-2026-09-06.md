# Phase 6 root restore review consent dialog — 2026-09-06

## 実装

`RootRestoreReviewSession`と`RootRestoreReviewDialog`を追加。専用clientでpreviewを取得し、host/UID/backup ID/固定target/現在とbackupの存在・hash・mode・UID/GID/期限/preview hashをplain textで表示する。内容確認のcheckboxは初期未選択。明示同意後だけレビュー保存ボタンを有効にする。

同意は表示selectionのhashへ束縛する。checkbox解除、selection変更、期限切れ・clock逆行、失敗で保存不可となる。保存task取得時に一度だけrequest/approval IDを作り、その時点で重複送信を抑止。receipt一致時だけsavedとなり、画面は「設定は復元していません」と表示する。失敗やclose後の遅延成功を成功として受け付けず、同じdialogでpreview/approveを再送しない。

QtTaskRunnerを使用し、GUI threadで認証やprocess待機をしない。window close、閉じるボタン、Escapeはworkerへcancelを伝え、finishedまでdialogを保持する。cancel非協力区間でもevent loopを動かし、強制終了しない。英日文言、折返し同意説明、accessible name/description、default保存ボタンの無効化を追加した。

production composition関数は実host IDと通常UIDを確認して専用client/session/dialogを構築できるが、通常メニューへは登録していない。既存local user restore画面・root mutation availabilityは変更していない。新しいroot実行routeを公開するものではない。

## 検証

新規13 test（純粋session 6、runtime不在境界1、Qt runtime 6）。host全683 test: 654成功・29 skip。compileall、local/remote packaging shell syntax、desktop-file-validate、git diff --check成功。

Ubuntu 26.04 VMは開始時shut off、guest agentでIP 192.168.122.48を再取得。既存PySide6 6.10.2を使用し、通常userでoffscreen関連22 testを実行、21成功・1 expected skip（runtime不在境界）。metadata/同意/単発保存、期限解除、失敗伏字、close/Escape終了待機、480 px幅の折返し、300 ms cancel非協力save中の10 ms eventを10回以上処理することを検証した。Qt command backendはfixtureで、実PolicyKit認証ではない。client→実CLI→一時root store往復testも同じartifactで成功した。

最終artifact SHA-256: `1a2aee6adf764d5efa3102451c1f5d14226550269d9a02ba29c9cdc940178374`。host作成物とVM受信物の一致を確認した。転送は既存鍵・known_hostsを用いた明示`ssh -F /dev/null`のGate経路であり、production system SSHの検証根拠にはしない。

packageの追加・更新なし、実Ollama/OpenCode設定・service・SSH設定変更なし。今回だけのVM一時directoryとhost転送archiveを削除し、Ubuntuを停止へ戻した。Debianは起動していない。全変更は未コミット。

## 残件

次もPhase 6。実PolicyKit認証/installed debで専用review entryを検証し、root backupの選択導線と通常GUI menu公開を判断する。実display/screen readerとDebian runtimeは今回未検証。root復元の専用実行認可/CLI、全mutatorの同一target lock、明示provisioning、OS Gateは引き続き未完了。保存済みdeb/SBOMは今回の変更に対するartifact証拠ではない。
