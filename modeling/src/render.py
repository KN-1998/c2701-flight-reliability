"""Generate traceable handoff figures and findings; never invent missing results."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import os
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.cache'/'matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'core'


def main():
    summary=json.loads((OUT/'run_summary.json').read_text(encoding='utf-8'))
    byyear=pd.read_csv(OUT/'metrics_by_year_airport.csv')
    data=byyear[byyear.year.eq(2023)].sort_values('reliability_15_lower',ascending=False)
    fig,ax=plt.subplots(figsize=(10,5))
    for t in [0,15,30,60,120]:
        ax.plot(data.Origin,100*data[f'reliability_{t}_lower'],'o-',label=f'Arrival delay < {t} min')
    ax.set(title='2023 reported domestic departures: threshold sensitivity',ylabel='Share of scheduled records (%)')
    ax.legend(ncol=2,fontsize=8);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/'threshold_sensitivity_2023.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    ix=np.arange(len(data))
    ax.bar(ix-.18,100*data.conditional_on_time,width=.36,label='Conditional on normal completion')
    ax.bar(ix+.18,100*data.reliability_15_lower,width=.36,label='All retained scheduled records')
    ax.set(xticks=ix,xticklabels=data.Origin,ylabel='On-time percentage',title='2023 denominator effect (on time = arrival delay < 15 min)')
    ax.legend(fontsize=8);ax.set_ylim(0,100);fig.tight_layout();fig.savefig(OUT/'denominator_effect_2023.png',dpi=180);plt.close(fig)
    audit=pd.read_csv(OUT/'audit_by_month.csv')
    lines=['# 给编程手的当前实测快照','',f'状态：**{summary["status"]}**。本表不是完整2023—2025核心期，也不是2027预测。',
           '',f'完整下载并审计的月份数：{len(summary["periods"])}；保留记录：{summary["retained_rows"]:,}；未知结局：{summary["unknown"]}。',
           f'完全重复删除：{summary["exact_duplicates_removed"]}；冲突身份键记录：{summary["conflicting_key_rows"]}；ArrDel15与ArrDelay>=15不一致：{int(audit.arrdel15_disagreement.sum())}。',
           '', '## 2023全年描述统计（真实观测，不是调整后排名）','',
           '| 出发机场 | 记录数 | 正常完成后的准点率 | 计划航段满意率下界 | 取消率 | 完成后P90延误/分钟 |',
           '|---|---:|---:|---:|---:|---:|']
    for r in data.itertuples():
        lines.append(f'| {r.Origin} | {r.n:,} | {r.conditional_on_time:.1%} | {r.reliability_15_lower:.1%} | {r.cancellation_rate:.1%} | {r.delay_p90_completed:.0f} |')
    lines+=['','注：表格按原始计划满意率排列，仅方便阅读；尚未作航班组合调整，不能解释为机场运营优劣。','',
            '## 已验证与未验证','',
            '- 已验证：本包真实记录的月度审计、五分类对账、阈值指标计算。','- 已验证：10项自动测试，涵盖15/60分钟边界、未知/冲突、概率守恒、拟合与校准联调、共同支持标准化和可复现重采样。',
            '- 尚未完成：36个月核心覆盖、完整时间外预测、真实数据调整排名及区间、天气信息增益、事件资料补核、实证洞见验证。',
            '- prediction.py/comparison.py/stress.py是通过合成数据或逻辑测试的参考实现；缺少真实全期运行就不能写成实证完成。',
            '- 缺失结局界不是置信区间；2027倍率情景不是实测。',
            '', '## 当前月份','',', '.join(summary['periods'])]
    (OUT/'CURRENT_FINDINGS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Rendered 2023 figures and CURRENT_FINDINGS.md')

if __name__=='__main__':main()

