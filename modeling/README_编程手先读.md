# C2701 v6 复算入口

从仓库根目录按[交接说明](../V6_复算与交接.md)运行。三年历史样卡和两个阈值的实测分别见[结果摘要](results/implementation_v6/DELIVERY_RESULTS.md)。

以下为旧版本记录。

---

# C2701 v5 编程交接

从 [v5 复算说明](../V5_复算说明.md) 运行完整数据审计、评分和事件回测。对照 [实测结果](results/validation_v5/FINDINGS_V5.md) 与 [冻结规则](docs/VALIDATION_V5.json) 核查测试月份、同航段评分与选模。

以下为 v3/v4 快照说明，供复现对应历史结果。

---

> **2026-11-27 v4补充（旧文以下保留为历史）**：先读 `modeling/docs/TEAM_REQUIREMENTS_V4.md` 及三个角色独立要求；实际新增见 `modeling/results/review_v4/FINDINGS_V4.md`。新版仅增加要求、指标/来源审计与旧预测诊断，不新增留出月份。测试当前状态以 `modeling/results/TEST_STATUS.json` 为准，数据/来源门禁仍未通过。引用路径均相对仓库根目录。

# 编程手先读：C2701审查修订交接 v3

日期：2026-11-26。**已修复真实比较故障、补充真数据时间外对照和可追溯建模过程；不是所有统计假设均已获证的最终论文。**

## 状态与范围

- PARTIAL_CORE：21个月、3,519,884条十机场出发记录；核心36月尚缺15月。具体月份与指纹见data/manifest.json。
- SOURCE_AUDIT_INCOMPLETE：P1/P2两条相连原式已核读，54项假设/口径/默认登记；区块条件、工程参数和信息时间戳仍有缺口。
- 25项程序/代数/来源回归测试通过，不能当“所有假设已验证”。
- 比较只在共同支持下解释；主2023基础覆盖MCO23.61%、HNL98.92%，不得发全体航班严格公平排名。

## 先读顺序

1. docs/REVIEW_RESPONSE_V3.md：逐项审查回应与实际完成状态。
2. docs/MODELING_REVISION_V3.md：围绕两原式从问题到推导、假设、检验和结论边界。
3. docs/FORMULA_PROVENANCE.md、DERIVATION_LOG.md、ASSUMPTION_REGISTER.csv：原式准确页码/版本、真实查找顺序、失败与缺口。
4. results/review_v3/CURRENT_FINDINGS_V3.md：真实比较、分母例子、去DEN样卡和三模型分数。
5. docs/PRIMARY_FULL_READING_NOTES_V3.md：P1/P2全篇核读发现；CAL2005/SCORE2007/T0未完成全读，只按书目核验候选。
6. docs/TRAVELER_SCORECARD_V3.md：条件式旅客样卡、监测频率及未验证触发方案。
7. docs/CODER_SPEC.md、FIRST_HOUR.md：接口、复算和后续验收。
8. docs/MANUAL_ERRATA_V3.md：解析手册勘误，未覆盖改写用户原件。

## 复算

在解压后的根目录，使用已安装requirements.lock.txt依赖的Python：

```powershell
python modeling/src/verify_handoff.py
python modeling/src/check_all.py
python modeling/src/reproduce_review_v3.py --out modeling/results/recomputed_v3 --predict --development --cap 50000 --mc-check --snapshot modeling/results/review_v3/primary_snapshot/data_snapshot.json
python modeling/src/render_review_v3.py --results modeling/results/recomputed_v3
```

上述命令锁定本轮20月primary快照。交接包另含后来取得的2024-07，共21个月；7月仅通过最终审计，未插入已经完成的primary或后续航段实验。去掉--snapshot将使用包内全部月份，属于新的21月复算范围，不应宣称与原实验样本完全相同。复算会创建新目录，不覆盖旧结果。完整重算比单元测试耗时长。独立入口run.py也可按任务开关运行；预测不再因比较故障或36个月未齐而整体等待。

```powershell
python modeling/src/run.py --out modeling/results/new_primary --skip-comparison --fit-cap 50000
python modeling/src/reproduce_v2_failure.py
```

第二条是旧版本故障反例，不是当前模型入口。缺月可用fetch_bts.py或fetch_bts_ranges.py补取；后者验证Range/ETag/字节长度和ZIP CRC后才发布月表。

## 写作禁区

15分钟与60分钟是不同目标；计划字段不是已验证订票快照；MCO应急激活不是全机场关闭；测试Y选尾日不能证明独立低估；同特征不等复杂度；bootstrap频率不是后验概率；任意2027倍率默认停用。支持不足者须补证、缩小或撤回，不能用更多迭代强行“证明”。

本包不含全国原始ZIP、环境、缓存、pickle模型/预测、凭据或挑战HTML；包含筛选月表与指纹、原始研究PDF、核读官方证据、来源失败日志、审查原件、代码与真实结果。v1/v2 ZIP保持原样。

---

