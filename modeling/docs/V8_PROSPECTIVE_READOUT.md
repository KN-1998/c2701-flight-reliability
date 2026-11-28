# 2026 年 10 月起的前瞻回放

2026-11-28 核查官方发布页及目标 ZIP。10 月结局未取得。10 月 TAF 发行档案已从 IEM 获取，十站 Q/C 通过。文件 [taf_2026_10_extension](../data/taf_2026_10_extension/) 保留单独标准化输出、获取记录和组合档案的指纹。

先确认 [BTS 正式发布](https://www.transtats.bts.gov/ReleaseInfo.asp)。保留官方 ZIP、初次取得时间和指纹，冻结设置保持 [VALIDATION_V8.json](VALIDATION_V8.json) 与原 v7 协议。把新月源数据转成与 `modeling/data` 同结构的筛选 CSV 及来源 sidecar；在独立的 `SCORING_DATA` 目录保留原项目历史输入。结果只在获取后回放。

```text
python -B modeling/src/extend_taf_v8.py --extension modeling/data/taf_2026_10_extension --out OCTOBER_TAF
python -B modeling/src/run_weather_v8.py --data SCORING_DATA --prospective-month 2026-10 --taf OCTOBER_TAF/taf_prevailing_normalized.csv.gz --taf-products OCTOBER_TAF/taf_products_normalized.csv.gz --out OCTOBER_BINARY
python -B modeling/src/weather_joint_v8.py --data SCORING_DATA --prospective-month 2026-10 --taf OCTOBER_TAF/taf_prevailing_normalized.csv.gz --taf-products OCTOBER_TAF/taf_products_normalized.csv.gz --out OCTOBER_FIVE_LEAF
```

入口的前瞻模式仅接受已登记的 10–12 月，核查原 v7 规则的指纹，不允许把 1–9 月当作前瞻样本。10 月组合以 UTC 10 月 2 日为接缝，在十个机场检查接缝前后连续性。对于 11、12 月，按带缓冲的日期区间使用 `download_taf.py --date-range START STOP --out NEW_RAW`、`normalize_taf_fast.py --raw NEW_RAW --out NEW_NORMALIZED` 和 `check_taf.py NEW_NORMALIZED --expected-months 2026-11`（或对应月份），再以最新可用旧档案和新的接缝组合。记录新档案缺失、修订和正向风险，保留发行时间和适用时间。按月报告评分、校准、非匹配范围与 TAF/排班两种信息条件。共享五叶全量输出在不可匹配时使用同一排班模型。

全月评分是否真正未见结局仍由外部获取记录确认。起飞前的排班字段只来自 BTS 报送代理。真实购票时点需可订版本及预报接收时间，仍无充分数据。
