# C2701 v8 TAF 来源修正与复算

从 [v8 复算交接](V8_TAF修正与复算交接.md) 查看原报判决、配对分数、共享五叶和后续月份门禁。MATLAB 第 9 图见 [图表索引](modeling/figures/v8/FIGURE_INDEX.md)。

以下保留历史交接。

---

# C2701 v7 独立复核与来源补查

先读 [本轮交接](V7_独立复核与来源待办交接.md) 与 [两核心公式及证据链](modeling/docs/V7_INDEPENDENT_MODELING_REVIEW_20261128.md)。实际重拟合与21+3表对照通过；新增天气双阈值核验无倒置，但27段TAF字段/文本候选矛盾待原发报核定。**可复算不等于输入已完全核实，未批准实时2027预测或同卡上线。**

[三角色最新要求](modeling/docs/TEAM_REQUIREMENTS_V7_REVIEW_20261128.md) · [本轮测试](modeling/results/v7_review_20261128/tests/TEST_STATUS.json)

下方保留原 v7 及更早历史说明；旧测试数与旧复算边界仅对应当时。

---
# C2701 v7 验证与图表

从 [v7 交接说明](V7_验证与图表交接.md) 查看新的测试月、出发前信息对照和实测证据。
MATLAB 导出的矢量图、高分辨率预览和整表见 [图表索引](modeling/figures/v7/FIGURE_INDEX.md)。

以下为各历史版本的交接记录。

---

> **本机独立验收（2026-11-28）**：94项测试通过，56表重核通过；详见[独立验收与真实边界](V6_核验补丁独立验收_20261128.md)。本次不重新训练或改变模型。

# C2701 v6 存档核验完善

2026-11-28 完成倒置明细的航段键、概率差、逐月和汇总对账。先读[核验完善说明](V6_核验完善说明.md)。旧交接和实测记录见下方。

---

# v6 建模复核增补（2026-11-27）

基于80b953e独立复跑：37个月审计、19个既有留出月、56张CSV对照通过；这是工程复现，不是新增盲测。五叶解决同卡结构倒置但15分钟Brier略差；异常事件与低共同支持覆盖限制保留。

- [新版完整交接入口](V6_建模复核交接.md)
- [当前三角色要求](modeling/docs/TEAM_REQUIREMENTS_V6_20261127.md)
- [两核心公式的五叶逐步推导](modeling/docs/V6_MODELING_DERIVATION_20261127.md)
- [复核结果与环境差异](modeling/results/review_v6_20261127/FINDINGS.md)
- [真实过程和失败记录](modeling/docs/V6_REVIEW_PROCESS_20261127.md)

以下保留原v6及更早版本说明，具体状态以对应版本为准。

---

# C2701 v6 代码交付

本版合并本地 v5 完整实验与 GitHub 4b6a044 的双阈值诊断，并接入三年旅客卡及五叶回顾候选。

- [复算与交接说明](V6_复算与交接.md)
- [实测结果](modeling/results/implementation_v6/DELIVERY_RESULTS.md)
- [三年旅客卡](modeling/results/implementation_v6/traveler_card/TRAVELER_CARD.md)

以下为各旧版本的说明，窗口、数据覆盖和测试数量对应当时的快照。

---

# C2701 航班可靠性建模与验证 v5

2026-11-27 完成 2023–2025 年核心月覆盖、固定模型时间外评分与达美事件正式复算。此次交接以 GitHub v4 快照 b16a0e0 为基础，在独立副本完成。

- [实测结果与口径](modeling/results/validation_v5/FINDINGS_V5.md)
- [复算入口及事件定义](V5_复算说明.md)
- [冻结验证规则](modeling/docs/VALIDATION_V5.json)
- [原始数据与抽取指纹](modeling/results/validation_v5/data_snapshot.json)
- [来源与证据状态](modeling/docs/PROVENANCE_GATE.json)

下方保留了 v3/v4 快照说明，样本量、测试计数和门禁对应当时的版本。

---

# C2701 航班可靠性建模与审查修订

本仓库为 KN-1998 团队的数学建模协作项目，公开的是 **v3实验快照 + 2026-11-27 v4要求与诊断增量**。从已验证的建模手→编程手交接包独立建立，不包含此前其他题目的 Git 历史或删除记录。