> **最新反例更新（2026-11-27，晚于ec6c428）**：团队报告v5的19个留出月、3,287,437条中，15直接/60树组合发现1条倒置（9.021% / 9.177%）。分别阈值历史评分保留，但不授权作为同一分布在同卡联合展示。先读[双阈值反例与当前要求](docs/COUNTEREXAMPLE_RESPONSE_20261127.md)。本助手只收到报告；新增测试为合成数值回归，不是v5全量复算。下文旧两月无倒置结果保留为历史，不外推。

> **2026-11-27当前衔接说明**：先读 `modeling/docs/CURRENT_TEAM_REQUIREMENTS_20261127.md`。用户已报告v5验收，但对应数据/脚本尚未在本机及远端检出。本包是v4可核实底座上的公式与交接增量，不是v5数据包。新增双阈值检查仅针对v3旧两月；本机57项测试≠复跑v5的41项。以下各版缺月与结论均为当时历史记录，不作为对已验收v5的最新否定。

> **2026-11-27 v4补充（旧文以下保留为历史）**：先读 `modeling/docs/TEAM_REQUIREMENTS_V4.md` 及三个角色独立要求；实际新增见 `modeling/results/review_v4/FINDINGS_V4.md`。新版仅增加要求、指标/来源审计与旧预测诊断，不新增留出月份。测试当前状态以 `modeling/results/TEST_STATUS.json` 为准，数据/来源门禁仍未通过。引用路径均相对仓库根目录。

# 编程手先读：C2701审查修订交接 v3

日期：2026-11-26。**已修复真实比较故障、补充真数据时间外对照和可追溯建模过程；不是所有统计假设均已获证的最终论文。**

## 状态与范围

- PARTIAL_CORE：21个月、3,519,884条十机场出发记录；核心36月尚缺15月。具体月份与指纹见data/manifest.json。
- SOURCE_AUDIT_INCOMPLETE：P1/P2两条相连原式已核读，54项假设/口径/默认登记；区块条件、工程参数和信息时间戳仍有缺口。
- 25项程序/代数/来源回归测试通过，不能当“所有假设已验证”。
- 比较只在共同支持下解释；主2023基础覆盖MCO23.61%、HNL98.92%，不得发全体航班严格公平排名。

## 先读顺序

1. docs/REVIEW_RESPONSE_V3.md：逐项审查回应与实际完成状态。
2. docs/MODELING_REVISION_V3.md：围绕两原式从问题到推导、假设、检验和结论边界。
3. docs/FORMULA_PROVENANCE.md、DERIVATION_LOG.md、ASSUMPTION_REGISTER.csv：原式准确页码/版本、真实查找顺序、失败与缺口。
4. results/review_v3/CURRENT_FINDINGS_V3.md：真实比较、分母例子、去DEN样卡和三模型分数。
5. docs/PRIMARY_FULL_READING_NOTES_V3.md：P1/P2全篇核读发现；CAL2005/SCORE2007/T0未完成全读，只按书目核验候选。
6. docs/TRAVELER_SCORECARD_V3.md：条件式旅客样卡、监测频率及未验证触发方案。
7. docs/CODER_SPEC.md、FIRST_HOUR.md：接口、复算和后续验收。
8. docs/MANUAL_ERRATA_V3.md：解析手册勘误，未覆盖改写用户原件。

## 复算

在解压后的根目录，使用已安装requirements.lock.txt依赖的Python：

```powershell
python modeling/src/verify_handoff.py
python modeling/src/check_all.py
python modeling/src/reproduce_review_v3.py --out modeling/results/recomputed_v3 --predict --development --cap 50000 --mc-check --snapshot modeling/results/review_v3/primary_snapshot/data_snapshot.json
python modeling/src/render_review_v3.py --results modeling/results/recomputed_v3
```

上述命令锁定本轮20月primary快照。交接包另含后来取得的2024-07，共21个月；7月仅通过最终审计，未插入已经完成的primary或后续航段实验。去掉--snapshot将使用包内全部月份，属于新的21月复算范围，不应宣称与原实验样本完全相同。复算会创建新目录，不覆盖旧结果。完整重算比单元测试耗时长。独立入口run.py也可按任务开关运行；预测不再因比较故障或36个月未齐而整体等待。

```powershell
python modeling/src/run.py --out modeling/results/new_primary --skip-comparison --fit-cap 50000
python modeling/src/reproduce_v2_failure.py
```

第二条是旧版本故障反例，不是当前模型入口。缺月可用fetch_bts.py或fetch_bts_ranges.py补取；后者验证Range/ETag/字节长度和ZIP CRC后才发布月表。

## 写作禁区

15分钟与60分钟是不同目标；计划字段不是已验证订票快照；MCO应急激活不是全机场关闭；测试Y选尾日不能证明独立低估；同特征不等复杂度；bootstrap频率不是后验概率；任意2027倍率默认停用。支持不足者须补证、缩小或撤回，不能用更多迭代强行“证明”。

本包不含全国原始ZIP、环境、缓存、pickle模型/预测、凭据或挑战HTML；包含筛选月表与指纹、原始研究PDF、核读官方证据、来源失败日志、审查原件、代码与真实结果。v1/v2 ZIP保持原样。
