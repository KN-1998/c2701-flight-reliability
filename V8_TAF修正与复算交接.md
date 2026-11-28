# C2701 v8 TAF 来源修正与复算

2026 年 11 月 28 日（北京时间）。本交接从 `da21fba` 接续，保留所有已发布的 v7 数据、结果和图。2026 年 1–8 月已在 v7 看过，9 月继续单列。

## 原报、修正与同批复算

从 IEM 档案按完整 WMO/AWIPS/BBB 产品 ID 取回 20 份原始 NWS 报文，核对 49 个常态组。18 个初始组混入了后续 PROB30 条件，另一个 FM 组缺失了报文明确给出的可变方向风速。8 个组仅调整随附文本或能见度比较符，22 个组完整一致。修正保持所有版本身份、发行时间、预报有效期和航班匹配规则。

- [确切组的逐段判决、原值和新值](modeling/data/taf_v8/exact_product_adjudication.csv)及[发行原件与获取指纹](modeling/data/taf_v8/original_products/)。
- [修正影响与配对范围](modeling/results/v8_20261128/corrected_binary/taf_source_impact_pooled.csv)、[逐日探索区间](modeling/results/v8_20261128/corrected_binary/taf_source_impact_date_blocks.csv)。
- 分开做了 23,134 个明确标为 VRB 的缺失风速的附带文本敏感性。每行要求组身份、能见度、云底和天气码相容。按固定哈希规则选了每站两条挑战样本，20/20 个原报核对一致。这组敏感性另行重拟合和校准，保留两套输入身份。详见[规则、抽查和计数](modeling/data/taf_v8/taf_vrb_sensitivity_manifest.json)及[结果](modeling/results/v8_20261128/vrb_sensitivity/taf_source_impact_pooled.csv)。
- 原有异常段之外再核 28 份报文，共 137 个常态组。39 个组另有结构化字段修正，包括 20 个将高空风切变速度误作地面速度的组。扩展版仅根据原报修正对应组，保持匹配身份并另做二分类与共享五叶完整复算。用于后续月的组合档案采用此版本。详见[扩展原报和判决](modeling/data/taf_v8/extended_exact/)和[扩展复算](modeling/results/v8_20261128/extended_exact_binary/)。

下表覆盖 1,373,557 条同批可匹配航段。表中风速敏感性以确切原报修正版本为起点。越低的 Brier 表示平方概率误差越小。

|口径|二分类仅排班|二分类原 TAF|二分类确切修正 TAF|二分类 VRB 敏感性|共享五叶仅排班|共享五叶确切修正 TAF|
|---|---:|---:|---:|---:|---:|---:|
|15 分钟|0.19259831|0.18727482|0.18727169|0.18728227|0.19173701|0.18634979|
|60 分钟|0.10340125|0.10042909|0.10042825|0.10039856|0.10308663|0.10005286|

二分类的确切数据修正使 15 和 60 分钟 Brier 分别变化约 −0.00000313 和 −0.00000084。60 分钟修正幅度的 7 天日期块探索范围跨零。共享五叶的天气增量相对自身排班对照分别为 −0.00538722、−0.00303377。1,407,837 条已知结局航段含 34,280 条无可用 TAF。使用共享排班模型承接这些航段后，整批分差为 −0.00525604、−0.00295990。无可用 TAF 时的模型仍取自共同拟合窗口的可匹配训练池。

按实际入模字段计，两轮原报修正分别影响 19、32 个组。固定 50,000 条拟合子样本中分别有 9、10 条，校准有 362、0 条，1–8 月评估中有 0、1 条与对应修正组直接匹配。末轮扩展修正后的 TAF 二分类 Brier 为 0.18726972 和 0.10042796，共享五叶为 0.18635044 和 0.10005480。与首轮共享结果相比，变化均小于 0.000002，预测选择保持冻结。见[实际暴露](modeling/data/taf_v8/exact_repairs_flight_exposure.json)和[扩展共享结果](modeling/results/v8_20261128/extended_exact_joint/shared_weather_comparison_pooled.csv)。

## 结构保证和剩余风险

