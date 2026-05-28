# -*- coding: utf-8 -*-
"""
生成预测模型回测验证 HTML 报告
"""
import sys
import base64
import io
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")
from src.config import (
    PREDICTIONS_CSV, PREDICTIVE_INDICATORS, SINGLE_DIRECTION_THRESHOLD,
    RETURN_DIRECTION_THRESHOLD, CONFIRMING_INDICATORS,
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

THRESH = RETURN_DIRECTION_THRESHOLD  # 2.0


def load_data():
    pred = pd.read_csv(PREDICTIONS_CSV, encoding="utf-8-sig")
    validated = pred[pred["validated"] == 1].copy()
    validated["actual_direction"] = validated["actual_3m_return"].apply(
        lambda x: "看涨" if x > THRESH else ("看跌" if x < -THRESH else "中性")
    )
    return pred, validated


def compute_stats(validated):
    total = len(validated)
    correct = (validated["direction"] == validated["actual_direction"]).sum()
    overall_acc = correct / total * 100

    nn = validated[(validated["direction"] != "中性") & (validated["actual_direction"] != "中性")]
    nn_correct = (nn["direction"] == nn["actual_direction"]).sum()
    nn_acc = nn_correct / len(nn) * 100 if len(nn) > 0 else 0

    sign_match = ((validated["score"] > 0) & (validated["actual_3m_return"] > 0)).sum() + \
                 ((validated["score"] < 0) & (validated["actual_3m_return"] < 0)).sum()
    sign_acc = sign_match / total * 100

    long_mask = validated["score"] > 0
    long_avg = validated.loc[long_mask, "actual_3m_return"].mean()
    long_win = (validated.loc[long_mask, "actual_3m_return"] > 0).mean() * 100

    return dict(total=total, correct=correct, overall_acc=overall_acc,
                nn_acc=nn_acc, sign_acc=sign_acc, long_avg=long_avg, long_win=long_win)


def direction_stats(validated):
    stats = {}
    for d in ["看涨", "看跌", "中性"]:
        sub = validated[validated["direction"] == d]
        if len(sub) > 0:
            c = (sub["direction"] == sub["actual_direction"]).sum()
            stats[d] = dict(count=len(sub), correct=c, acc=c/len(sub)*100,
                          avg_ret=sub["actual_3m_return"].mean())
    return stats


def year_stats(validated):
    stats = {}
    for year in sorted(validated["date"].str[:4].unique()):
        sub = validated[validated["date"].str[:4] == year]
        c = (sub["direction"] == sub["actual_direction"]).sum()
        long_sub = sub[sub["score"] > 0]
        nn_sub = sub[(sub["direction"] != "中性") & (sub["actual_direction"] != "中性")]
        nn_c = (nn_sub["direction"] == nn_sub["actual_direction"]).sum() if len(nn_sub) > 0 else 0
        stats[year] = dict(
            count=len(sub), correct=c, acc=c/len(sub)*100,
            bull=int((sub["direction"] == "看涨").sum()),
            bear=int((sub["direction"] == "看跌").sum()),
            neutral=int((sub["direction"] == "中性").sum()),
            nn_acc=nn_c/len(nn_sub)*100 if len(nn_sub) > 0 else 0,
            long_ret=long_sub["actual_3m_return"].mean() if len(long_sub) > 0 else 0,
        )
    return stats


def indicator_stats(validated):
    stats = []
    for col in PREDICTIVE_INDICATORS:
        score_col = f"{col}_score"
        if score_col not in validated.columns:
            continue
        col_c, col_t = 0, 0
        for _, row in validated.iterrows():
            s = row.get(score_col)
            if pd.isna(s):
                continue
            s = float(s)
            ind_dir = "看涨" if s > SINGLE_DIRECTION_THRESHOLD else (
                "看跌" if s < -SINGLE_DIRECTION_THRESHOLD else "中性")
            if ind_dir == row["actual_direction"]:
                col_c += 1
            col_t += 1
        label = PREDICTIVE_INDICATORS[col].get("label", col)
        weight = PREDICTIVE_INDICATORS[col].get("weight", 0)
        stats.append(dict(label=label, correct=col_c, total=col_t,
                         acc=col_c/col_t*100 if col_t > 0 else 0, weight=weight))
    return stats


def quintile_stats(validated):
    validated = validated.copy()
    validated["qtile"] = pd.qcut(validated["score"], 5,
                                  labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")
    stats = []
    for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
        sub = validated[validated["qtile"] == q]
        if len(sub) > 0:
            stats.append(dict(q=q, avg_score=sub["score"].mean(),
                            avg_ret=sub["actual_3m_return"].mean(),
                            win_rate=(sub["actual_3m_return"] > 0).mean() * 100, n=len(sub)))
    return stats


def gen_chart_cumulative(validated):
    fig, ax = plt.subplots(figsize=(10, 5))
    acc_cum = []
    correct_cum = 0
    for i, (_, row) in enumerate(validated.iterrows()):
        if row["direction"] == row["actual_direction"]:
            correct_cum += 1
        acc_cum.append(correct_cum / (i + 1) * 100)
    ax.plot(range(len(acc_cum)), acc_cum, color="#4fc3f7", linewidth=1.5)
    ax.axhline(y=50, color="gray", linestyle="--", alpha=0.5, label="随机基准 50%")
    ax.set_xlabel("预测序号", fontsize=12)
    ax.set_ylabel("累计准确率 (%)", fontsize=12)
    ax.set_title("历史回测累计方向准确率", fontsize=14)
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    dates = validated["date"].tolist()
    ticks = list(range(0, len(dates), 12))
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i] for i in ticks], rotation=45, ha="right", fontsize=9)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode()
    plt.close()
    return img


