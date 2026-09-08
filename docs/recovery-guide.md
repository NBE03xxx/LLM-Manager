# Backup・Rollback・Recoveryガイド

この文書はLLM-Manager MVPで設定変更を行う利用者向けの復旧手順です。画面に表示された状態と、現在公開済みの経路だけを基準にしてください。

## 利用できる経路

| 対象 | Apply失敗時の自動rollback | Backup画面からの手動restore |
|---|---|---|
| local user OpenCode設定 | 利用可能 | 利用可能（単一target） |
| local root Ollama設定 | productionでは利用不可 | 利用可能（事前に採取済みのroot backup） |
| SSH user OpenCode設定 | 利用可能 | 利用不可 |
| SSH root設定 | 利用不可 | 利用不可 |

利用不可の経路は、経路ごとのprotocolと公開Gateが完了するまでI/O前に固定理由を表示して停止します。local root手動restoreは各工程でPolicyKit管理者認証と明示同意を要求します。SSH手動restoreは専用protocol未完成です。別経路のhelperやbackupを流用して復元しないでください。

## Apply前に確認すること

Review画面でhost、target、現在値、変更後の値、masked diff、再起動の有無を確認します。表示内容が想定と違う場合は承認せず、診断からやり直してください。承認後にhost、Plan、設定内容、backup設定が変わると承認は失効します。

一般配布buildはbackup暗号化が既定で有効です。local暗号鍵はdesktop sessionのSecret Serviceに保存されます。Secret Serviceがロック中ならOSの解除画面に従い、解除を取り消した場合はApplyも停止します。暗号化を利用できない状態で自動的に平文へ切り替わることはありません。

SSH user Applyはlocal正本とSSH先のroot-owned recovery copyを両方作成・検証してから変更を開始します。外部端末にsudo認証が表示された場合、passwordはその端末だけへ入力します。LLM-Managerの画面、引数、標準入力へpasswordを渡さないでください。

## Apply結果の意味

| 状態 | 意味 | 次の操作 |
|---|---|---|
| `committed` | 変更とruntime検証が完了 | 必要なら診断を再実行して結果を確認 |
| `rolled_back` | Applyまたは検証に失敗し、元状態の復元を検証済み | 診断を再実行。原因を解消するまで同じ変更を繰り返さない |
| `approved` | Backupまたは変更開始前に停止 | 表示されたerror codeを確認し、再診断・再Reviewする |
| `recovery_required` | Apply/rollback結果が不明、または復元を完了できない | 下記のRecovery手順へ進む |

SSH切断後にLLM-Managerが同じimmutable resultをread-onlyで再確認する場合があります。Apply requestそのものは自動retryしません。`recovery_required`を見てApplyボタンを繰り返し押さないでください。

## local user backupを手動restoreする

現行GUIで手動restoreできるのは、local user所有の単一OpenCode設定だけです。

1. local hostを選択してBackup画面を開き、「バックアップ一覧を再読込」を実行します。
2. `attention`と`restore attention`がfalseで、目的のbackup IDであることを確認します。
3. backupを選択します。画面には内容ではなくtarget、元の存在、SHA-256、modeだけが表示されます。
4. targetとmetadataを確認し、そのプレビュー専用のrestore承認checkboxを選択します。
5. restoreを実行し、`committed`、`failed`、`unknown`の明示的なevidence状態を確認します。
6. 完了後に一覧を明示的に再読込します。同じ承認は再利用できません。

host変更、一覧再読込、選択変更、期限切れでプレビューと承認は失効します。`failed`または`unknown`では自動retryせず、Recovery手順へ進んでください。

## local root backupを手動restoreする

local hostを選択し、Backup画面の「システム設定を復元」から、採取済みのroot所有Ollama backupを復元できます。root stateが未初期化、backupがない、またはevidenceが不整合の場合は、管理者認証後もfail closedで停止します。

1. 「システム設定を復元」を開き、管理者認証でroot backupのメタデータ一覧を取得します。
2. backup ID、採取日時、元ファイルの存在とSHA-256を確認し、1件を選択します。
3. 別の管理者認証でpreviewを取得し、現在値と復元値、host、target、期限を確認します。
4. 明示同意を選択し、別の管理者認証でreviewを保存します。reviewだけでは復元されません。
5. 最終確認画面で復元を実行し、専用execute認証を完了します。
6. `committed`と`requires_attention: false`を確認します。中断や応答不明時は同じ要求を再送せず、「保存済み結果を確認」でread-only statusを照合します。

認証ダイアログのキャンセル、期限切れ、対象hash変更では復元を開始しません。`failed`はterminal evidenceを保存済み、`unknown`または`requires_attention: true`は管理者照合が必要な状態です。いずれも自動retryしないでください。

restoreの`failed`は、失敗を示すterminal evidenceが保存された状態です。`unknown`はmutation後の中断やterminal evidenceの保存失敗などにより、結果を成功・失敗のどちらとも断定できない状態です。`failed`でもtargetやserviceが利用可能とは推測せず、`unknown`では特に再実行で上書きしないでください。