取消、改降、正常完成且延误至少 60 分钟、正常完成且延误 15 至不足 60 分钟、正常完成且延误不足 15 分钟构成五个互斥叶。沿用原模型的分支逻辑回归和路径乘积，各分支校准后再相乘。两档风险由同一分布累加得到，未使用排序修正。全量回放的五叶和最大误差为 `4.44e-16`，无负值或阈值倒置。阈值结构通过与模型适用性是两项分别记录的检查。

不利 TAF 下 60 分钟实际 28.22%，修正后独立二分类预测 20.82%，共享五叶预测 20.35%。这组低估照原值报告。分数、压力诊断、秩序检查和分母见[共享模型输出](modeling/results/v8_20261128/joint/)。[新增 MATLAB 图](modeling/figures/v8/fig09_taf_source_and_coherence.pdf)与原结论保留图表索引中的输入口径。

## 复算入口

从仓库根运行，输出目录必须是新目录。二分类原 v7 与 v8 本次拟合均使用 Python 3.13.7、pandas 3.0.2、numpy 2.5.0、scipy 1.17.1、scikit-learn 1.8.0。实际环境也在每次运行状态表中记录，历史版本的依赖锁随原版本保留。

```text
python -B modeling/src/verify_handoff.py
python -B modeling/src/check_all.py --out NEW_TESTS
python -B modeling/src/review_v7_evidence.py --results modeling/results/v7_20261128 --out NEW_V7_EVIDENCE.json
python -B modeling/src/correct_taf_v8.py --out NEW_EXACT_SOURCE
python -B modeling/src/correct_taf_v8.py --segments modeling/data/taf_v8/taf_prevailing_corrected.csv.gz --vrb-sensitivity --out NEW_VRB_SOURCE
python -B modeling/src/run_weather_v8.py --taf modeling/data/taf_v8/taf_prevailing_corrected.csv.gz --out NEW_BINARY
python -B modeling/src/run_weather_v8.py --taf modeling/data/taf_v8/taf_prevailing_vrb_sensitivity.csv.gz --reference NEW_BINARY --out NEW_VRB_BINARY
python -B modeling/src/weather_joint_v8.py --taf modeling/data/taf_v8/taf_prevailing_corrected.csv.gz --corrected-weather NEW_BINARY/taf_monthly.csv --out NEW_FIVE_LEAF
python -B modeling/src/run_weather_v8.py --taf modeling/data/taf_v8/extended_exact/taf_prevailing_corrected.csv.gz --reference NEW_BINARY --out NEW_EXTENDED_BINARY
python -B modeling/src/weather_joint_v8.py --taf modeling/data/taf_v8/extended_exact/taf_prevailing_corrected.csv.gz --corrected-weather NEW_EXTENDED_BINARY/taf_monthly.csv --out NEW_EXTENDED_FIVE_LEAF
python -B modeling/src/audit_taf_repair_exposure_v8.py --out NEW_EXPOSURE_AUDIT
```

冻结月份校验对照原协议，拒绝误归入留出范围的 9 月，以及校准十分箱边界、箱内均值和计数错误。保留正常 v7 的核验报告。

## 下一期实际结果门禁

已经登记 2026 年 10–12 月，训练与校准仍截止于原窗口。10 月十个机场的 TAF 已归档，包含 UTC 发行窗口的前后缓冲以及来源哈希。官方 BTS 页面仍列到 2026 年 9 月，10 月结果文件返回 HTTP 404。未来回放和数据准备见[后续月命令](modeling/docs/V8_PROSPECTIVE_READOUT.md)及[协议](modeling/docs/VALIDATION_V8.json)。评分前还需确认真正的首次接触结果；真实购票排班版本、实收预报时间及 2027 年可迁移性需实际输入。异常事件表现与已有压力测试反例一并保留。

[BTS 数据发布](https://www.transtats.bts.gov/ReleaseInfo.asp) · [IEM NWS 原报档案](https://mesonet.agron.iastate.edu/nws/text.php) · [NWS TAF 规范](https://www.weather.gov/media/directives/010_pdfs/pd01008013curr.pdf) · [OPM 联邦假日日历](https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/)