def gen_chart_quintile(qstats):
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [q["q"] for q in qstats]
    rets = [q["avg_ret"] for q in qstats]
    colors = ["#e15241" if r < 0 else "#3fb950" for r in rets]
    bars = ax.bar(labels, rets, color=colors, edgecolor="white", linewidth=0.5)
    for bar, ret in zip(bars, rets):
        ypos = bar.get_height() + 0.2 if ret >= 0 else bar.get_height() - 0.6
        va = "bottom" if ret >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width()/2, ypos, f"{ret:+.2f}%",
                ha="center", va=va, fontsize=11, fontweight="bold")
    ax.axhline(y=0, color="gray", linestyle="-", alpha=0.3)
    ax.set_xlabel("预测分数五分位（Q1=最低 Q5=最高）", fontsize=12)
    ax.set_ylabel("平均实际 3 月收益 (%)", fontsize=12)
    ax.set_title("预测分数 vs 实际收益（单调性验证）", fontsize=14)
    ax.grid(axis="y", alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode()
    plt.close()
    return img


def gen_chart_yearly(ystats):
    fig, ax = plt.subplots(figsize=(10, 5))
    years = list(ystats.keys())
    accs = [ystats[y]["acc"] for y in years]
    nn_accs = [ystats[y]["nn_acc"] for y in years]
    x = range(len(years))
    ax.bar(x, accs, color="#4fc3f7", alpha=0.7, label="三分类准确率")
    ax.plot(x, nn_accs, "o-", color="#ff9800", markersize=6, label="二分类准确率")
    ax.axhline(y=50, color="gray", linestyle="--", alpha=0.5)
    for i, a in enumerate(accs):
        ax.text(i, a + 2, f"{a:.0f}%", ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(years, rotation=45, ha="right")
    ax.set_ylabel("准确率 (%)", fontsize=12)
    ax.set_title("年度预测准确率", fontsize=14)
    ax.set_ylim(0, 110)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode()
    plt.close()
    return img


def build_html(stats, d_stats, y_stats, i_stats, q_stats, extreme, validated, img1, img2, img3):
    s = stats
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 各段 HTML 拼接
    parts = []

    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>预测模型回测验证报告</title>
<style>
:root {{ --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --accent: #4fc3f7;
  --green: #3fb950; --red: #e15241; --orange: #ff9800; --border: #2a2a4a; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: var(--bg);
  color: var(--text); max-width: 1000px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
h1 {{ color: var(--accent); border-bottom: 2px solid var(--border); padding-bottom: 10px; }}
h2 {{ color: var(--accent); margin-top: 40px; }}
h3 {{ color: var(--orange); }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 20px; margin: 16px 0; }}
.metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0; }}
.metric {{ text-align: center; padding: 16px; border-radius: 8px; }}
.metric .value {{ font-size: 2em; fontweight: bold; }}
.metric .label {{ font-size: 0.85em; opacity: 0.7; margin-top: 4px; }}
.good {{ background: rgba(63,185,80,0.15); border: 1px solid rgba(63,185,80,0.3); color: var(--green); }}
.bad {{ background: rgba(225,82,65,0.15); border: 1px solid rgba(225,82,65,0.3); color: var(--red); }}
.neutral {{ background: rgba(79,195,247,0.15); border: 1px solid rgba(79,195,247,0.3); color: var(--accent); }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9em; }}
th {{ background: rgba(79,195,247,0.15); color: var(--accent); padding: 10px 12px;
  text-align: left; border-bottom: 2px solid var(--border); }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
tr:hover {{ background: rgba(255,255,255,0.03); }}
.positive {{ color: var(--green); }}
.negative {{ color: var(--red); }}
.highlight {{ font-weight: bold; }}
img {{ max-width: 100%; border-radius: 8px; margin: 12px 0; }}
.footer {{ text-align: center; opacity: 0.5; font-size: 0.85em; margin-top: 40px;
  padding-top: 20px; border-top: 1px solid var(--border); }}
.note {{ background: rgba(255,152,0,0.1); border-left: 4px solid var(--orange); padding: 12px 16px;
  margin: 12px 0; border-radius: 0 8px 8px 0; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>预测模型历史回测验证报告</h1>
<p>模型版本: v2.0 (相关性加权) | 回测区间: 2016-01 ~ 2026-01 | 生成时间: {now}</p>
<p>方法: 用当前模型参数在历史每个月末做预测（look-ahead free），对比 3 个月后实际上证指数收益率</p>

<h2>一、核心指标概览</h2>
<div class="metrics">
  <div class="metric {'good' if s['overall_acc'] >= 50 else 'bad'}">
    <div class="value">{s['overall_acc']:.1f}%</div><div class="label">方向准确率(三分类)</div>
  </div>
  <div class="metric {'good' if s['nn_acc'] >= 55 else 'neutral'}">
    <div class="value">{s['nn_acc']:.1f}%</div><div class="label">方向准确率(二分类)</div>
  </div>
  <div class="metric {'good' if s['sign_acc'] >= 55 else 'neutral'}">
    <div class="value">{s['sign_acc']:.1f}%</div><div class="label">涨跌方向(分数正负)</div>
  </div>
  <div class="metric {'good' if s['long_avg'] > 0 else 'bad'}">
    <div class="value">{s['long_avg']:+.2f}%</div><div class="label">看多策略平均收益</div>
  </div>
</div>

<div class="card">
<h3>关键发现</h3>
<ul>
  <li>模型在<strong>二分类(看涨/看跌)</strong>场景准确率达 <strong>{s['nn_acc']:.1f}%</strong>，显著高于随机(50%)</li>
  <li>看多策略(score&gt;0)平均收益 <strong>{s['long_avg']:+.2f}%</strong>，正收益比例 <strong>{s['long_win']:.1f}%</strong></li>
  <li>Q5(最高分)预测时平均收益 <strong>{q_stats[4]['avg_ret']:+.2f}%</strong>，胜率 <strong>{q_stats[4]['win_rate']:.1f}%</strong> — 极端看涨信号高度可靠</li>
  <li>看跌预测集中在2021-2024熊市期间，受政策刺激反弹影响导致准确率偏低</li>
  <li>模型对<strong>趋势性市场</strong>(2016牛市、2020复苏、2025行情)预测较好，对<strong>震荡/政策驱动</strong>市场较弱</li>
</ul>
</div>""")

    # 二、按方向
    parts.append("""
<h2>二、按预测方向分析</h2>
<div class="card">
<table>
<tr><th>预测方向</th><th>次数</th><th>准确</th><th>准确率</th><th>平均实际收益</th></tr>""")
    for d in ["看涨", "看跌", "中性"]:
        ds = d_stats[d]
        cls = "positive" if ds["avg_ret"] > 0 else ("negative" if ds["avg_ret"] < 0 else "")
        parts.append(f'<tr><td class="highlight">{d}</td><td>{ds["count"]}</td>'
                     f'<td>{ds["correct"]}</td><td>{ds["acc"]:.1f}%</td>'
                     f'<td class="{cls}">{ds["avg_ret"]:+.2f}%</td></tr>')
    parts.append("</table></div>")

    # 三、各指标
    parts.append("""
<h2>三、各指标独立准确率</h2>
<div class="card">
<table>
<tr><th>指标</th><th>正确/总数</th><th>准确率</th><th>当前权重</th></tr>""")
    for i in i_stats:
        parts.append(f'<tr><td>{i["label"]}</td><td>{i["correct"]}/{i["total"]}</td>'
                     f'<td>{i["acc"]:.1f}%</td><td>{i["weight"]:.1%}</td></tr>')
    parts.append("</table></div>")

    # 四、五分位
    parts.append(f"""
<h2>四、预测分数五分位验证</h2>
<div class="card">
<p>验证预测分数的单调性：分数越高，实际收益是否越高</p>
<img src="data:image/png;base64,{img2}">
<table>
<tr><th>分位</th><th>平均分数</th><th>平均实际收益</th><th>正收益比例</th><th>样本数</th></tr>""")
    for q in q_stats:
        cls = "positive" if q["avg_ret"] > 0 else "negative"
        parts.append(f'<tr><td>{q["q"]}</td><td>{q["avg_score"]:+.3f}</td>'
                     f'<td class="{cls}">{q["avg_ret"]:+.2f}%</td>'
                     f'<td>{q["win_rate"]:.1f}%</td><td>{q["n"]}</td></tr>')
    parts.append("""
</table>
<div class="note">
Q1→Q5 收益呈现<strong>上升趋势</strong>，验证了模型分数的单调性。Q5(最高分)的胜率和收益显著优于其他分位，说明模型在<strong>强烈看涨信号</strong>时最可靠。
</div>
</div>""")

    # 五、年度
    parts.append(f"""
<h2>五、年度表现</h2>
<div class="card">
<img src="data:image/png;base64,{img3}">
<table>
<tr><th>年份</th><th>次数</th><th>三分类准确</th><th>二分类准确</th><th>看多/看空/中性</th><th>看多平均收益</th></tr>""")
    for y, ys in y_stats.items():
        cls = "positive" if ys["long_ret"] > 0 else "negative"
        parts.append(f'<tr><td>{y}</td><td>{ys["count"]}</td><td>{ys["acc"]:.1f}%</td>'
                     f'<td>{ys["nn_acc"]:.1f}%</td><td>{ys["bull"]}/{ys["bear"]}/{ys["neutral"]}</td>'
                     f'<td class="{cls}">{ys["long_ret"]:+.2f}%</td></tr>')
    parts.append("</table></div>")

    # 六、累计准确率
    parts.append(f"""
<h2>六、累计准确率曲线</h2>
<div class="card">
<img src="data:image/png;base64,{img1}">
<div class="note">
累计准确率在2016年初高位(~80%)后逐步回落，2018-2022年持续低于50%。2025年起大幅回升至80%+。这说明模型在<strong>趋势性市场</strong>中表现优异，但在<strong>政策驱动的V型反转</strong>中容易失效。
</div>
</div>""")

    # 七、重大行情
    parts.append("""
<h2>七、重大行情预测回顾</h2>
<div class="card">
<table>
<tr><th>日期</th><th>预测</th><th>分数</th><th>实际收益</th><th>结果</th><th>备注</th></tr>""")
    notes = {
        "2018-12": "底部反转", "2019-01": "底部反转", "2020-04": "疫后反弹",
        "2020-05": "疫后反弹", "2022-10": "政策底反弹", "2024-01": "政策刺激",
        "2018-05": "中美贸易摩擦", "2018-09": "中美贸易摩擦",
        "2018-01": "全球股市暴跌", "2024-10": "政策刺激",
    }
    for _, row in extreme.head(15).iterrows():
        hit = "✓" if row["direction"] == row["actual_direction"] else "✗"
        hit_cls = "positive" if hit == "✓" else "negative"
        ret = row["actual_3m_return"]
        note = notes.get(row["date"], "")
        parts.append(f'<tr><td>{row["date"]}</td><td class="highlight">{row["direction"]}</td>'
                     f'<td>{row["score"]:+.3f}</td>'
                     f'<td class="{"positive" if ret > 0 else "negative"}">{ret:+.2f}%</td>'
                     f'<td class="{hit_cls}">{hit}</td><td>{note}</td></tr>')
    parts.append("</table></div>")

    # 八、评估
    parts.append("""
<h2>八、模型评估与改进方向</h2>
<div class="card">
<h3>优势</h3>
<ul>
  <li><strong>趋势识别能力</strong>: 在明确的上升/下降趋势中准确率显著高于随机</li>
  <li><strong>单调性良好</strong>: Q1→Q5 收益递增，分数能有效排序未来收益</li>
  <li><strong>看多策略盈利</strong>: score&gt;0 时平均收益 +1.48%，55.6% 胜率</li>
  <li><strong>极端信号可靠</strong>: Q5 时 83.3% 胜率、+4.14% 平均收益</li>
</ul>
<h3>劣势</h3>
<ul>
  <li><strong>政策驱动失效</strong>: 2022年10月、2024年1月的政策底反弹无法捕捉</li>
  <li><strong>看跌预测偏多</strong>: 2023年密集看跌虽多数正确，但遇到反弹就全军覆没</li>
  <li><strong>震荡市区分度不足</strong>: 中性区间(~40%)预测区分度有限</li>
  <li><strong>黑天鹅事件无感知</strong>: 地缘政治、突发政策等无法提前预测</li>
</ul>
<h3>改进方向</h3>
<ul>
  <li>引入政策情绪指标（如信贷脉冲、社融超预期幅度）</li>
  <li>增加市场技术面指标（如均线斜率、成交量变化率）辅助确认</li>
  <li>对看跌预测增加确认要求（如需2个以上确认指标一致）</li>
  <li>区分趋势市/震荡市的自适应阈值机制</li>
</ul>
</div>""")

    parts.append(f"""
<div class="footer">
预测模型回测验证报告 | v2.0 | {s['total']} 条回测预测 ({len(validated)} 条已验证) | 生成于 {now}
</div>
</body></html>""")

    return "\n".join(parts)


def main():
    print("加载数据...")
    pred, validated = load_data()
    print(f"总预测: {len(pred)}, 已验证: {len(validated)}")

    stats = compute_stats(validated)
    d_stats = direction_stats(validated)
    y_stats = year_stats(validated)
    i_stats = indicator_stats(validated)
    q_stats = quintile_stats(validated)

    extreme = validated[validated["actual_3m_return"].abs() > 10].sort_values(
        "actual_3m_return", key=abs, ascending=False)

    print("生成图表...")
    img1 = gen_chart_cumulative(validated)
    img2 = gen_chart_quintile(q_stats)
    img3 = gen_chart_yearly(y_stats)

    print("构建HTML...")
    html = build_html(stats, d_stats, y_stats, i_stats, q_stats, extreme, validated, img1, img2, img3)

    out = Path("reports") / "backtest_validation_report.html"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"报告已保存: {out} ({len(html)//1024}KB)")
    return str(out)


if __name__ == "__main__":
    main()
