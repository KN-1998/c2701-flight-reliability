# O奖论文检索与阅读记录（不混淆获奖核验/读过全文）

## 本轮检索真实顺序
先读COMAP 2024/2025官方结果页→官方会员资源索引→2024 C三队候选全文地址尝试（失败，含404和TLS EOF）→GitHub公开索引获取2002/2007航空相关候选→raw下载失败后API blob成功→选页阅读。全部失败保留在 literature/review_v4/FETCH_ATTEMPTS.json。
不绕过会员权限；公开镜像只作检索和个人阅读，版权归原权利人，未将这些PDF加入公开仓库。

## 奖项已官方核验，但本轮没有取得全文的三篇
COMAP 2024结果页“eleven Outstanding Winners of THE MCM (C) Problem”：
- 2401298，Fudan University，AMS Award；
- 2401445，Renmin University，COMAP Scholarship Award；
- 2401919，Renmin University，SIAM Award。
官方页：https://www.contest.comap.com/undergraduate/contests/mcm/contests/2024/results/
状态：AWARD_VERIFIED_FULLTEXT_NOT_OBTAINED。**不能为这三篇编写具体模型、公式、结果或页码读后感。**

## 实际取得并选页阅读的三篇航空相关候选
本节**不称“三篇已认证O奖全文读完”**。镜像目录文件名O不足以独立核验奖项，阅读范围也只是所列页。原PDF哈希和API来源见 SOURCE_NOTES_V4.json。

### S1 Schubmehl / Turner / Boylan, Models for Evaluating Airline Overbooking
UMAP Journal 23(3), 2002, pp301—316，Harvey Mudd College。已读PDF pp1—3及15（刊页301—303、315）。p15有MAA颁奖图注，可支持该文团队获该奖的图注事实，不当作完整官方O结果表。
- p1先说明两个模型分别承担前瞻评估和历史回溯，紧接文献综述；对本题启发：描述比较与事前预测必须明确分工，而不是都叫“评价准确”。
- pp2—3回顾已有收益管理路线，并讨论网络/完整行程效应。本题没有旅客行程数据，不能只因这篇谈网络效应就自行构造旅客衔接损失。
- 借鉴论证结构而非迁移EMSR参数；文内二手文献未直接读过的仍属未读。
状态：PRIMARY_STUDENT_SELECTED_PAGES_READ_AWARD_CLASSIFICATION_PENDING。

### S2 Bowman / Houmard / Dickey, Bumping for Dollars: The Airline Overbooking Problem
UMAP Journal 23(3), 2002, pp351—365，Wake Forest University。已读PDF pp1—2（刊页351—352），并检查候选后部页但不宣称全读。
- p1由单航班扩到两航班、再到多航班，核心概率对象与收入对象保持连接；本题借鉴的是局部q→叶概率→联合风险的严密连续推导。
- p2定义参数后给单/两/多航班公式；声称用Monte Carlo核对理论式。对本题的警示：数值核对只能核对实现，不能把他们的二项到场独立假设移作本题航班独立依据。
状态：PRIMARY_STUDENT_SELECTED_PAGES_READ_AWARD_CLASSIFICATION_PENDING。

### S3 Team2053, Boarding at the Speed of Flight, 2007-02-12
30页竞赛稿。已读PDF pp1—4、14、28，非全文。
- p1摘要把可操作的瓶颈（入舱流率、行李存放等）放在建议前，同时指出需航空公司内部数据进一步校正参数。
- p4先术语/变量，再分析机制与模拟，不靠名称堆模型。
- p14从稠密与稀疏排布机制解释结果；p28明确独立、完美知识等假设与未测情景限制。本题写作应同样把适用前提对结论的影响写出来，而非最后空泛“存在不足”。
官方2007结果页已读，仅列获奖学校，没有在已读页面把2053与学校准确对应，故不升级其O认证。
状态：PRIMARY_STUDENT_SELECTED_PAGES_READ_AWARD_CLASSIFICATION_PENDING。

## 下一步的完成标准
至少补足三篇“官方队号/学校/奖项核验+可合法取得的全文+逐页读书卡”。本轮完成候选发现和实际选页阅读，但**尚未完成三篇认证O全文精读**；不得在队内要求文档或论文中伪称完成。
