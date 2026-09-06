# Phase 6 local root restore intent codec — 2026-09-05

現在・次ともPhase 6。local root手動restoreの[専用契約](../local-root-restore-protocol.md)を追加し、canonical/bounded request codecだけを実装した。既存Apply rollbackのRESTORE_FILE、SSH user、retention/deletion protocolは変更していない。

requestは固定target、現在/復元先の存在・hash・root:root 0644、呼出元UID、host、backup/manifest/inventory/preview/approval、最大5分の期限を束縛する。最大16 KiB、canonical JSON以外は拒否する。decode時は呼出元とhostの独立した期待値を必須にした。ただしhashとcaller一致だけでは認可できず、codecはI/Oもauthority発行も行わない。

新規9 testでreplace/create/remove往復、binding改変、別caller/host、期限境界、bool/integer区別、不正metadata、no-op、未知/欠落/重複field、oversize、非有限数値、異常Unicode、深いJSONを検証した。既存helper decoderは新protocolを拒否し、local root restore availabilityも引き続きfalseである。

全553 test完走（530成功・23 skip）。compileall、local/remote packaging shell syntax、desktop validation、diff check成功。実VM、PolicyKit、Ollama/systemd、SSH、backup/keyは操作していない。全変更は未コミット。保存済みdeb/SBOMは本codecを含むartifactの根拠にはしない。

次はroot-owned backup/inventory evidenceの保存方式を確定し、read-only preflightを構築する。現行user-owned local manifestをroot authorityへ転用しない。専用executor/result store/reconciliationと実機Gateが揃うまでproductionへ接続しない。MVP scopeは変更せず、Phase 6未完了を維持する。
