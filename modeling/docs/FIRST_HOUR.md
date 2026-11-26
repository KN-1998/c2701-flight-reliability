# 编程手接手顺序 v3

1. 在ZIP解压根运行modeling/src/verify_handoff.py，核验CHECKSUMS.sha256；查看HANDOFF_CONTENTS.json中的实际数据和未完成项。
2. 阅读README_编程手先读、MODELING_REVISION_V3、REVIEW_RESPONSE_V3、FORMULA_PROVENANCE与ASSUMPTION_REGISTER。
3. 运行modeling/src/check_all.py。通过仅表示逻辑/回归测试，不是统计假设证明。
4. 先核results/review_v3/comparison_2023/base的coverage、bootstrap_diagnostics和pairwise，再看点排序。必须识别MCO低支持。
5. 查看primary/development预测status的准确月份、上限、同一测试hash；先看直接联合对照，不以树优越为先验。
6. 按README命令在新目录从月表复算；需要精确primary清单时指定--snapshot。不要为普通实现选择等待建模手回应，不在来源缺口处擅自填真值。
7. 缺月用fetch_bts或受限并发的fetch_bts_ranges补取。失败保留日志，完整校验后才发布月表，不将.part当有效输入。
8. 对尚未支持的假设补证或限制声明；若要改变阈值、分层、信息截止或时间窗，创建新实验目录和新台账行，不覆盖旧结果。
