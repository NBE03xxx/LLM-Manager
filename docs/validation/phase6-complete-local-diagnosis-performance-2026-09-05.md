# Phase 6 complete local production診断 Gate

## 検出と修正

2026-09-05、hostには稼働中Ollama 0.33.2とOpenCode 1.18.25が存在したが、OpenCodeは標準的なuser配置 `/home/yoshimi/.opencode/bin/opencode` だった。production `SubprocessRunner`は安全のためPATHを `/usr/local/bin:/usr/bin:/bin`へ固定しており、従来の`opencode` argvではuser配置を検出できなかった。これはlocal診断とlocal user Apply後のruntime validationが、実インストールを見落とす原因になる。

任意PATHは許可せず、固定位置 `~/.opencode/bin/opencode`について次を満たす場合だけabsolute executableとしてproduction compositionへ渡すよう修正した。

- binary自身がsymlinkではないregular file
- 実行user所有
- owner executable
- group/world writableではない
- `.opencode`と`bin` directoryがsymlinkではない

条件を満たさない場合は従来の`opencode`へ戻り、固定system PATH内だけを検索する。診断用runner allowlistにも選択したabsolute pathだけを加える。同じresolverをlocal user production ApplyのOpenCode runtime validatorへ接続した。rootやSSH経路はこの変更で拡張しない。

unit testは安全な固定fileの採用、group writable file、binary symlink、parent directory symlinkの拒否、診断runner allowlist、診断adapter、Apply validatorへの同一binary注入を検証する。

## 実環境5 sample

`packaging/measure-complete-local-diagnosis.py`からproduction `DiagnosticTaskFactory`を5回実行した。Ollama API、OpenCode version、OS、CPU/memory/disk/GPU probe、local helper capability probeはすべてread-only。report内容や設定値は保存せず、状態とversion、時間だけを記録した。

| 指標 | 結果 |
| --- | ---: |
| report | `complete` 5/5 |
| wall time | 434.000–509.774 ms |
| process CPU | 3.203–4.714 ms |
| process累積peak RSS | 77,864 KiB |
| Ollama | 0.33.2、API `ok` 5/5 |
| OpenCode | 1.18.25、固定user binary 5/5 |
| system / hardware | 両方5/5 |
| `can_elevate` | false 5/5 |

生データ: [JSON](phase6-complete-local-diagnosis-2026-09-05.json)。`can_elevate=false`は同梱helper readinessを満たさない現在hostのread-only evidenceで、診断失敗には数えない。

全534 test完走（511成功・23 PySide6 runtime skip）。compileall、local/remote packaging shell syntax、desktop-file-validate、全Phase 6 JSON parse、git diff checkも成功した。

## 限界

同一hostで連続した5 sampleであり、Qt event loopはこの測定に含まない。Ollama/OpenCodeへ診断以外のrequestを送らず、model loadや推論benchmarkは行っていない。単一hardwareのbaselineでありrelease SLOではない。

SSH再Gateはhost system SSH configの所有者・mode不正によりproduction `ssh`が設定読込時にfail closedするため保留した。`-F /dev/null`は製品経路の代替根拠にしない。host SSH設定は変更していない。

次もPhase 6。host SSH設定が管理者により修復された後の完成GUI SSH disconnect/reconciliation、またはログイン済みDebian実display/menu/accessibilityを継続する。
