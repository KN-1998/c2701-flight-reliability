# 编程手要求与验收 · v4

## 输入与方法契约
- 只加载来源清楚、哈希核验、行数及月覆盖可审计的月文件；未知结局不填0。取消/改航的结构性无正常到达不能作为普通缺失插补。
- 三个分支风险集与两条主公式严格一致；叶概率非负且和为1；15/60阈值边界测试。
- 计划时刻和事后修订航班表不是自动可得的购票时快照；实际天气、延误归因、实际到达均不得混入事前预测特征。
- 随机种子、抽样上限、正则化候选、每支事件数、警告、拟合/调参/校准/测试月写入输出。工程默认值不是论文规定参数。

## 本轮已交付
1. src/calibration_diagnostics.py：粗10箱、低风险细箱、保留预测同值的分位箱；每箱n/事件/非事件。PAV同样本诊断及Brier分解，**不输出新预报、不产生独立航班置信带**。
2. src/mc_diagnostics.py：按 a,b,mode,threshold_minutes,block_days 一对一合并两次实验，重复键/缺键/半缺区间即失败；输出分位变动和含零分类变化。
3. reproduce_review_v3.py --mc-check 自动生成派生MC表；--predict后生成v4校准诊断。所有输出放全新目录，不能覆盖v3。
4. 预测文件先验契约核对日期、单阈值、状态/完成/联合坏结局、边际质量与风险集；拒绝unknown和已有输出。
5. tests/test_review_v4.py：边界、零事件、同值、PAV单调性、分解恒等式、MC错误配对/抑制区间、四行保存预测集成、非法输入/覆盖保护及MC入口快速失败。

## 复算命令（从仓库根目录；使用新目录）
```powershell
python modeling/src/check_all.py
python modeling/src/reproduce_review_v3.py --out modeling/results/recompute_v4 --snapshot modeling/results/review_v3/primary_snapshot/data_snapshot.json --predict --cap 50000 --reps 1000 --mc-check
```
这会重做较大规模实验，不是只读检查。预测pkl只能由本项目可信本地运行生成，不加载网络来历不明pkl，不纳入公开包。
MC现有结果可单独复算：
```powershell
python modeling/src/mc_diagnostics.py modeling/results/review_v3/comparison_2023/base/pairwise_comparisons.csv modeling/results/review_v3/comparison_2023/mc_2000_seed2702/pairwise_comparisons.csv modeling/results/new_mc/monte_carlo_quantile_changes.csv
```
保存的v3预测缺基线条件分支概率，v4不编造此对比；下一轮要同时保存基线分支，使用各自真实风险集。

## 下一轮必须做但本轮未完成
- 缺月安全下载与全量ZIP覆盖审计，禁止季节性复制凑齐数据。
- 新月份滚动验证，模型选优不得用已经看过的2024-10/2025-01结果做盲测宣称；树/直接模型/历史基线同样本比较。
- Delta独立事件完整复算；来源验证与事件结果分离。
- 分层事件数和不同拟合上限/种子/正则候选，尤其改航罕见事件；不能只报总Brier与0—10%箱。

## 发布门槛
测试通过只证明程序契约。数据PARTIAL_CORE和来源SOURCE_AUDIT_INCOMPLETE不因测试清零。新文件必须进入清单；发布前核哈希；Git只用隔离公开仓库，禁入旧题历史、凭证、个人路径及不明第三方版权全文。
