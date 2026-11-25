# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批：报告中除原始结论外，还包含 `disputes`（争议清单）、`supplements`（已采信补证）、`recomputed`（补证后各组复算状态）、`case_signability`（逐组可签发判定与阻塞原因）以及当前 `case_reviews`。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`，状态使用 `APPROVED` 或 `HELD`，作用于整批，仅在整批无待处理差异时允许签发。冲突返回 409，客户端读取新版本后重试。

`PATCH /api/runs/<id>/cases/<case>` 为组级复核，请求体含 `revision`（该组自己的修订号，首次为 0）、`status`（`APPROVED`/`HELD`）和 `note`。组处于未决争议中或补证复算未通过时返回 409 `CASE_NOT_SIGNABLE`；组已签发后再改写返回 409 `CASE_FINALIZED`；修订号过期返回 409 `STALE_REVIEW`。无争议且判定 READY 的组可独立签发，不受同批其他争议组影响。

`POST /api/runs/<id>/supplements` 提交补证，请求体含 `dispute_id` 与 `row`（与来源 CSV 同列的 9 个字段数组）。系统用补证行替换争议记录后对全部受影响组（争议原涉及组 ∪ 补证改归的目标组）整体复算，任一组非 READY 则裁决 `accepted=false` 且所有受影响组继续暂缓。同一争议只采信一个补证版本：重复或并发提交落败者返回 409 `SUPPLEMENT_CONTESTED`，胜出版本不被覆盖；补证若触及已签发组返回 409 `CASE_FINALIZED`。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、争议与补证裁决、逐组复算与可签发判定、业务证据和两级复核信息的 JSON（schema `review-evidence/2`）。
