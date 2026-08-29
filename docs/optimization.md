# 最適化・Rule Engine 設計

## 1. 原則

MVP の推奨は LLM に判断させない。version 管理された明示ルールを純粋関数として評価し、同じ `DiagnosticReport + Profile + RuleCatalog` から同じ結果を生成する。推奨は変更ではなく助言であり、Change Planner と Executor から分離する。

## 2. 用途プロファイル

| Profile | 重視するもの | 許容する trade-off |
|---|---|---|
| Balanced | 応答性、品質、資源消費、安定性の均衡。初期既定 | 最大 context や最大並列性を追わない |
| Coding | コード品質、編集に十分な context、対話 latency、対象モデルとの整合 | 極端な長時間常駐より反復速度を優先 |
| Agent | 長時間処理、tool call 往復、増大する context、KV cache、compaction、timeout、復旧性 | メモリ余裕と安定性のため throughput/最大 context を抑える場合がある |

Coding と Agent は分離する。Agent は「context を最大化」するプロファイルではない。VRAM/RAM の安全余裕、KV cache の成長、tool output、compaction 発生点、API/client timeout、モデル常駐の安定性を同時に評価する。

## 3. ルールモデル

各 rule は次を持つ。

- `id`, `version`, `title`, `targets`, `profiles`, `priority`
- `conditions`: 型付き predicate の AND/OR。欠損値の扱いを明示
- `recommendation`: setting key、値または安全な計算式
- `reason_template` と `evidence_fields`
- `reason_key`, `reason_args`, `fallback_reason`（日本語・英語表示はUI catalogで解決）
- `severity`, `confidence`, `impact`, `risk`
- `requires_restart`, `requires_root`
- `conflicts_with`, `supersedes`, `applicability`
- `references`: 根拠となる対応版や内部設計注記

任意 Python、shell、template 内 expression の実行は禁止し、安全な predicate/operator のみ許可する。

## 4. 評価フロー

```text
Validate report freshness/completeness
→ Select rules by product/version/profile/capability
→ Evaluate conditions with evidence
→ Compute bounded recommendation
→ Resolve precedence/conflicts
→ Emit recommendations and skipped-rule reasons
```

値が不足する場合、高 confidence の断定を行わない。安全に計算できなければ `informational` な「測定不能」推奨か、`not_applicable` とする。

## 5. 初期ルール群の領域

MVP では具体値を製品対応版の検証前に固定せず、以下の rule family を実装対象とする。

- endpoint/provider/model の到達性と整合
- model が利用可能な memory に収まるための安全余裕
- context 増加に伴う KV cache と RAM/VRAM 圧迫
- Balanced/Coding/Agent ごとの context 上限候補
- Agent の compaction 方針と timeout 下限候補
- loaded model の保持とメモリ圧迫の trade-off
- CPU-only または partial offload 時の latency 警告
- 設定値と runtime 値の不一致解消
- 再起動が必要な systemd environment 変更

ハードウェア情報だけから量子化やモデル品質を断定しない。model download は提案対象に含めても実行対象外とする。

## 6. 値計算の安全策

- すべての計算値に min/max と単位を定義する。
- 「空きメモリの全量使用」を推奨せず、OS、tool、context 成長用の reserve を profile ごとに確保する。
- 複数 GPU は単純合算できると仮定しない。Ollama runtime の実観測を優先する。
- 現在ロード中の瞬間値だけで永続設定を決めない。
- version/schema が未対応なら設定変更可能な推奨にしない。

## 7. Python と YAML の比較

| 方式 | 長所 | 短所 |
|---|---|---|
| Python 定義 | 型検査、複雑な境界処理、debug、単体テストが容易 | 非開発者の編集、静的監査、外部更新が難しい |
| YAML | review、差分、配布、非コード更新が容易 | schema/型/式言語が必要で、複雑化すると独自言語になる |
| Hybrid | predicate と計算器は Python、閾値・説明・metadata は YAML | 2 層の version/検証が必要 |

