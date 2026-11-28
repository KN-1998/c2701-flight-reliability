# C2701 模型评分和压力测试图

图以已验收的 v6 保存表为输入，论文图中文字为英文。三张图都由 MATLAB 从表中读取真实数值，配套 CSV 记录每个图形点或标签的数值。更新图时使用新输出目录，原 v6 表和以前发布的图保持版本记录。

|图|英文图注建议|读取表|
|---|---|---|
|q3_model_brier|Flight-weighted Brier scores on the same 2,592,299 flights across 15 core months. Distances are relative to the historical baseline. Bold labels identify the retained v5 model. Shared five-leaf scores are retrospective.|primary_t15/60 下 joint_pooled_v5.csv、joint_monthly_v5.csv，joint_candidate 下 candidate_joint_pooled.csv、candidate_comparison.csv|
|q3_september_calibration|Observed and forecast failure rates in the September 2024, 2025, and 2026 cohorts. Fitting ended in March 2024 and the calibration period ended in June 2024. Panel axes use different ranges.|primary_t15/60 下 joint_monthly_v5.csv|
|q4_external_event_stress|Observed and model-predicted 60-minute joint failure in the Delta outage and the Orlando EOC activation windows. Adjacent same-weekday calendar controls are descriptive. Their weather conditions are unverified.|primary_t60/external_event_scores.csv|

PDF 为矢量制图，PNG 为 300 dpi（300 像素/英寸）。Brier 图按航班数复算加权均值，五叶输出与归档比较表核对样本数、事件数及行指纹。9 月图只描述总体平均预测与实测率的差，三个月的离散点以线连接帮助阅读。事件图核对三个方法的样本数、观察事件数和事件期取消数，事件与日历对照分开使用各自分母。三图均用已查看的历史留出结果，未将后续新月份用于模型选择。

## MATLAB 复算

在 MATLAB 工作目录中运行以下命令，将输入路径换成 v6 的 implementation_v6 或同口径重放结果目录，将输出路径换成新的目录。

    make_model_figures("path/to/implementation_v6", "path/to/figures")

脚本也支持 MATLAB 的 -batch 入口。运行环境与源表相对路径记录于 model_figures_matlab_run.json。七个输入表的校验指纹见 MODEL_FIGURE_INPUTS.sha256。