## v4新增（2026-11-27）

- [三角色共同要求](modeling/docs/TEAM_REQUIREMENTS_V4.md) 与建模手/编程手/论文手独立验收文档。
- [指标优先评价框架](modeling/docs/EVALUATION_FRAMEWORK_V4.md)、20项候选指标、10项缺失/代理决策。
- [原始资料阅读](modeling/docs/SOURCE_NOTES_V4.md) 与 [O奖论文真实检索/阅读状态](modeling/docs/O_PAPER_READING_V4.md)。
- [v4实际结果和未完成项](modeling/results/review_v4/FINDINGS_V4.md)：旧预测的稀有事件诊断与405行MC复算，不是新留出月验证。
- 仍为 PARTIAL_CORE / SOURCE_AUDIT_INCOMPLETE；未补齐核心月、未完成Delta独立复算、未完成三篇认证O全文精读。

## 先读这几份材料

1. [编程手接手说明](modeling/README_编程手先读.md)
2. [逐项审查回应](modeling/docs/REVIEW_RESPONSE_V3.md)
3. [建模过程与逐步推导](modeling/docs/MODELING_REVISION_V3.md)
4. [公式原文、版本、符号与页码](modeling/docs/FORMULA_PROVENANCE.md)
5. [核心论文全文阅读记录](modeling/docs/PRIMARY_FULL_READING_NOTES_V3.md)
6. [假设、定义及工程选择登记](modeling/docs/ASSUMPTION_REGISTER.csv)
7. [实际结果与结论边界](modeling/results/review_v3/CURRENT_FINDINGS_V3.md)
8. [旅客样卡和监测约定](modeling/docs/TRAVELER_SCORECARD_V3.md)

## 当前真实范围

- **数据：21个月、3,519,884条**十机场出发的 BTS 报送国内计划航段，1条未知结局。2023全年；2024年1—7月及10月；2025年1月。
- **PARTIAL_CORE**：核心36个月仍缺15个月；2026-09未取得。不得表述为2025全年或2027真实预测。
- 主实验冻结快照为 **20个月**，2024-07后来取得，仅审计及打包，未混入已完成实验。实际主测试月为 **2024-10、2025-01**。
- **SOURCE_AUDIT_INCOMPLETE**：54项台账不等于54项假设均获证明。两篇核心原文已全读；未全读辅助论文降级。共同支持区间仍为实验性，不作全体航班严格公平或因果排名。
- **38项测试通过（v4增加13项）**只说明程序、代数、来源记录的一致性，不证明全部统计假设。
- 保留条件树不总优于直接模型/基线的反例、MCO应急窗口失效、低共同支持覆盖、失败检索及未完成事项。

## 安装、核验与复算

