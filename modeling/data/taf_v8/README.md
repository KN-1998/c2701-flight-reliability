# v8 TAF 来源核对与派生输入

本轮按 WMO 报头、AWIPS ID、修订码、站点及有效时间核对 NWS 发报原文。两轮核对共保存 48 份 IEM 原报文及其 SHA‑256 来源记录。每份报文的初始组和 FM 组独立解析，TEMPO 和 PROB 条件另行分组。 [IEM NWS 文本档案](https://mesonet.agron.iastate.edu/nws/text.php) · [NWSI 10-813](https://www.weather.gov/media/directives/010_pdfs/pd01008013curr.pdf)

|版本|来源与范围|主要证据|
|---|---|---|
|原始核对|针对 v7 标记的 20 份原报文，核对 49 个常态段。19 个段修正实际模型输入，8 个段仅调整附带文本或能见度限定符。|[逐段对照](exact_product_adjudication.csv) · [清单](taf_correction_manifest.json)|
|补充核对|用原始核对后的 362,285 个段筛查组标记和各项结构化字段，再查另 28 份原报文的 137 个常态段。20 个段的归档地面风速与高空风切变速度混淆，12 个段从原文恢复缺失风速，另有 7 个段修正对本模型影响为零的天气码。|[筛查清单](extended_exact/diagnostic_inventory.csv) · [逐段对照](extended_exact/exact_product_adjudication.csv) · [清单](extended_exact/taf_correction_manifest.json)|
|风速敏感性|以原始核对版本为起点，核对组起点、云底、能见度、天气码及已记录阵风后，从归档附带文本恢复 23,134 个段的缺失 VRB 地面风信息。另取每站 2 个预先选定的样本，20 个样本的原报文风速和阵风均支持恢复值。|[敏感性清单](taf_vrb_sensitivity_manifest.json) · [来源抽查](vrb_source_challenge/CHALLENGE_RECEIPT.json)|

三个输入沿用 v7 的产品清单、航班匹配和发行时间规则。风速敏感性与补充核对是从同一原始核对版本派生的两个独立数据版本。原始报文核查仍限于上述产品与抽查样本。实际接收时间与购票版本排班需另行取证。

[航段暴露表](exact_repairs_flight_exposure.json)只计入改变模型输入的预报段。训练样本计数按 v7 固定随机种子在相同的 2,415,385 条匹配航段上重建 50,000 个有序样本位置，并核对受影响月份的匹配计数与偏移。

## 从仓库根目录复算

以下命令使用独立空目录，默认从包内读取原始核对的 20 份报文。

    python -B modeling/src/correct_taf_v8.py --out NEW_EXACT
    python -B modeling/src/correct_taf_v8.py --out NEW_EXACT --vrb-sensitivity
    python -B modeling/src/correct_taf_v8.py --segments NEW_EXACT/taf_prevailing_corrected.csv.gz --out NEW_EXTENDED --screen
    python -B modeling/src/correct_taf_v8.py --segments NEW_EXACT/taf_prevailing_corrected.csv.gz --flags NEW_EXTENDED/diagnostic_inventory.csv --raw modeling/data/taf_v8/extended_exact/original_products --out NEW_EXTENDED

各前后对照中的资料字段按原文解码，P6SM 沿用 v7 的 6.01 数值编码，语义为大于 6 英里。CSV 压缩包可按两份来源清单核对 SHA‑256。
