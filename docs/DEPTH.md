# 分区补数排程盘规则登记

- 规模：中型

## 功能模块

| 模块 | 动作 | 接口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 样例采信 | 预览并定位坏行 | `POST /api/stages/intake` | `app/intake/service.py` | `tests/test_intake.py` |
| M2 依赖校核 | 检查领域约束 | `POST /api/stages/prepare` | `app/modules/prepare.py` | `tests/test_prepare.py` |
| M3 时隙编排 | 查看业务计算结果 | `POST /api/stages/calculate` | `app/modules/calculate.py` | `tests/test_calculate.py` |
| M4 期限核验 | 查看签收判定 | `POST /api/stages/policy` | `app/modules/policy.py` | `tests/test_policy.py` |
| M5 运行对账 | 对照输入、采信和隔离行 | `POST /api/stages/balance` | `app/modules/reconcile.py` | `tests/test_reconcile.py` |
| M6 批次复核 | 执行批次并整批或逐组签发、暂缓 | `POST /api/runs、PATCH /api/runs/<id>、PATCH /api/runs/<id>/cases/<case>` | `app/review/service.py` | `tests/test_review.py、tests/test_disputes.py` |
| M7 证据交付 | 下载含争议裁决的复核清单 | `GET /api/runs/<id>/evidence` | `app/evidence/render.py` | `tests/test_evidence.py` |
| M8 争议补证 | 登记跨组争议、补证复算与唯一采信 | `POST /api/runs/<id>/supplements` | `app/intake/disputes.py、app/review/adjudication.py` | `tests/test_disputes.py、tests/test_dispute_http.py` |

## 输入陷阱

| 编号 | 规则 | 处理 | 测试 |
|---|---|---|---|
| TRAP-02 | 去除 BOM | `app/intake/reader.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-03 | 按逻辑记录读取引号内换行 | `app/intake/reader.py` | `tests/test_intake.py::test_quoted_newline_is_one_logical_record` |
| TRAP-04 | 重复表头计入忽略行 | `app/intake/service.py` | `tests/test_intake.py::test_repeated_header_is_counted` |
| TRAP-05 | 异常列数隔离 | `app/intake/schema.py` | `tests/test_intake.py::test_extra_column_is_isolated` |
| TRAP-06 | 归一化全角数字和千分位 | `app/intake/numeric.py` | `tests/test_intake.py::test_full_width_and_grouping_are_canonical` |
| TRAP-07 | 空值行隔离 | `app/intake/numeric.py` | `tests/test_intake.py::test_sentinel_keeps_row_out_of_total` |
| TRAP-08 | 记录键保留前导零 | `app/intake/schema.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-14 | 冲突版本都进入隔离 | `app/intake/resolve.py` | `tests/test_intake.py::test_duplicate_conflict_removes_both_copies` |
| TRAP-16 | 引号未闭合时拒收文件 | `app/intake/reader.py` | `tests/test_intake.py::test_unclosed_quote_invalidates_source` |
| TRAP-18 | 区分空文件、全空白和仅表头 | `app/intake/reader.py` | `tests/test_intake.py::test_empty_states_have_distinct_causes` |
| TRAP-26 | 拒绝旧版本复核 | `app/review/store.py` | `tests/test_review.py::test_review_optimistic_lock` |
| TRAP-27 | 跨组争议双组暂缓，无争议组照常签发 | `app/intake/disputes.py、app/review/adjudication.py` | `tests/test_disputes.py::test_unaffected_group_can_be_issued_while_disputed_groups_hold` |
| TRAP-28 | 补证改组后任一复算失败则全组暂缓 | `app/review/adjudication.py` | `tests/test_disputes.py::test_failed_recompute_blocks_both_groups` |
| TRAP-29 | 同一争议补证只采信一个版本 | `app/review/store.py` | `tests/test_disputes.py::test_concurrent_supplements_have_single_winner` |
| TRAP-30 | 已签发内容不被落败补证覆盖 | `app/review/service.py` | `tests/test_disputes.py::test_losing_supplement_retry_after_issue_does_not_overwrite` |

## 领域反例

单执行槽，起止为左闭右开整数时隙。依赖通过后，在最早释放点之后找连续空档。可选任务按截止时间再按任务编号调度。没有足够空档和上游无法调度分别记录。策略输出可复算的排程，优先保留紧迫任务。

`sample_data/incoming.csv` 的 0003 组触发预检异常，0004 组触发业务判定。`tests/test_calculate.py` 还核对逐组结论和证据字段。

## 争议与补证裁决

`DUPLICATE_CONFLICT` 的每个记录号登记为一条争议。版本指向多个业务组时为跨组争议，所有涉及组打 `dispute_ids` 标记并同时暂缓——单条记录无法同时归属两组，裁决前任一组都不完整。组级签发只看该组自身的有效判定与阻塞争议：无争议且 READY 的组可独立放行，值班窗口不必因整批争议错过。

补证按 `dispute_id` 提交，胜出行替换争议记录后，在「原始采信行剔除全部争议记录 + 已采信补证行」的有效集合上重算。受影响组为争议原涉及组与补证目标组的并集；只要其中一组复算非 READY，裁决 `accepted=false`，所有受影响组继续暂缓。同一争议的补证以 `(run_id, dispute_id)` 唯一约束裁决，并发提交只落库一条，落败者收到 `SUPPLEMENT_CONTESTED` 且胜出版本不可变；补证触及 `APPROVED` 组时返回 `CASE_FINALIZED`，已签发内容不受任何后续操作覆盖。
