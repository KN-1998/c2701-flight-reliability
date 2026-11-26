> 2026-11-27新增：先读 TEAM_REQUIREMENTS_V4.md 及对应角色要求；本文件保留既有契约，v4增量见 EVALUATION_FRAMEWORK_V4.md 与 VALIDATION_PLAN_V4.md。

# 编程手实现与验收合同 v3

## 输入与接口

从data/bts_YYYY_MM.csv.gz及匹配JSON读取。先核SHA256和筛选行数，再audit；不同月原始ZIP来源与指纹保留。不得把全国ZIP缺席说成已经从最原始字节完整复算；包内复算起点是筛选月表。

run.py支持--out新目录、--skip-comparison、--skip-model、--prediction-plan、--prediction-threshold、--comparison-threshold、--fit-cap、--reps。默认不覆盖已有结果。execute_tasks分别记录错误，继续其余独立任务；最后非零退出供调度识别。

src/reproduce_review_v3.py是便携复算入口，不依赖本地pickle缓存；--snapshot可锁定包内primary_snapshot/data_snapshot.json，避免新下载月份改变实验清单；--predict --development --cap 50000 --mc-check对应本轮实验选择。

## 必须保留的数学与审计断言

1. 互斥结局计数闭合；重复、冲突和无法判定原因逐月保留；未知不填0。
2. 条件风险集正确：全部已知/非取消/正常完成。三无条件概率不能套路径乘积。
3. 四叶概率非负且和为1；联合坏率为满意补集。每张预测表带threshold_minutes，t=15/60分开。
4. 源字段2400标志保留，分钟编码可为0；不据此擅改FlightDate或断言真实跨日语义。
5. 改航最终抵达与正常完成分开，DivArrDelay不回填ArrDelay。
6. D7三项分解残差<1e-12只是浮点代数验收，不证明因果或模型正确。

## 比较输出

comparison_status、standardization_cells、standard_population_weights、common_support_coverage、cell_day_exposure、resampling_calendar_episodes、bootstrap_diagnostics、empty_cell_frequencies、rank_intervals、pairwise_comparisons和mix_decomposition。

cell_day_exposure的等计数天数不是独立有效样本量。pairwise中prob_a_better只表示bootstrap重复内差值为正的频率，不是后验概率。支持定义/参考构成变化必须另目录，不能拼成一个“稳健调整排名”。若区间被抑制不得补0。

## 预测输出

prediction_status、tuning、prediction_metrics、calibration_bins、paired_prediction_loss；外加分支可靠性/分组错误报告。每期三模型joint测试n/events/hash必须相同。拟合、调参、校准、测试互不越界；clip、C、上限、样本事件数和收敛警告明示。未知排除率及样本范围不能藏起来。

同特征≠同参数预算；基线退回全局的未见格比例须披露。预测pkl只供本地串联，不作为可信外来文件打开，不收入交接包；编程手从可信月表重算。

## 外部事件与尾日

MCO窗口仅源机场MCO、2024-10-09/10；EXTERNAL_EVENTS配置保留出处、地方日期、对照和后验选择史。外部事件测试必须是独立预测留出；无事件留出行写NO_HELDOUT_EVENT_ROWS，不编造分数。日历对照不是已核实正常天气，匹配覆盖单报。按测试Y选尾日显式RETROSPECTIVE_OUTCOME_SELECTED。

## 下一轮真正待做

补缺月；扩大训练上限/多seed、校准与季节迁移敏感性；取得区块方法原作并验证条件；取得订票时排班/取消通知/天气发布时延；补事件和对照天气、技术指令31/39；完善真正2027排班或有依据情景。不得把这些未完成项写成已验收。
