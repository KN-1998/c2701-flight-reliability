# v4 原始资料阅读记录

## CORP2020：原始研究，不是二手教程
Dimitriadis, T.; Gneiting, T.; Jordan, A. I. Evaluating probabilistic classifiers: Reliability diagrams and score decompositions revisited. arXiv:2008.03033v1，2020，16页；PDF首页标August10及arXiv Aug7，保留版本，不冒充已核验期刊版。
https://arxiv.org/pdf/2008.03033v1
本轮由重点页开始，再补读余页和附录/参考文献；时间在旧实验之后，部分在诊断代码初版之后，不能写为事前设计。PDF SHA256见SOURCE_NOTES_V4.json。
- pp1—2：校准定义和分箱不稳定；pp3—4图1/2展示不同箱的差异。
- p5 §3：单调CEP下PAV的唯一等距回归解；同值概率合并，水平段事件频率，正则假设是单调而非天然真理。
- p6：共同分布等条件下渐近描述；不自动适用于航班网络时序。
- pp7—8 §4：一致性带与置信带区别；p8明确独立或至少可交换条件，相关场景需进一步研究。
- p9 Table1：Brier=(x−y)^2；logarithmic=−ylogx−(1−y)log(1−x)，Eq(1)样本均分。
- p9 Eq(2)—(3)：原预测均分SX、PAV校准均分SC、边际频率参考均分SR；MCB=SX−SC，DSC=SR−SC，UNC=SR，SX=MCB−DSC+UNC。
- p10：解释非负性及例子，适当评分不等于某特定模型在本题最好。
- pp11—12 AppendixA/B：模拟条件及CEP单调/光滑等效率条件，不能移植为航班假设的证据。
- pp13—14 AppendixC：Theorem1有限样本分解性质、Theorem2与传统分解相等的条件；不是校准在测试后重拟合就能提高未来技能。
- pp14—16参考文献：PAV起源1955等仅为本论文的引文，未逐一直接阅读，不能写成已读这些原作。

本题适配：冻结v3概率不变，增加低概率事件计数、三种分箱与PAV描述；不发i.i.d.置信带，不把同样本拟合的Brier下降当泛化改善。辅助诊断不是新增核心预测公式。

## BTS官方字段字典
https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ
读取已存review_v3/BTS_FIELDS.html具体字段行：ArrDelay负值表示早到；ArrDelayMinutes早到归0；ArrDel15是≥15分钟；Cancelled/Diverted指标；WeatherDelay是报送原因分钟。定义可信不自动补齐月份或全国报送范围，本轮重抓官方页仍有网络失败。

## Delta公司投资者关系原始披露
Delta Air Lines Announces September Quarter 2024 Financial Results (2024)，Financial Impact Of The CrowdStrike-Caused Outage小节。
https://ir.delta.com/news/news-details/2024/Delta-Air-Lines-Announces-September-Quarter-2024-Financial-Results/default.aspx
已读取该小节：报告五天内7000架次取消及财务影响。仅能作公司口径背景，不足以独立确定本题July19—23日边界和十机场DL航段5458/2139等数字。审查报告所列数字仍为待复算，不将其拷贝成我们的结果。
SEC候选8K/10K及DOT页面本轮未成功获取，不能写成已读。

## 官方比赛资料
已读取COMAP 2024/2025结果及资源索引。2024三队奖项核验见O_PAPER_READING_V4.md。官方会员入口不等于全文已获取；旧AI政策候选URL404，不声称现行AI规则已核验。2002结果地址返回了不同内容，HTTP200不等于拿到了所需结果表。

## 最后回查补记
2026-11-27完成最终回查PDF p6和p10的完整提取文本：p6 Figure3及一致性/大样本论述，p10 Table2、分解解释及Discussion。此回查发生在初版诊断之后，不把方法顺序重写为事前设计。读取工具缺PyMuPDF、一次GBK输出失败后改用已安装pypdf与UTF-8成功；失败没有被记为阅读成功。
