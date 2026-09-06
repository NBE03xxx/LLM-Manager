# Phase 6 dedicated root restore review CLI — 2026-09-06

専用CLI `root_restore_review_cli`とdeb用isolated launcherを追加した。既存Apply helperにdispatchを追加せず、独立した`review-system-restore` PolicyKit actionを定義した。active sessionはauth_admin、inactive/anyはno、認証保持指定なし。実PolicyKit認証は未実施。

## 境界

CLIはpreview backup-idとapprove expected-hash canonical-request-hexだけを受け付ける。approveは最大16 KiBの専用requestをlowercase hex argvで受け取り、長さ・形式をroot storeアクセス前に検査する。入力はmetadataのみで設定本文を含めない。stdinの無期限待機やuser-owned staging pathは導入しない。UID/hostはprivileged resolverから取得し、固定source/backup/key/execution openerをExitStackで束ねる。部分失敗を含め全fdを閉じる。owner override、directory/key作成、任意path、実行subcommandはない。

レビュー内容の再計算・期限・AEAD・immutable保存は前sliceのproducerを使う。成功はpreviewまたはreview_savedを表し、復元完了や実行認可を表さない。未知例外は固定error codeに変換し、tracebackや例外本文を返さない。既知エラーもcodeだけを返す。

このactionはroot-owned backup閲覧とレビュー保存に限る。将来の設定変更entryには別の専用認可が必要であり、review_savedやhashをその代わりにしない。GUIで表示した内容への同意とrequest生成・呼出しは未接続。実行coordinatorも未接続でroot mutation routeは非公開を維持する。

## 配布・検証

local deb install manifest、manpage、verify-deb.shへ新launcherを追加した。verifierはroot/root 0755、isolated shebang、entry module、PolicyKit固定pathを確認する。保存済みdeb/SBOMは本変更前のartifactであり今回の配布検証証拠ではない。

新規8 test。実一時backup/key/storeを使うCLI preview→approve、拒否入力でstore未アクセス、nonroot拒否、未知例外の伏字化、execute/path option拒否、部分・正常compositionのfd close、独立PolicyKit actionを検証。既存配布ファイル一覧testを更新した。

全661 test（638成功・23 skip）成功。compileall、packaging shell syntax、desktop-file-validate、git diff --check成功。実PolicyKit/installed deb/GUI/OS Gateは未実施。実設定・service・VM・SSHを変更していない。全変更は未コミット。

次もPhase 6。GUI consentと専用呼出し、root実行の専用認可/CLI、全mutator target lock、provisioningおよびPolicyKit/OS/Qt Gateを進める。
