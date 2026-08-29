# MVP Setting Allowlist

## 1. 原則

allowlistは「推奨可能」ではなく「自動Changeを生成可能」な対象を定義する。version、source、path、type、validation、rollbackが一致しない場合はread-onlyにする。credential、SSH設定、vendor unit本体、model作成・削除は対象外である。

## 2. Ollama 0.33.2

自動変更先はsystem unitが確認できた場合の専用drop-in `/etc/systemd/system/ollama.service.d/90-llm-manager.conf` とする。既存unitや他drop-inを編集しない。user unitしか存在しない環境は初期MVPではDのみとし、別fixture確立後にAへ追加する。

| Key | Type / bounds | Profiles | Risk | Validation |
|---|---|---|---|---|
| `OLLAMA_HOST` | loopback address (`127.0.0.1`, `::1`, `localhost`) + portのみ | all | port conflict | effective env + bind/API |
| `OLLAMA_CONTEXT_LENGTH` | positive integer、model上限とmemory ruleでbounded | all | memory/OOM | effective env + `/api/ps` runtime context when loaded |
| `OLLAMA_KEEP_ALIVE` | duration/seconds、無期限値はhigh risk | all | persistent memory | effective env + loaded model expiry behavior |
| `OLLAMA_MAX_LOADED_MODELS` | positive integer、GPU/RAM capacityでbounded | Balanced/Agent | memory/OOM | effective env + controlled load observation |
| `OLLAMA_NUM_PARALLEL` | positive integer、初期上限はrule fixtureで決定 | Balanced/Agent | context×parallel memory | effective env + overload validation |
| `OLLAMA_MAX_QUEUE` | positive integer、hard capはrule fixtureで決定 | Agent | latency/memory pressure | effective env + API connectivity |
| `OLLAMA_FLASH_ATTENTION` | `0`/`1` | Coding/Agent | compatibility | effective env + service/API health |
| `OLLAMA_KV_CACHE_TYPE` | `f16`, `q8_0`, `q4_0`。公式対応確認済み値のみ | Agent | quality/compatibility | effective env + model load/API health |

`OLLAMA_CONTEXT_LENGTH × OLLAMA_NUM_PARALLEL`がmemoryを増加させるため、これらは同一ChangeSetで再評価する。`OLLAMA_HOST`のnon-loopback、wildcard、hostname/IPによる外部bindはMVP denylistとし、自動Changeを生成しない。必要な利用者には認証・TLSを備えたreverse proxy等の手動設計を案内する。

Apply後は`systemctl daemon-reload`, `restart ollama.service`, service status, API, effective environmentの順で検証する。drop-inが元から存在しなければrollbackは削除、存在すれば元content/metadataへ復元する。

## 3. OpenCode 1.18.25

初期A対象はXDG global configの既存active candidate内に既に存在するscalar keyだけとする。JSON/JSONC token scannerで対象valueのsource spanを特定し、そのliteralだけを置換する。key/object/arrayの追加・削除、ファイル新規作成、全体再serializeは行わない。project、`.opencode`、`OPENCODE_CONFIG(_CONTENT/_DIR)`、managed/remote sourceが対象keyをoverrideする場合は変更しない。

| JSON path | Type | Profiles | Secret | Validation |
|---|---|---|---|---|
| `model` | `provider/model` string | all | no | schema + provider/model availability |
| `small_model` | `provider/model` string | Balanced/Agent | no | schema + availability |
| `provider.ollama.options.baseURL` | 対象hostのloopback `http://127.0.0.1:<port>/v1` またはIPv6相当 | all | endpoint/port | schema + native/API connectivity。userinfo/redirect禁止 |
| `provider.<id>.options.timeout` | positive ms or `false` | Agent | no | tag schema + config reload parse |
| `provider.<id>.options.headerTimeout` | positive ms or `false` | Agent | no | tag schema + config reload parse |
| `provider.<id>.options.chunkTimeout` | positive ms | Agent | no | tag schema + config reload parse |
| `provider.<id>.models.<model>.limit.context` | finite positive number | Coding/Agent | no | tag schema + Ollama model metadata |
| `compaction.auto` | boolean | Agent | no | tag schema + config reload parse |
| `compaction.prune` | boolean | Agent | no | tag schema + config reload parse |
| `compaction.tail_turns` | non-negative integer | Agent | no | tag schema + config reload parse |
| `compaction.preserve_recent_tokens` | non-negative integer | Agent | no | tag schema + context budget rule |
| `compaction.reserved` | non-negative integer | Agent | no | tag schema + context budget rule |

`apiKey`, `headers`, `{env:...}`, `{file:...}`の参照先、auth fileは診断時にmaskし、自動変更しない。Ollama以外のprovider、non-loopback、URL userinfo、redirect、scheme変更はMVP自動変更対象外とする。`timeout=false`はAgentの長時間処理に使えるが無限hang riskがあるためRule Engineの既定推奨にはせず、bounded timeoutを優先する。

## 4. 明示的Denylist

- `/usr/lib/systemd`, `/lib/systemd`配下のvendor unit
- allowlist外の`/etc`ファイル、sudoers、SSH config/keys
- Ollama model blob、Modelfile、create/pull/delete API
- OpenCode credential/auth、plugin、permission、tools、instructions、shell
- inline/remote/managed OpenCode config
- OpenCodeのkey/object/array追加・削除、および既存config全体の再serialize
- non-loopback/wildcard Ollama bind、Ollama以外のprovider base URL
- symlink解決後に許可root外となるtarget

## 5. 未確定閾値

context、parallel、loaded models、queue、timeout、compaction token値の具体的推奨値はRule fixtureとmemory modelが完成するまでactionableにしない。allowlistに存在することは推奨値が確定したことを意味しない。
