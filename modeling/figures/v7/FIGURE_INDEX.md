# C2701 MATLAB 图表索引

以下图表均使用 MATLAB R2025a 从仓内实测 CSV 导出。PDF 用于论文排版，PNG 用于预览。文件名中的序号对应以下图注。

|序号|主题|口径|
|---|---|---|
|01|可靠性分母与阈值|2023–2025 十机场，正常完成条件与全部计划航段分别展示。|
|02|机场构成和共同支持|原始、支持内和标准化比较，适用航段覆盖同时展示。|
|03|历史旅客记分卡|EWR/LGA 飞往 DEN，报告池化与年度共同支持。|
|04 q3_model_brier|已见 v6 选模月份 Brier|原 15 个新增核心月用于选择，按航段加权分差。|
|05 q3_september_calibration|三个 9 月的校准漂移|同一固定模型的各月观察与预测，不等于模型更新。|
|06 q4_external_event_stress|外部异常事件|达美 CrowdStrike 与 MCO 应急窗口，使用原冻结三模型和日历控制。|
|07|后补八个月的冻结评分|2026 年 1–8 月为本轮新增；竖虚线右方为已经查看的 9 月。上排是相对历史基线，下排是原入选模型平均预测与观察。|
|08|出发前 TAF 的信息增量与压力|A 为相同可匹配航段的 Brier 差与 7 天配对区块探索区间。B 为 60 分钟已发行不利预报与联邦假日窗口之条件风险，两种分组可重叠。|

前六图的细图注与源表见 HISTORICAL_FIGURE_SOURCES.md 和 README_model_figures.md。第 7–8 图使用 v7 的冻结月份与 TAF 实验。附带 MATLAB 导出的评分、区间、压力组与覆盖 CSV。

## English captions for the v7 figures

**Figure 7. Frozen-model follow-up.** January–August 2026 include 1,407,837 newly scored scheduled legs with known outcomes. September 2026, to the right of the dotted line, was previously inspected. The top panels show flight-level Brier score differences from the same historical grouping baseline. The bottom panels compare observed proportions and the fixed forecasts selected in v6. No re-selection uses these scores.

**Figure 8. Incremental predeparture forecast information.** Both models are scored on the same time-eligible flights with a usable origin terminal forecast. Panel A shows the paired Brier change and descriptive seven-day block ranges. Panel B shows 60-minute joint disruption rates for four forecast- and calendar-defined groups. Adverse and non-adverse-signal categories are distinct from the overlapping holiday classification. Schedule fields are reporting-time proxies; see the coverage table for network generalization.

在 MATLAB 中从仓库根目录调用以下命令，指定新输出目录。

    addpath('modeling/figures/v7')
    render_historical_figures('modeling/results/implementation_v6','new_figures')
    make_model_figures('modeling/results/implementation_v6','new_figures')
    render_v7_followup('modeling/results/v7_20261128','new_figures')