## `recovery_required` / `failed` / `unknown`時の手順

1. そのhostに対するApply、restore、backup cleanupを止めます。アプリを何度も再実行しないでください。
2. host ID、SSHの場合はfingerprint、Plan/backup ID、target、状態、error codeを記録します。設定本文やsecretは記録へ貼り付けないでください。
3. LLM-Managerのlocal state、対象設定、SSH先のrecovery copyと鍵を削除・編集しないでください。packageのpurgeを復旧手段として使わないでください。
4. SSHの場合はknown-host fingerprintと接続先を管理者が確認します。fingerprintが変わっている場合、変更理由が確認できるまで接続や復元を進めません。
5. 対象設定の現在hashが、画面や保存済みevidenceのbefore hash、after hashのどちらに一致するかを確認します。どちらにも一致しない場合は外部変更または破損として扱い、上書きしません。
6. 現行GUIが対応するlocal user単一targetなら、Backup画面をread-only再読込し、整合したbackupから上記の手動restoreを行います。
7. local rootは上記の専用画面で保存済みstatusを照合します。SSHの手動restoreは現行MVPで未提供のため、対象サービスの管理者が保存済みevidenceと別途保有する運用backupを照合して手動復旧します。非公開helperや未完成protocolを直接呼ばないでください。

対象設定を手動で調査・退避する場合も秘密情報を含むものとして扱い、一般ユーザーから読める場所やsupport ticketへ平文で置かないでください。

## Backupと鍵の場所

local state rootは、絶対pathの`XDG_STATE_HOME`が設定されていれば`$XDG_STATE_HOME/llm-manager/`、それ以外は`~/.local/state/llm-manager/`です。backup、journal、audit、restore evidenceはこの配下の分離されたdirectoryへ保存されます。directoryは0700、fileは0600を前提に検証され、symlinkや別ownerなどの不安全な状態では処理を停止します。

local暗号鍵はSecret Serviceにあり、backup fileやmanifestには鍵本体を保存しません。SSH先のroot recovery copyは`/var/lib/llm-manager/backups/`、独立したremote鍵は`/var/lib/llm-manager/keys/backup.key`です。remote側はroot:root、directory 0700、file 0600を前提とします。

これらのfileを移動・改名・編集すると、identity/hash/AAD検証に失敗して復元できなくなります。通常のfile backupとして保全する場合は、directory構造、owner、mode、Secret Serviceまたはremote鍵を含む一貫した復旧計画を別途用意してください。

## 鍵を失った場合

- local Secret Service鍵を失うと、対応するlocal暗号化copyは復号できません。
- remote鍵を失うと、対応するremote root copyは復号できません。
- SSH backupはlocalとremoteで独立鍵を使うため、片側の鍵とcopyが健全なら復元素材が残る設計です。ただし現行GUIにはSSH手動restoreがないため、管理者による検証済みの復旧が必要です。
- local/remote両方の鍵またはcopyを失った場合、LLM-Managerから設定本文を復元することはできません。

鍵を新規作成しても過去のbackupは復号できません。紛失した鍵と同じ名前の新しい鍵で復旧を試みないでください。

片側のcopyまたは鍵だけを失った場合は、健全な側のcopy、manifest、receipt、鍵をそのまま保全し、backup cleanupや同じIDでの再作成を停止してください。失われた側を空fileや新しい鍵で補わず、host ID、fingerprint、backup ID、各copyのhashとpresenceを管理者が照合します。SSH手動restoreは現行GUIで未提供のため、健全な片側が残っていても未公開helperを直接実行しないでください。

## 保持、upgrade、uninstall

設計上の既定保持は30日かつhostごとに直近10世代で、保護backupは自動削除対象外です。現行GUIのBackup画面は一覧とrestoreを中心としたread-only境界であり、表示されたaction名を削除実行済みとは解釈しないでください。

debのupgrade、remove、purgeはpackage管理対象のlauncher、helper、desktop metadataを扱います。user state、Secret Service鍵、SSH先のrecovery copyを復旧目的で自動削除するものではありません。OSやhome directoryを廃棄する前に、必要なbackupと鍵を別の検証済み手段で保全してください。

## 既知の制限

- local root Applyは実装済み内部compositionを公開しておらず、根拠あるactionable Ollama recommendationが確定するまでfail closedです。
- local root手動restoreには、事前初期化とLLM-Managerが採取した互換root backupが必要です。任意のbackup importや自動鍵再作成は行いません。
- SSH user、SSH rootの手動restoreは利用できません。
- SSH切断時の結果照合は自動mutation retryの許可ではありません。
- audit hash chainは偶発的な改変検出用で、同じuser権限を完全に侵害した攻撃者に対する外部署名ではありません。
- 未知のsecret形式を自動redactionで完全に検出する保証はありません。診断・復旧情報を共有する前に利用者自身でも確認してください。
