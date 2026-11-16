"""Render retained aggregate measurements; optional developer-only matplotlib."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['svg.fonttype'] = 'none'
ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT/'docs/benchmarks/historical-96.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout='constrained')
colors = ['#174261','#cb7742']
for ax, kind, title in zip(axes, ['complete_documents','window_fts5'],
                           ['Complete documents · 6 pairs/model','32K constrained FTS5 baseline · 18 pairs/model']):
    groups = [g for g in data['groups'] if g['baseline_type']==kind]
    for j, (condition,label) in enumerate([('disabled','Without KRE'),('enabled','With KRE')]):
        bars=ax.bar([i+(j-.5)*.34 for i in range(len(groups))],
                    [g['conditions'][condition]['total_tokens'] for g in groups],.34,label=label,color=colors[j])
        ax.bar_label(bars,fmt='{:,.0f}',padding=3,fontsize=9)
    ax.set_xticks([0,1],['Qwen 9B','Qwen 35B']);ax.set_title(title,fontsize=11,pad=14)
    ax.set_ylabel('Measured input + output tokens');ax.set_ylim(0,max(g['conditions'][c]['total_tokens'] for g in groups for c in ['disabled','enabled'])*1.23)
    ax.spines[['top','right']].set_visible(False);ax.legend(loc='upper left',fontsize=9)
fig.suptitle('Observed token consumption — quality-preserving savings remain unproven',fontsize=13)
fig.supxlabel('Historical runtime; synthetic tasks; one attempt per arm. Independent semantic review: 0/96.',fontsize=10)
for ext in ['svg','png']:
    fig.savefig(ROOT/f'docs/benchmarks/historical-tokens.{ext}',dpi=160,metadata={'Creator':'KRE benchmark reproduction'} if ext=='svg' else None)
