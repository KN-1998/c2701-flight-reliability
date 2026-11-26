# C2701 航班可靠性建模与审查修订

本仓库为 KN-1998 团队的数学建模协作项目，公开的是 **2026-11-26 v3 审查修订快照**。从已验证的建模手→编程手交接包独立建立，不包含此前其他题目的 Git 历史或删除记录。

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
- **25项测试通过**只说明程序、代数、来源记录的一致性，不证明全部统计假设。
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

公开版只将提取审查JSON中的个人本机路径改为包内相对路径；不改审查正文、公式、月数据或结果。公开版重新生成 `CHECKSUMS.sha256`；原始ZIP和原件在原工作区不动。参见 [公开快照记录](PUBLICATION_NOTES.md)。

没有上传登录凭据、环境、缓存、部分下载、pickle或旧项目历史。第三方论文、官方文档及数据保留各自来源与权利；本仓库不对第三方材料授予新的许可证。尚未选定覆盖全部团队原创内容的开源许可证，**公开可见不等于任意再授权**。

协作时在新分支、实验目录和台账中保留修改理由及证据；不得为未获支持的参数补造出处，不覆盖已发表结果来掩盖失败。