建议使用 Python 3.12，在仓库根目录：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r modeling/requirements.lock.txt
.venv/Scripts/python modeling/src/verify_handoff.py
.venv/Scripts/python modeling/src/check_all.py
```

精确锁定本轮主实验样本，在**新的输出目录**复算：

```powershell
.venv/Scripts/python modeling/src/reproduce_review_v3.py --out modeling/results/recomputed_v3 --predict --development --cap 50000 --mc-check --snapshot modeling/results/review_v3/primary_snapshot/data_snapshot.json
.venv/Scripts/python modeling/src/render_review_v3.py --results modeling/results/recomputed_v3
```

完整复算比测试耗时长。去掉 `--snapshot` 将使用包内21个月，范围与原20月实验不同。先做完整性核验，再重算；重算修改受核验文件后的哈希变化属于预期。需要数据审计而暂不拟合时，可使用 `run.py --out 新目录 --skip-comparison --skip-model`。

## 目录

- `problem/`：题面、解析手册与提取文本；冲突以英文题面为准。
- `modeling/docs/`：推导、来源/假设台账、审查回应、编程约定和原件副本。
- `modeling/literature/`：原始研究、已核读官方证据、阅读状态、哈希及获取失败日志。
- `modeling/data/`：已核验的筛选月表及来源元数据；不含全国原始ZIP。
- `modeling/src/`、`modeling/tests/`：参考实现和测试。
- `modeling/results/review_v3/`：实际结果、快照、图表和状态。

## 公开与协作边界

初始v3公开快照将提取审查JSON中的个人本机路径改为包内相对路径；本次v4另增要求、来源审计与诊断代码/结果，不改写审查正文和v3实验结果。公开版重新生成 `CHECKSUMS.sha256`；原始ZIP和原件在原工作区不动。参见 [公开快照记录](PUBLICATION_NOTES.md)。

没有上传登录凭据、环境、缓存、部分下载、pickle或旧项目历史。第三方论文、官方文档及数据保留各自来源与权利；本仓库不对第三方材料授予新的许可证。尚未选定覆盖全部团队原创内容的开源许可证，**公开可见不等于任意再授权**。

协作时在新分支、实验目录和台账中保留修改理由及证据；不得为未获支持的参数补造出处，不覆盖已发表结果来掩盖失败。

---

> **最新反例更新（2026-11-27，晚于ec6c428）**：团队报告v5的19个留出月、3,287,437条中，15直接/60树组合发现1条倒置（9.021% / 9.177%）。分别阈值历史评分保留，但不授权作为同一分布在同卡联合展示。先读[双阈值反例与当前要求](modeling/docs/COUNTEREXAMPLE_RESPONSE_20261127.md)。本助手只收到报告；新增测试为合成数值回归，不是v5全量复算。下文旧两月无倒置结果保留为历史，不外推。

# C2701 航班可靠性建模与审查修订

本仓库为 KN-1998 团队的数学建模协作项目，公开的是 **v3实验快照 + v4要求与诊断 + 2026-11-27验收衔接/阈值审查增量**。从已验证的建模手→编程手交接包独立建立，不包含此前其他题目的 Git 历史或删除记录。

## 当前入口：v5已报告验收，本包是证据衔接增量

- 用户报告v5：36核心月约611万条、2026-09单列；15分钟直接联合/60分钟结局树，同批Brier低于历史基线；达美事件大幅低估，41项测试通过。见 [验收报告分层记录](modeling/docs/V5_ACCEPTANCE_REPORTED_20261127.json)。
- **本轮远端/本机未找到对应v5工件**，不把报告改写为本机复算。本包仍含21个月的v4数据底座；不是v5数据包，也未重做已验收v5。
- [三角色当前要求](modeling/docs/CURRENT_TEAM_REQUIREMENTS_20261127.md)：模型、编程、论文的证据与交付边界。
- [两公式派生的双阈值推导](modeling/docs/THRESHOLD_COHERENCE_20261127.md) 与 [真实过程](modeling/docs/FOLLOWUP_PROCESS_20261127.md)：原式→集合嵌套→一致性诊断；候选五叶适配未训练，不称已提升。
- [实际旧预测检查](modeling/results/followup_20261127/FINDINGS.md)：对v3两月336,224条核身份后检查，三方法及15直接/60树组合均未见倒置；**不是v5新留出验证**。
- 本轮本机测试57项（v4底座38+新增19）；与用户报告的v5 41项是不同版本证据，不可互换。
- [协作状态](modeling/docs/COLLABORATION_STATUS_20261127.json)：本轮查询时两队友均已接受并具有write权限；是有日期的状态快照。

## v4历史增量（2026-11-27，以下不代表对v5的最新判断）

- [三角色共同要求](modeling/docs/TEAM_REQUIREMENTS_V4.md) 与建模手/编程手/论文手独立验收文档。
- [指标优先评价框架](modeling/docs/EVALUATION_FRAMEWORK_V4.md)、20项候选指标、10项缺失/代理决策。
- [原始资料阅读](modeling/docs/SOURCE_NOTES_V4.md) 与 [O奖论文真实检索/阅读状态](modeling/docs/O_PAPER_READING_V4.md)。
- [v4实际结果和未完成项](modeling/results/review_v4/FINDINGS_V4.md)：旧预测的稀有事件诊断与405行MC复算，不是新留出月验证。
- 仍为 PARTIAL_CORE / SOURCE_AUDIT_INCOMPLETE；未补齐核心月、未完成Delta独立复算、未完成三篇认证O全文精读。

## 先读这几份材料

1. [编程手接手说明](modeling/README_编程手先读.md)
2. [逐项审查回应](modeling/docs/REVIEW_RESPONSE_V3.md)
3. [建模过程与逐步推导](modeling/docs/MODELING_REVISION_V3.md)
4. [公式原文、版本、符号与页码](modeling/docs/FORMULA_PROVENANCE.md)
5. [核心论文全文阅读记录](modeling/docs/PRIMARY_FULL_READING_NOTES_V3.md)
6. [假设、定义及工程选择登记](modeling/docs/ASSUMPTION_REGISTER.csv)
7. [实际结果与结论边界](modeling/results/review_v3/CURRENT_FINDINGS_V3.md)
8. [旅客样卡和监测约定](modeling/docs/TRAVELER_SCORECARD_V3.md)

## 本包v3/v4底座的已核实范围（与报告v5分开）

- **数据：21个月、3,519,884条**十机场出发的 BTS 报送国内计划航段，1条未知结局。2023全年；2024年1—7月及10月；2025年1月。
- **PARTIAL_CORE**：核心36个月仍缺15个月；2026-09未取得。不得表述为2025全年或2027真实预测。
- 主实验冻结快照为 **20个月**，2024-07后来取得，仅审计及打包，未混入已完成实验。实际主测试月为 **2024-10、2025-01**。
- **SOURCE_AUDIT_INCOMPLETE**：54项台账不等于54项假设均获证明。两篇核心原文已全读；未全读辅助论文降级。共同支持区间仍为实验性，不作全体航班严格公平或因果排名。
- **v4历史为38项测试通过（增加13项）；本轮为57项**只说明程序、代数、来源记录的一致性，不证明全部统计假设。
- 保留条件树不总优于直接模型/基线的反例、MCO应急窗口失效、低共同支持覆盖、失败检索及未完成事项。

## 安装、核验与复算

建议使用 Python 3.12，在仓库根目录：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r modeling/requirements.lock.txt
.venv/Scripts/python modeling/src/verify_handoff.py
.venv/Scripts/python modeling/src/check_all.py
```

