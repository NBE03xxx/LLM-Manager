# Version Matrix

## 1. 対応レベル

- **D:** 診断対応。read-only probeとparser fixtureが合格。
- **A:** 自動変更対応。Dに加えplan、backup、apply、validate、rollback fixtureが合格。
- **R:** 認識のみ。versionと未対応理由を表示し、設定変更しない。

## 2. 初期Matrix

| Component | Version / environment | Target | Initial level | Aへ進む条件 |
|---|---|---|---|---|
| Ubuntu | 26.04.1 + systemd | Local: D、SSH: D→A候補 | Local read-only統合済み。SSH、system/user unit、PolicyKit、terminal、deb sandbox test |
| Debian | 13 + systemd | Local/SSH | D→A候補 | Ubuntuと同じ契約test、desktop差分test |
| Python | 3.14.4 baseline、3.13.5 supported minimum | application | required | unit/serialization/thread/locale test。Debian 13 stockで338件成功 |
| PySide6 | 6.8.6以上、同一minorをpin | GUI | required | 3.14.4 wheel/import/Qt plugin/QThreadPool/i18n test |
| Ollama | 0.33.2 | Local: D、SSH: D→A候補 | Local API/systemd統合済み。SSH、allowlist、restart/rollback test |
| OpenCode | 1.18.25 | Local: D、SSH: D→A候補 | Local複数provider JSONC解析済み。merge provenance、SSH、round-trip、connection validation |
| OpenCode | 1.18.18 | SSH: R | 実設定のread-only解析は成功。tag固定schema差分とfixture追加後にDを判断 |
| Local helper | appと同一release/protocol | Local | required for A | 固定path、root owner/mode、canonical package/version/protocol metadata、PolicyKit action、protocol contract |
| Remote helper | app互換protocolの別deb | SSH | required for root A | 固定path、canonical package/version/protocol metadata、root owner/mode、sudo、journal/recovery test |

PySide6は公式release note上6.8.6からPython 3.14対応が明記されるため最低版とする。ただし配布時は、検証済みの同一versionへupper/lower pinし、未検証の新minorへ自動追随しない。

Debian 13のstock runtimeはPython 3.13.5、cryptography 43.0.0、SecretStorage 3.3.3である。初期検証基準のPython 3.14.4は維持しつつ、Debian 13を正式対象としてinstall可能にするsupported minimumをこのstock組合せまで拡張する。2026-08-31のdesktop Live Gateで全338単体テスト、AES-GCM import、Secret Service create/reload/delete、local/remote helper package runtimeを確認した。

## 3. Ollama 0.33.2 診断契約

| 情報 | 第一source | 期待field | 失敗時 |
|---|---|---|---|
| installed/version | `GET /api/version`、CLI fallback | raw + normalized semver | Rまたはnot_installed |
| service/effective env | `systemctl show`, unit/drop-in content | unit, active/sub, FragmentPath, DropInPaths, Environment | partial |
| connectivity | HTTP base URL | status, latency, endpoint | unavailable |
| models | `GET /api/tags` | name, size, digest, family, parameter, quantization | partial |
| loaded models | `GET /api/ps` | name, size, size_vram, context_length, expires_at | partial |
| model detail | `POST /api/show` | details, capabilities, model_info, parameters | per-model partial |

Ollama APIは厳密にversionedされないため、version rangeだけで互換扱いにしない。保存済みJSON fixtureに対してrequired field、optional field、unknown field保持を検証する。

Ubuntu 26.04.1での実機確認では、CLI version照会がAPI接続待ちにより短いprobe timeoutを超える場合があった。このため、稼働serverの診断は`GET /api/version`を第一sourceとし、CLIはAPI非稼働時の導入確認fallbackとする。

## 4. OpenCode 1.18.25 診断契約

tag固定sourceから次を基準とする。

- XDG config directory下の`config.json`, `opencode.json`, `opencode.jsonc`をmergeする。
- `OPENCODE_CONFIG`、project `opencode.json(c)`、`.opencode` directory等の追加sourceが存在し得る。
- global file candidateは`opencode.jsonc`, `opencode.json`, `config.json`の順に書込対象が選択される一方、読込merge順は別である。
- schemaには`model`, `small_model`, `provider`, `compaction`が存在する。
- provider optionsには`baseURL`, `timeout`, `headerTimeout`, `chunkTimeout`が存在する。

Ubuntu 26.04.1上の1.18.25実設定では、`provider` object配下に複数providerがあり、それぞれが`options.baseURL`と`models`を持つ構成を確認した。active providerが明示されない場合は単一値を推測せず、検出したprovider/model/base URL一覧をreportする。API key等のcredential値はdomain modelへ取り込まない。

LLM-Managerは「見つかった単一ファイル」をeffective configとみなさず、source provenanceとmerge順をreportする。初期A対応はglobal user configだけを変更対象とし、project/custom/inline/managed sourceが同じkeyをoverrideする場合はread-onlyとする。

## 5. 周辺Version追加規則

1. 公式release/tag/schemaを保存し、baselineとの差分を分類する。
2. D fixtureを追加し、unknown fieldと欠損fieldの挙動を確認する。
3. setting key、type、precedence、restart/validationが同じ場合だけA fixtureへ進む。
4. rollback故障注入を含むA testが通ったversionだけA rangeへ追加する。
5. prerelease、nightly、未知majorはR。version偽装・取得不能はD/Aにしない。

## 6. Matrix所有と更新

matrixはアプリreleaseとともにversion管理する。実行時にネットワークからschemaを自動取得してA対応を拡張しない。新しいschemaは開発時にreview・fixture化して次releaseへ含める。
