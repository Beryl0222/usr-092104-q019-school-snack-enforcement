# 领域词汇与事件约定

本文件登记校园跨界零食处置证据链的对象、事件与不变约定。所有事件使用 `domain.schema.json` 定义的信封交换，业务内容放在 `payload` 对象中；本文件只约定关键载荷字段，不限制额外字段。

## 核心对象（aggregate_type）

| 对象 | 说明 |
| --- | --- |
| product_listing | 平台商品链接及其页面证据（截图、快照、标题历史） |
| business_entity | 经营主体（店铺、校园周边小店） |
| manufacturer | 生产企业 |
| license | 食品生产/经营许可证 |
| product_version | 产品与包装版本（同一图案不同配料或许可证须区分版本） |
| physical_lot | 实物批次，身份不随商品标题或链接变化 |
| inspection_sample | 购样、送检与留样，全程交接留痕 |
| test_report | 检测报告，异议产生复检版本 |
| distribution_flow | 流向记录（批次到门店/链接的分销路径） |
| enforcement_action | 执法决定，可精确到链接、门店或批次 |
| public_notice | 面向学校和家长的通知，不暴露购买儿童身份 |
| recall_notice | 召回反馈与统计 |

## 领域事件（event_type）

| 事件 | 适用对象 | 说明与关键载荷 |
| --- | --- | --- |
| LISTING_CAPTURED | product_listing | 留存页面证据。`payload.url`、`payload.title_at_capture`、`payload.evidence_hash` |
| LISTING_REVISED | product_listing | 商家改标题或换链接。`payload.previous_title`、`payload.new_title`；批次身份不变 |
| LISTING_LINKED | product_listing | 跨平台同源关联。`payload.matched_listing_id`、`payload.match_basis`（见约定 4） |
| ENTITY_REGISTERED | business_entity / manufacturer | 登记经营主体或生产企业及其证照关联 |
| LICENSE_VERIFIED | license | 许可证核验。`payload.license_no`、`payload.verified_at`、`payload.result` |
| VERSION_RECORDED | product_version | 记录包装版本。`payload.version_code`、`payload.ingredients`、`payload.license_no` |
| LOT_CLASSIFIED | physical_lot | 食品分类判定。`payload.standard_id`、`payload.standard_effective_at`、`payload.evidence`（见约定 2） |
| CONFLICT_FLAGGED | physical_lot | 系统提示页面标称与实物分类等冲突，仅提示不作决定（见约定 3） |
| SAMPLE_TRANSFERRED | inspection_sample | 抽样、送检、留样的每次交接。`payload.from_party`、`payload.to_party`、`payload.seal_no` |
| REPORT_ISSUED | test_report | 检测报告出具。`payload.report_no`、`payload.conclusion` |
| RETEST_FILED | test_report | 异议复检，产生新版本，原报告保留（见约定 6） |
| FLOW_RECORDED | distribution_flow | 记录流向。`payload.from_node`、`payload.to_node`、`payload.quantity` |
| DECISION_SIGNED | enforcement_action | 执法决定经人工签字生效。`payload.scope` 取 `listing` / `store` / `lot`（见约定 3、7） |
| MERCHANT_INFORMED | enforcement_action | 向商户公开整改或申诉依据 |
| NOTICE_PUBLISHED | public_notice | 向学校和家长发布通知（见约定 8） |
| RECALL_UPDATED | recall_notice | 召回反馈。`payload.recall_status` 四态（见约定 9） |

## 不变约定

1. **批次身份**：商家改标题、换链接不改变 physical_lot 身份；标题与链接变化以 LISTING_REVISED 记入历史，不得新建批次顶替。
2. **分类依据**：LOT_CLASSIFIED 必须依据当时有效标准（`standard_id` + `standard_effective_at`）和实物证据（配料表、包装照片等），不得仅凭商品标题分类。
3. **人工签字**：CONFLICT_FLAGGED 只是系统提示；DECISION_SIGNED 必须由执法人员人工签字，系统不得自动生成或代签。
4. **同源关联**：LISTING_LINKED 必须保留匹配依据（如生产许可证编号、包装版本号、生产企业一致），不得仅凭图片相似自动合并。
5. **交接留痕**：抽样、送检、留样的每次交接各产生一条 SAMPLE_TRANSFERRED，记录交接双方与封存编号，链条不得断档。
6. **复检版本**：对检测结果的异议产生 RETEST_FILED 事件，新报告 version 递增，原报告保留可查。
7. **处置精度**：执法决定可精确到链接（listing）、门店（store）或批次（lot），避免仅凭标题下架误伤合规批次。
8. **隐私保护**：NOTICE_PUBLISHED 不得包含可识别购买儿童身份的信息。
9. **召回统计**：RECALL_UPDATED 的 `recall_status` 取 `notified`（已通知）、`delisted`（已下架）、`returned`（已退回）、`unrecoverable`（无法追回），统计按四态分列。
10. **双向可查**：凭实物批次可回查线上宣传、生产资质、检测与流向；商户可凭 MERCHANT_INFORMED 查看整改或申诉依据。