**MVP 設計判断:** 最初は型付き Python rule definitions と pure evaluator を採用する。ルール数と対応版が安定した後、制約付き YAML catalog へ外出しできるよう rule model と serializer を先に定義する。任意コード実行を許す YAML は採用しない。

## 8. 競合と優先順位

同一 setting に異なる値が出た場合、暗黙の last-win を禁止する。`supersedes`、profile-specificity、priority の順で解決し、解決不能なら conflict としてユーザー選択または plan 除外にする。安全上限 rule は性能 rule より優先する。

## 9. 説明可能性

Recommendation は、入力 evidence、比較式、採用値、除外された代替を人間向けに説明できる。例: 「Agent profile だから」だけでなく、runtime context、available memory、reserve、対応 version を示す。confidence はデータ完全性と source 信頼度から決める。

Ruleは判定結果として翻訳済み文章ではなく安定したmessage keyとtyped argumentsを返す。日本語・英語の翻訳は同じevidenceとseverityを表現し、翻訳によって技術的意味やrisk levelを変えない。

## 10. テストと versioning

- threshold 境界の table-driven test
- 3 profile の golden fixture
- 欠損・矛盾・複数 GPU・CPU-only・未知 version
- 全推奨値が schema と安全上限内である property test
- 競合が明示され last-win が発生しないテスト
- rule catalog の変更で golden 差分を review

計画には rule catalog version を固定する。rule 更新後に既存 plan を silently 再解釈しない。

### Rule fixture 契約

各ルールは最低限、次の fixture 群を持つ。

```yaml
rule_id: agent.context.memory-headroom
rule_version: 1
profile: Agent
cases:
  - name: matches_with_complete_evidence
    report_fixture: agent_gpu_supported.json
    expected: recommendation_golden.json
  - name: boundary_does_not_exceed_safe_limit
    report_fixture: agent_memory_boundary.json
    expected: recommendation_boundary_golden.json
  - name: missing_runtime_memory_reduces_confidence
    report_fixture: agent_missing_runtime_memory.json
    expected: recommendation_partial_golden.json
  - name: unsupported_version_is_not_actionable
    report_fixture: agent_unknown_version.json
    expected: recommendation_readonly_golden.json
```

これはテストデータの形式例であり、YAMLルールエンジンの採用を意味しない。期待結果には rule/profile/catalog version、evidence、値と単位、severity/confidence、risk、actionability を含める。

### 閾値確定手順

1. 対応版の公式仕様と取得可能なruntime値を確認する。
2. 単位、min/max、reserve、丸めを設計記録に残す。
3. Balanced/Coding/Agentの境界fixtureを作る。
4. CPU-only、単一GPU、複数GPU、欠損値で安全側になることをreviewする。
5. 根拠が不足する値はactionable ruleにせずinformational findingに留める。

## 11. 残存検証事項

baseline version matrixは確定した。具体的なreserve比率、context/timeoutの閾値と周辺version追加はfixture、公式仕様、sandbox観測後に確定する。これらを未検証のまま「最適値」またはA対応として文書化しない。

## 12. Phase 3 初期Catalog実装

catalog `1.0.0`では、安全に根拠を固定できる次のruleだけを有効化した。

- OpenCodeのOllama互換設定に対してOllama APIが利用不能な場合のmanual review
- OpenCode基準版1.18.25以外をread-onlyへ縮退するversion compatibility
- Agent profileで既存の`compaction.auto` / `compaction.prune`がfalseの場合のtrue推奨

Agent compactionは、基準版、active global config、parse warningなし、既存値がbooleanという全条件を満たす場合だけactionableになる。Balanced/CodingへAgent固有設定を流用しない。context、parallel、timeout等の数値ruleは、対応版ごとの検証済みboundsを追加するまでcatalogへ入れない。

Change PlannerはOpenCode設定全文をChange/diffへ保存せず、変更対象scalarのsource span、置換literal、変更前file hashだけを保持する。Ollamaは専用`90-llm-manager.conf`だけを生成し、数値設定は明示された`OllamaSettingPolicy` boundsがなければ拒否する。
