# C2701 航班计划与历史气象输入核验

核验日期 2026-11-28（Asia/Shanghai）。本目录获取气象与公告产品，未读取新留出月的航段结局或模型成绩。

## 这轮可用的数据

NWS Terminal Aerodrome Forecast（TAF）是近出发时可用的机场天气预报，描述机场跑道区中心约 5 statute miles 内预期条件，通常有效 24 小时，部分机场 30 小时。Iowa State University 的 IEM 提供 NWS 原发报产品的公共历史再分发。IEM 逐段数据及产品元数据本身不同于原发报的实际用户接收日志。原始定义与服务文档见 [NOAA AWC 产品说明](https://aviationweather.gov/help/data/)、[IEM TAF 下载](https://mesonet.agron.iastate.edu/request/taf.php)、[IEM API 参数](https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py?help=)。

- 取样训练期 2023-01 至 2024-06，验证可用期 2026-01 至 09，UTC 查询首尾留出数日，以容纳本地日期差和跨日有效期。精确查询和源 SHA-256 见 taf_raw/download_manifest.json。
- 十站用 ICAO 明确标识。ATL→KATL、DEN→KDEN、DFW→KDFW、EWR→KEWR、HNL→PHNL、LGA→KLGA、MCO→KMCO、ORD→KORD、SEA→KSEA、SFO→KSFO。省略 PHNL 的 P 起始会误找 KHNL。
- 版本元数据按站取，至少有 utc_issued、utc_issue、utc_expire、product_id。utc_issued 是发行；尽管名字相近，utc_issue 是预报有效开始。用站和产品号配上逐组预报；产品号开头是 WMO 头的 UTC 分钟。直接向当局 AWC API 查询只能返回近 30 天历史。历史 NOAA 可向 NCEI SRRS/AIRS 请求，网页目录未逐月验证。见 [IEM 单站历史接口示例](https://mesonet.agron.iastate.edu/api/1/nws/taf_overview.json?station=KSEA&sts=2026-09-01&ets=2026-09-02)、[NOAA AWC API](https://aviationweather.gov/data/api/)、[NOAA AWC 历史入口](https://www.connect.aviationweather.gov/tools/archive/)。
- 产品和预报段区间使用 UTC ISO8601。availability 取存档发行、WMO 报头、逐段数据发行的最晚时点；额外至少 30 分钟为保守延迟假设，不代表能证明当时的旅客收到公告。

## 复用与审计

    py -3.13 -B modeling/src/download_taf.py --out taf_raw
    py -3.13 -B modeling/src/normalize_taf_fast.py --raw taf_raw --out taf_normalized_fast
    py -3.13 -B modeling/src/check_taf.py taf_normalized_fast

下载脚本最多两请求并行，按站和有界日期分开，请求成功后校验状态、体量/字段、站范围、首末记录与 SHA-256。重试会复用校验后的完整文件。归一化须保留两个表。

|文件|关键信息|
|---|---|
|taf_products_normalized.csv.gz|一条产品版本的 station、product_id、issued_utc、available_utc、product_valid_from_utc、product_valid_to_utc、is_amendment、product_status、has_tempo_or_prob|
|taf_prevailing_normalized.csv.gz|按产品列附 valid_from_utc、valid_to_utc、visibility_sm、visibility_relation、ceiling_ft_agl、ceiling_status、wind_speed_kt、gust_kt、weather_codes、segment_kind、source_forecast_text|
|taf_normalization_manifest.json|匹配异常、可用/不可用产品计数、站码覆盖、归一化表 SHA-256|

按始发地 IANA 时区把 BTS 计划时间代理转换到 UTC，先根据预设的 120 min 决策时距及 30 min 发行缓冲挑选最新已经发布的产品，再检验预报时段是否覆盖计划起飞。失效、缺失、同分钟顺序无法核定或被取消的产品明确记不可用，将该航段保留于覆盖率总分母及全样本主模型评分。TAF 配对消融评分只纳入同一批可合并到有效预测段的航段，并单报其覆盖与样本构成。不要寻找被更新产品替换的旧版本来抬高覆盖。BTS 的午夜编码为 2400 时另设时间解释记录；夏令时跳变、不明时区或时间歧义单独处置。气象档案仅核查始发站的 TAF；抵达站、航路、乘客收到天气的时刻都未进入验证。

IEM 对 TAF 初始 prevailing 预报段的内部标签是 Observation，其文本与 FAA/NWS 所指的例行 TAF 初始时段一致，并非 METAR 实况。FM 组从自身 UTC 起点到下一 FM 或到产品失效。TEMPO/PROB 留存存在标记但不覆盖 prevailing，不提供临时/条件天气改善的证据。有不符合该归一化方案的 BECMG 则产品留存并标不可用。能见度的 P6SM 在 IEM 存为 6.01 及 greater_than，作为 6 英里以上这一等级的数值编码进入模型，不能把 6.01 当精确英里读数。ceiling 为 BKN/OVC/VV 的最低有效英尺 AGL，状态 none 与 unknown 分开。同一产品存在但字段无法解析时保留缺失。见 [AWC TAF 组定义](https://aviationweather.gov/help/data/)、[IEM 解析器源码](https://github.com/akrherz/pyIEM/blob/main/src/pyiem/nws/products/taf.py)。

## 其他候选与可获得性

- 真实版本化排班有商业来源。OAG Flight Info Direct 给 FILE_DATE，表示一份截至该日的前瞻排班快照，订阅决定获取频率；是否覆盖 2023–2026 目标日期的每个所需 vintage 应由采购样表验证。Cirium 官方称历史排班需联系；确认是否有同样可保留的发布时间及版本。当前尚未取得免费完整历史购票版本和旅客购票行为记录。普通历史航班状态或BTS历史报送计划并未提供该购票时点版本。见 [OAG 版本说明](https://knowledge.oag.com/docs/what-is-a-schedule-snapshot-file-date)、[Cirium 历史排班](https://developer.cirium.com/apis/data/overview)。
- FAA ATCSCC 公开历史日列表可提取 SEND TIME。实测 2025-01-09 有65条、2026-09-07 有131条，单条可见机构/地点、EVENT TIME、地面管控、变更和取消。技术设计需按公告发送时间、活动区间及修订链做 as-of，区别已启动与可能启动、目标机场与受影响航班。当前两个日期探测未验证范围内完整性、机器批量权限或旅客接收条件。已保留原始样例。见 [官方查询入口](https://www.fly.faa.gov/adv/advAdvisoryForm)、[2026-09-07 示例](https://www.fly.faa.gov/adv/adv_list?whichAdvisories=ATCSCC&advisoryCategory=All&date=2026-09-07)、[ATCSCC公告示例](https://www.fly.faa.gov/adv/adv_otherdis?adv_date=01092025&advn=30)、[FAA ASPM 数据说明](https://aspmhelp.faa.gov/index/ASPM_Advisories.html)。
- OPM 联邦节假日可做事前日历暴露标签。当地出发日的邻近日窗口及是否采用法定日期或联邦雇员补休日期须事先定。它只指示日历暴露，不证明当日客流激增，实际安检客流只能用于事后核查或目标已可得的滞后来量。见 [OPM Federal Holidays](https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/)。
- METAR/ASOS 的历史观测适于事件成因线索和天气验证。如用于预出发输入，使用截止前已发布的最近观测，别把起飞时间附近实际观测当作早两个小时已有的预报。仅存观测分钟的清洗表通常无法确认发布时间/修订时点，宜回到原报头或明确保守假设。见 [NOAA AWC 产品说明](https://aviationweather.gov/help/data/)、[IEM METAR 档案](https://mesonet.agron.iastate.edu/request/download.phtml)。



