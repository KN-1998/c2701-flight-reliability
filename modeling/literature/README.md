# v3当前阅读状态（覆盖下方历史选页记录）

P1全32页、P2全25页已于2026-11-26收尾顺读，关键页和取舍见docs/PRIMARY_FULL_READING_NOTES_V3。CAL2005/SCORE2007/T0只读选页，当前按项目规则仅列书目信息核验/全文阅读待完成；不充当已读全文正式公式来源。官方字段/行政记录按具体所读字段/页面定位，不伪称研究论文全文。核对11份真实来源文件和嵌套路径见SOURCE_MANIFEST。

# 原始文献及核验范围

- P1：PEYHARDI2014_SPEC.pdf，作者原始研究预印本，arXiv:1404.7331v2，32页。关键PDF页4—7已核读。https://arxiv.org/pdf/1404.7331v2
- P2：PEYHARDI2014_TREE.pdf，同作者原始研究预印本，arXiv:1405.5802v1，25页。关键PDF页5—6已核读。https://arxiv.org/pdf/1405.5802v1
- T0：TUTZ2020.pdf，Gerhard Tutz，A Taxonomy of Polytomous Item Response Models，arXiv:2010.01382v1，26页。PDF页6—8用于候选筛选与解释，不作为PCGLM首创原文。https://arxiv.org/pdf/2010.01382v1
- KITAGAWA1955_CROSSREF.json：只有书目信息。DOI 10.1080/01621459.1955.10501299；JASA 50(272):1168–1194。**未读全文；不提供原式证据。**
- ARXIV_METADATA.xml：直接API返回作者、版本日期、题名；不凭文件名认论文。
- FETCH_LOG_INITIAL.json / FETCH_LOG_SECOND.json：真实HTTP结果，包括失败。失败响应HTML不是论文，不作为证据或交付文献正文。
- SOURCE_MANIFEST.json：已交付来源文件的SHA256、核读定位和核验层级。哈希保证文件一致，不证明论文结论适用于本题。

公式以原PDF为准，文本提取可能破坏希腊字母/上下标。原式没有编号的地方用节名、Definition以及PDF页定位，不补造式号。公开预印本不冒称已核验期刊版本。研究用原文单列保存，正文只重述必要公式，不大段复制论文文字。

## 辅助方法证据（不是新增核心模型）

- CAL2005：Niculescu-Mizil与Caruana，Predicting Good Probabilities With Supervised Learning，ICML 2005，作者站点8页PDF。核读PDF页2 §2.1式(1)—(3)与独立校准集说明；论文明确把sigmoid校准归于Platt1999，不能声称本次读过Platt原作或CAL2005首创该映射。
- SCORE2007：Gneiting与Raftery，Strictly Proper Scoring Rules, Prediction, and Estimation，2007，作者站点20页PDF。核读PDF页4 §2.3/3.1、页5 Example1/3；分别支持同一测试集比较与严格适当评分理论。页5对应期刊页363。论文明确将Brier分数归于Brier1950；本次未读1950原作，不冒充最早出处。
- FETCH_LOG_AUXILIARY.json：包含两个PDF及Künsch候选URL的真实访问结果。Künsch返回的是1157字节挑战HTML，不是论文，不能据此引用区块bootstrap原式或断言前提成立。
- 细致推导、映射差异与尚缺依据见docs/AUXILIARY_METHODS.md。评分、校准只是F1/F2输出的估计/检验工具，不改变两条核心公式的组织方式。
