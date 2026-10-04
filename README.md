# 校园跨界零食处置

本仓库保存校园跨界零食处置的领域词汇、事件约定与基础校验代码，供相关单位统一对象身份、事件顺序和版本语义。

## 目录

- `contracts/domain.schema.json`：领域事件信封与稳定枚举。
- `contracts/glossary.md`：对象与事件说明、载荷约定及不变规则。
- `data/sample.json`：一条中文联调样例。
- `data/sample_chain.json`：一条覆盖完整证据链的事件序列样例。
- `src/`：事件基础字段校验。
- `tests/`：领域资料一致性检查。

## 证据链对象与事件

核心对象为 product_listing（平台链接与页面证据）、business_entity（经营主体）、manufacturer（生产企业）、license（许可证）、product_version（产品与包装版本）、physical_lot（实物批次）、inspection_sample（购样与留样）、test_report（检测报告）、distribution_flow（流向）、enforcement_action（执法决定）、public_notice（家校通知）、recall_notice（召回反馈）。

已登记事件为 LISTING_CAPTURED、LISTING_REVISED、LISTING_LINKED、ENTITY_REGISTERED、LICENSE_VERIFIED、VERSION_RECORDED、LOT_CLASSIFIED、CONFLICT_FLAGGED、SAMPLE_TRANSFERRED、REPORT_ISSUED、RETEST_FILED、FLOW_RECORDED、DECISION_SIGNED、MERCHANT_INFORMED、NOTICE_PUBLISHED、RECALL_UPDATED。

关键约定：食品分类与添加剂适用性按当时有效标准及实物证据判断；商家改标题不改变批次身份；系统只提示冲突，执法决定须人工签字；跨平台同源关联保留匹配依据，不仅凭图片自动合并；抽样、送检、留样全程交接留痕，异议产生复检版本；处置可精确到链接、门店或批次；家校通知不暴露购买儿童身份；召回统计区分已通知、已下架、已退回、无法追回。详见 `contracts/glossary.md`。

这些资料描述基础交换边界，后续服务应保持事件兼容性：只新增枚举值与对象，不改写或删除已登记词汇。

## 本地检查

```bash
python3 -m unittest discover -s tests
```