精确锁定本轮主实验样本，在**新的输出目录**复算：

```powershell
.venv/Scripts/python modeling/src/reproduce_review_v3.py --out modeling/results/recomputed_v3 --predict --development --cap 50000 --mc-check --snapshot modeling/results/review_v3/primary_snapshot/data_snapshot.json
.venv/Scripts/python modeling/src/render_review_v3.py --results modeling/results/recomputed_v3
```

完整复算比测试耗时长。去掉 `--snapshot` 将使用包内21个月，范围与原20月实验不同。先做完整性核验，再重算；重算修改受核验文件后的哈希变化属于预期。需要数据审计而暂不拟合时，可使用 `run.py --out 新目录 --skip-comparison --skip-model`。

## 目录

- `problem/`：题面、解析手册与提取文本；冲突以英文题面为准。
- `modeling/docs/`：推导、来源/假设台账、审查回应、编程约定和原件副本。
- `modeling/literature/`：原始研究、已核读官方证据、阅读状态、哈希及获取失败日志。
- `modeling/data/`：已核验的筛选月表及来源元数据；不含全国原始ZIP。
- `modeling/src/`、`modeling/tests/`：参考实现和测试。
- `modeling/results/review_v3/`：实际结果、快照、图表和状态。

## 公开与协作边界

初始v3公开快照将提取审查JSON中的个人本机路径改为包内相对路径；v4增加要求、来源审计与诊断；本轮再增加验收衔接、双阈值推导与旧预测诊断，不改写审查正文和v3实验结果。公开版重新生成 `CHECKSUMS.sha256`；原始ZIP和原件在原工作区不动。参见 [公开快照记录](PUBLICATION_NOTES.md)。

没有上传登录凭据、环境、缓存、部分下载、pickle或旧项目历史。第三方论文、官方文档及数据保留各自来源与权利；本仓库不对第三方材料授予新的许可证。尚未选定覆盖全部团队原创内容的开源许可证，**公开可见不等于任意再授权**。

协作时在新分支、实验目录和台账中保留修改理由及证据；不得为未获支持的参数补造出处，不覆盖已发表结果来掩盖失败。


本轮本机程序测试：**63项全部通过（此前57项＋本轮6项合成回归）**。团队对ec6c428复跑的57项、最初v5报告的41项分别保留，不互相替代。
