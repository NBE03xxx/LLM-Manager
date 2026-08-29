# Rule Fixture Contract

## 1. 目的

Rule Engineの数値をコード実装前に検証可能にする契約を定義する。Phase 0ではfixtureのschemaと必須caseを確定し、具体的な性能閾値はPhase 3で公式仕様とsandbox観測を根拠に埋める。

## 2. Fixture構成

```text
tests/fixtures/rules/
├── reports/          # immutable DiagnosticReport JSON
├── expected/         # Recommendation JSON
└── cases/            # rule case manifest YAML/JSON
```

case manifestは`case_id`, `rule_id`, `rule_version`, `catalog_version`, `profile`, `report`, `expected`, `tags`, `references`を持つ。expectedは値だけでなく、applicability、evidence field、reason key、severity、confidence、risk、restart/root要否を含む。

## 3. 必須Case Matrix

| Family | 必須case |
|---|---|
| context/memory | CPU-only、単一GPU、複数GPU非合算、VRAM不足、runtime memory欠損、model上限境界 |
| parallelism | 1、境界、context×parallelがreserve超過、unknown runtime |
| KV cache | flash attention ON/OFF、f16/q8_0/q4_0、unsupported value |
| Agent timeout | bounded timeout、false指定、chunk/header/fullの矛盾 |
| compaction | auto/prune、reserved+recent budget境界、context不足 |
| source conflict | configured/runtime mismatch、OpenCode override source、stale report |
| version | exact baseline、compatible added version、unknown minor/major |

## 4. 安全Property

- unknown/missing evidenceからhigh confidence actionable recommendationを生成しない。
- context、parallel、loaded model数を単独最適化せず、combined memory constraintを満たす。
- allowlist外keyをRecommendationにできてもChangeへ変換しない。
- CodingとAgentのgolden結果が少なくともcontext/timeout/compactionのいずれかで異なる。
- 同じreport/profile/catalogからbyte-equivalentな正規化結果を返す。

## 5. Catalog Review

閾値変更はgolden diff、根拠URL、対応version、risk評価を必須とする。実機benchmarkはMVP対象外なので、測定不能な性能改善を断定せず、安全上限と整合性推奨を優先する。
