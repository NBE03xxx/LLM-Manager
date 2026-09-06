# Phase 6 root restore fixed source/service validation — 2026-09-06

現在・次ともPhase 6。固定source parent openerと`RootRestoreOllamaService`を追加した。実command実行を持つadapterの検証ロジックをcoordinatorに接続できるようにしたが、production dispatchと実service Gateは未実施。

## Source境界

`open_production_source_parent()`は固定drop-in parentを`/`からdir_fd/O_NOFOLLOWで辿る。全ancestorのroot ownershipと非group/other writableを確認し、最終directoryはroot:root・非writableを要求する。通常のsystemd drop-in directoryはprivate key/storeと違って0755も許可する。作成や権限修復は行わない。

## Service/API検証

coordinatorのservice portへ復元内容（または元不在を表すNone）を渡す。専用adapterは対応literal Environmentだけを解析し、未知directive/duplicate/escape/不明な形式は再起動前にFalseを返す。これはsystemd一般parserではない。

固定`/usr/bin/systemctl daemon-reload`、`restart ollama.service`、固定propertyの`show`を実行する。loaded/active/running、Environment propertyの存在、一意性、復元した設定との一致を要求する。共通SubprocessRunnerのstdout/stderr上限1 MiB、cancel/deadlineを使用し、変更commandは最大30秒、showは3秒で停止する。

API endpointは観測したOLLAMA_HOSTの127.0.0.1/localhost/[::1]＋有効portだけを許し、localhostは127.0.0.1へ固定して名前解決しない。OLLAMA_HOST未指定時は127.0.0.1:11434。external/wildcard/credential/path付きの値はHTTP前に拒否する。

固定`/usr/bin/curl`の最初のoptionを`--disable`とし、curlrcを無効化。proxyを使わず、HTTPだけ、redirect追跡なし、HTTP status 200を必須とする。`/api/version`は基準版0.33.2、`/api/tags`はmodels listを確認する。APIごとにcurl timeout 3秒、process deadline 4秒。いずれかの失敗/不正形式で成功を返さず、自動restart retryも行わない。

coordinatorはFalseをservice_validation_failed、例外/cancelをunknownとして保存する。設定本文、Environment原文、API本文をaudit/resultへ記録しない。実Ollama起動直後のAPI readinessや他形式との互換性はOS Gateで確認が必要。

## 検証

新規11 test（service 10＋coordinator統合1）を追加。固定argv、loopback/IPv6/port、external拒否、effective environment/service state、未知構文、redirect/HTTP error/JSON/version/schema、全5 command段階でのtimeout/nonzero/cancel、元不在の検証を確認した。coordinator統合は実file復元＋本serviceロジック＋模擬command結果を使う。実systemctl/curlを呼び出した証拠ではない。

全639 test完走（616成功・23 skip）。compileall、packaging shell syntax、desktop validation、diff check成功。実設定・service・API・VM・既存backup/key・SSHへの操作なし。全変更は未コミットで保持。

次もPhase 6。trusted review producerの認可境界、privileged composition/CLI、全製品mutatorの対象lock統合を整備し、その後PolicyKit/OS/Qt Gateを行う。保存済みdeb/SBOMは現codeより古いartifactの証拠である。root route availabilityは非公開を維持する。
