# 診断設計

## 1. 原則

診断は read-only であり、設定変更、package 操作、service restart、model pull、sudo を行わない。コマンド不在や権限不足は全体失敗にせず、項目単位の状態として返す。各 probe は timeout、取得元、時刻、parser version を持つ。

## 2. 診断パイプライン

```text
Resolve host → Check connectivity/capabilities → Run independent probes
→ Parse/normalize → Cross-check configured vs runtime → Assemble report
```

独立 probe は同一ホストへの負荷を制限しながら並列化する。SSH セッションの再利用は将来最適化とし、正確性を優先する。コマンドは locale を可能な範囲で固定し、機械可読形式、`/proc`、`/sys`、API JSON を人間向け CLI 出力より優先する。

## 3. MVP 必須診断

### System / Hardware

| 項目 | MVP | 候補ソース | 備考 |
|---|---|---|---|
| distribution/version | 必須 | `/etc/os-release` | parser で構造化 |
| kernel/architecture | 必須 | `uname` |  |
| CPU/model/logical cores | 必須 | `/proc/cpuinfo`, `lscpu -J` | physical cores は取得可能時 |
| RAM/available | 必須 | `/proc/meminfo` | bytes に正規化 |
| swap | 必須 | `/proc/meminfo` |  |
| disk total/free | 必須 | `statvfs` 相当、`df` | 対象設定・モデル領域を重視 |
| GPU vendor/name/count | 必須（存在時） | PCI、vendor tools | GPU なしを正常状態とする |
| VRAM total/used | 必須（対応時） | `nvidia-smi`, ROCm tools, sysfs | unavailable を許容 |
| driver / CUDA / ROCm | 必須（対応時） | vendor tools/package metadata | 導入はしない |
| utilization/temperature | 任意 | vendor tools | 瞬間値であり判断根拠を限定 |

CPU physical cores、uptime、filesystem 詳細は best-effort。GPU 温度、複数 GPU の topology、power limit、NUMA、iGPU shared memory は将来強化とする。

### Ollama

MVP は次を必須または状態付きで取得する。

- installed、binary path、version
- service status、検出された systemd user/system unit、enabled state
- systemd unit/drop-in の有効 environment（秘密値は mask）
- API endpoint と connectivity
- model list、size、digest、architecture、parameters、quantization（API が返す範囲）
- loaded models、runtime context、processor/offload 表示、CPU/GPU memory（API が返す範囲）

GPU layer 数や厳密な offload 内訳など、Ollama の対応版から安定して取得できない値は `unsupported/unavailable` とし、推測しない。runtime memory のプロセス/GPU tool による推定は将来対応とする。

### OpenCode

- installed、binary path、version
- version に応じた候補 config location と active source
- provider、model、base URL
- context/compaction/timeout 関連値（schema で認識できる範囲）
- Ollama または互換 API への接続関係

未知 schema は parse error で全体を捨てず、raw location と警告を返す。token、authorization header、credential reference は表示・ログから除外する。

## 4. 設定値と実行時値の不一致

値は `configured`, `runtime`, `effective`, `source`, `consistency` に分ける。優先順位を暗黙化せず、Adapter の対応版ごとの resolver が説明を返す。

例:

- systemd drop-in の endpoint と API 応答先が異なる
- 設定上の context と loaded model の runtime context が異なる
- OpenCode の設定モデルと接続先の利用可能モデルが一致しない
- 環境変数が設定ファイルを override している

不一致は `DiagnosticFinding` として severity、evidence、想定原因を持つ。runtime 値が取得不能な場合は mismatch と断定しない。

## 5. Probe 状態

`ok`, `not_installed`, `not_applicable`, `unsupported`, `permission_denied`, `unavailable`, `timeout`, `failed`, `cancelled` を区別する。必須 probe が複数失敗した report は `partial`、接続や host identity を確認できない場合は `failed` とする。

## 6. セキュリティ

- 許可リスト化した read-only command を argv で実行する。
- shell、profile scripts、任意ユーザー入力を評価しない。
- SSH host alias は厳格に検証し、オプション注入を防ぐ（`--` が使えない箇所も考慮）。
- stdout/stderr と環境変数は保存前に secret redaction を通す。
- API は既定 endpoint のみ自動照会し、任意 URL はユーザーが選んだホストとの整合を検証して SSRF 的な逸脱を防ぐ。

## 7. Timeout と負荷

probe 単位と診断全体の timeout を持つ。短い OS probe、vendor tool、SSH、HTTP で別既定値を設定し、UI から一律無限待機にしない。GPU query や model detail は同時実行数を制限する。

## 8. テスト

- 各 parser に正常、欠損、版差、locale 差、malformed fixture を用意する。
- Local/SSH Adapter が同じ構造結果を返す契約テストを行う。
- 実コマンドを呼ばない fake HostPort で完全な DiagnosticReport を生成する。
- 診断が write/service/root 操作を要求しないことを spy で保証する。
- secret redaction と partial report を故障注入で検証する。

### 対応マトリクスの管理形式

実装前に、診断項目ごとに次の列を持つ version matrix を test fixture と同じ場所で管理する。

| 項目 | 対象distro/product version | 第一取得元 | fallback | 必要command/API | 権限 | timeout class | parser fixture | 未対応時状態 |
|---|---|---|---|---|---|---|---|---|

matrix に存在しない major version は自動変更の根拠に使わない。診断は可能な範囲で継続し、結果に `unsupported_version` warning を付ける。matrix の変更は parser fixture と契約テストの追加を必須とする。

## 9. 将来対応

GPU topology/温度履歴、詳細 offload、プロセス別メモリ、benchmark、複数時点比較、他 OS、container/WSL 判定を追加できる。ただし benchmark は明示的な別ユースケースとし、read-only 診断に混ぜない。
