# Phase 6 local root planning: existing drop-in preservation — 2026-09-05

## 結果

未完成root routeの監査で、`OllamaDropInPlanner.plan()`が既存の専用drop-inを選択済み設定だけから再生成し、未選択設定とコメントを削除する不具合を確認した。例として`OLLAMA_HOST`と`OLLAMA_FLASH_ATTENTION`があるfileで後者だけを選ぶと、前者が消えていた。変更前に保持・追記・未対応指令拒否・重複選択拒否のregression testで失敗を再現した。

既存fileがある場合は、対応するliteral assignmentの選択行だけを置換し、未選択行・コメント・空行・末尾改行の有無を保持するよう修正した。選択keyがまだない場合は末尾へ追記し、必要な区切り改行だけを追加する。新規file生成は従来どおり。before hash、承認対象のreplacement text、root/restart、rollback metadataは引き続きChangeSetへ束縛する。`after`とReview diffは選択した設定だけを記載する。

## 解釈範囲

対応する既存形式はLF、単一`[Service]`、allowlisted keyの`Environment="KEY=literal"`、コメントと空行に限定する。既存値のliteralはASCII英数字と`_ . : [ ] + -`だけを許す。未選択の既存値は変更しないため、新たな推奨値や検証済み性能閾値とは扱わない。選択した新規値には従来の型・allowlist・bounds検査を適用する。

以下は`unsupported_existing_drop_in`で計画生成前に停止する。

- 未知directive/key、Environment reset、複数assignment、section重複・欠落
- 同じ既存keyの重複、escape・specifier展開・継続行など解釈が必要な記述
- CRLF、NULなど未対応control文字、空file

選択自体のkey重複は`duplicate_setting`で拒否する。任意のsystemd構文を一般parserで解釈する変更ではない。対応外fileを自動で正規化・上書きしない。エラーにはfile本文や値を含めない。

## 検証

全544 testが完走（521成功・23 skip）。新規7 testは未選択設定・コメントの保持、末尾追記、末尾改行保持、危険/曖昧な既存形式の拒否、重複選択拒否、report-bound application経路での保持と拒否を確認する。拒否後は元fileとplanが不変であることも確認した。

compileall、local/remote packaging shell syntax、desktop-file validation、`git diff --check`が成功した。実Ollama/systemd/PolicyKit/SSH/VMには変更を加えていない。保存済みdeb/SBOMは本修正前のartifactに対する証拠であり、今回のcodeを収録済みとは扱わない。

## Route判断と次のPhase

現在・次ともPhase 6。MVP scopeは縮小していない。

- local root Apply: production compositionはあるがdefault rule catalogに根拠あるactionable Ollama ruleがなく、引き続き公開しない。今回の修正は公開前のデータ保全に必要な修正。allowlistだけを根拠に性能推奨を追加しない。
- SSH root Apply: 専用protocol不足のためI/O前に拒否する。SSH user protocolを流用しない。
- local root restore: privileged inventory/restore protocolが未完成。
- SSH user/root restore: 固定inventory、fingerprint binding、atomic restore、immutable result reconciliationの専用protocolが未完成。

次は上記routeの専用契約と受け入れ条件を具体化する。scope/versionをfreezeする前に未完成routeの完了または明示的なscope変更が必要。Debian通常ログイン後の実display/menu、host SSH修復後のGUI切断Gate、最終artifact lifecycle/SBOM/署名も残る。
