# v2故障的可重复反例

src/legacy_v2_comparison.py是v3修改前保存的comparison.py快照，只供反例复算，当前模型从不调用它。运行src/reproduce_v2_failure.py会从包内2023月表审计并调用旧实现，预期捕捉共同支持空分母ValueError。已经观测的反例在results/review_v3/reproduction/v2_reproduction.json。

新实现第一次修订仍发现日期分辨率错误（微秒asi8不等于纳秒常量），已通过日期差比较修复；tests/test_review_v3.py保留缺日与稀疏格反例，避免单看“未抛错”误判重采样有效。初次错误区间已被重算，不作为交付结果。旧原始ZIP及v2交接包保持不变。
