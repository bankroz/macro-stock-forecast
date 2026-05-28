# 股市宏观分析系统

基于**非银金融机构存款增速 + 12 个宏观指标**的股市见顶信号检测系统 + **走势预测引擎**。通过追踪资金面、信用周期、实体经济和市场情绪四个维度的变化，实现市场阶段性顶部的自动预警；同时基于 4 个领先指标的历史相关性加权，生成 3 个月窗口的走势预测并持续验证微调。

## 核心逻辑

```
居民存款（慢变量，领先5-7月）
    ↓  资金搬家
非银金融机构存款（快变量，领先0-3月）≈ 券商保证金 + 基金存款 + 信托/保险存款
    ↓  直接入场
上证指数（即时响应）
```

当非银存款增速从高位回落、或出现存款涨而指数跌的背离时，往往意味着资金正在撤离股市，是见顶的重要预警信号。系统同时监控 M2/PMI/BDI/社零/财政收入等 12 个宏观指标，通过多维度交叉验证提升信号可靠性。

## 项目结构

```
股市分析/
├── run.py                          # 主入口：一键执行全流程（6步）
├── init_data.py                    # 核心数据初始化（存款+指数→CSV）
├── init_macro_data.py              # 宏观指标数据初始化（全部13个宏观指标→CSV）
├── requirements.txt                # Python 依赖
├── run.bat                         # 双击一键运行（生成报告+图表+自动打开）
├── setup_schedule.bat              # Windows 定时任务安装（每周一自动运行）
│
├── src/                            # 核心模块
│   ├── config.py                   # 全局配置：JSON 加载器 + 路径 + 默认值回退
│   ├── scraper.py                  # 数据采集：akshare 指数 + 12个宏观指标
│   ├── data_manager.py             # CSV 读写、14个数据源外连接合并、增量更新
│   ├── indicators.py               # 衍生指标：MoM/YoY/滚动均值/剪刀差等
│   ├── signal_detector.py          # 信号检测引擎：13个信号 + 风险评级 + 回测
│   ├── prediction.py               # 走势预测引擎 + 自学习系统（偏差追踪 + 智能权重调整）
│   ├── chart_generator.py          # 图表生成：6张分析图表
│   └── report_generator.py         # Markdown 8章分析报告
│
├── config/                         # JSON 配置文件（可手动编辑 + 程序自动微调）
│   ├── signal_config.json          # 信号检测阈值（13个信号 + 风险等级 + 历史顶底）
│   └── prediction_config.json      # 预测引擎配置（权重 + 确认指标 + 自学习参数）
│
├── data/                           # 数据目录（14个CSV）
│   ├── deposits.csv                # 存款月度数据（2015.01 - 最新）
│   ├── sh_index.csv                # 上证指数月度收盘价
│   ├── predictions.csv             # 走势预测记录（含验证结果）
│   ├── macro_m2.csv                # M2/M1/M0 货币供应量
│   ├── macro_pmi.csv               # PMI 制造业/非制造业
│   ├── macro_electricity.csv       # 全社会用电量
│   ├── macro_margin.csv            # 两融余额（日度聚合月度）
│   ├── macro_shibor.csv            # SHIBOR 隔夜/1周利率
│   ├── macro_lpr.csv               # LPR 1年期/5年期
│   ├── macro_cpi.csv               # CPI 同比/环比
│   ├── macro_ppi.csv               # PPI 同比
│   ├── macro_northbound.csv        # 北向资金月度净买入
│   ├── macro_bdi.csv               # BDI 干散货指数（日频→月度）
│   ├── macro_retail.csv            # 社消零售总额同比增速
│   └── macro_fiscal.csv            # 财政收入当月同比增速
│
├── output/                         # 图表输出（6张PNG，文件名带日期）
│   ├── main_trend_YYYY-MM-DD.png   # 存款+指数趋势对比图
│   ├── rate_comparison_YYYY-MM-DD.png  # MoM/YoY 增速对比图
│   ├── signal_backtest_YYYY-MM-DD.png  # 历史信号回测标注图
│   ├── macro_credit_cycle_YYYY-MM-DD.png # 宏观信用周期（M2+PMI+上证）
│   ├── macro_liquidity_YYYY-MM-DD.png   # 市场流动性全景（两融+SHIBOR+北向+上证）
│   └── prediction_dashboard_YYYY-MM-DD.png # 走势预测仪表盘（预测指标+趋势确认）
│
├── reports/                        # 分析报告
│   └── YYYY-MM-DD_report.md        # Markdown 8章格式报告（含走势预测）
│
└── logs/                           # 运行日志
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据

首次使用需运行两个初始化脚本：

```bash
python init_data.py              # 核心数据：存款 + 上证指数
python init_macro_data.py        # 宏观指标：M2/PMI/用电量/两融/SHIBOR/LPR/CPI/PPI/北向/BDI/社零/财政
```

### 3. 运行分析

```bash
# 完整流程（含网络数据采集）
python run.py

# 离线模式（仅使用本地CSV，不发起网络请求）
python run.py --no-fetch

# 或者双击 run.bat 一键运行
```

### 4. 查看结果

运行完成后查看：
- **图表**：`output/` 目录下的 6 张 PNG 图片
- **报告**：`reports/` 目录下的 Markdown 文件（含走势预测章节）
- **日志**：`logs/` 目录下的日志文件

## 数据管线

### 数据来源

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 居民/非银存款 | 中国人民银行 | 月度 | household_deposit, non_bank_deposit | 万元 |
| 上证指数 | akshare `stock_zh_index_daily` | 月度 | sh_close | 日线→月末收盘 |
| M2/M1/M0 | akshare `macro_china_money_supply` | 月度 | m2_amount, m2_yoy 等 | 信用周期核心 |
| PMI | akshare `macro_china_pmi` | 月度 | pmi_manufacturing, pmi_non_manufacturing | 景气先行指标 |
| 全社会用电量 | akshare `macro_china_society_electricity` | 月度 | electricity_total_yoy 等 | GDP高频替代 |
| 两融余额 | akshare `macro_china_market_margin_sh` | 日度→月度 | margin_balance, margin_yoy | 散户杠杆度量 |
| SHIBOR | akshare `macro_china_shibor_all` | 日度→月度 | shibor_on_avg, shibor_1w_avg | 资金面温度 |
| LPR | akshare `macro_china_lpr` | 日度→月度 | lpr_1y, lpr_5y | 货币政策风向标 |
| CPI | akshare `macro_china_cpi` | 月度 | cpi_yoy, cpi_mom | 消费价格 |
| PPI | akshare `macro_china_ppi` | 月度 | ppi_yoy | 工业品价格 |
| 北向资金 | akshare `stock_hsgt_hist_em` | 日度→月度 | northbound_net_buy | 外资风向标 |
| BDI 干散货指数 | akshare `macro_china_freight_index` | 日度→月度 | bdi_value, bdi_yoy | 全球需求同步指标 |
| 社消零售总额 | akshare `macro_china_consumer_goods_retail` | 月度 | retail_yoy | 消费端景气度 |
| 财政收入 | akshare `macro_china_czsr` | 月度 | fiscal_yoy | 政策空间参考 |

### 数据格式

所有 CSV 统一格式：第一列为 `date`（YYYY-MM-DD），后续为指标列，编码 UTF-8-sig。

## 信号检测机制

系统定义了 **13 个信号**（4 个存款类 + 9 个宏观类）和 **4 级风险等级**：

### 信号类型

#### 存款信号（4个）

| 信号 | 等级 | 触发条件 |
|------|------|----------|
| YoY 增速从高位回落 | PRIMARY | 近12月YoY峰值 > 15%，当前YoY > 0，相对峰值降幅 ≥ 30% |
| MoM 增速从高位急跌 | SECONDARY | 近12月MoM峰值 > 3%，当前MoM < 峰值 × 30% |
| 顶背离-A（存款涨+指数跌） | PRIMARY | 非银存款连续3月上升 + 指数连续3月下降 |
| 顶背离-B（存款加速+指数减速） | WARNING | 非银存款MoM连续2月加速 + 指数MoM连续2月减速 |

#### 宏观信号（6个）

| 信号 | 等级 | 触发条件 | 预测性 |
|------|------|----------|--------|
| M2增速拐点下行 | WARNING | M2 YoY 的3月移动平均拐头下行 | 领先股市6-12月 |
| PMI持续收缩 | SECONDARY | 制造业PMI连续3月 < 50 | 领先企业利润1-2季度 |
| 两融余额增速见顶 | SECONDARY | 两融YoY峰值 > 20%，当前相对峰值降幅 ≥ 30% | 散户杠杆退潮 |
| SHIBOR隔夜飙升 | WARNING | 月均值 > 前月 × 150% | 资金面骤紧，1-2周内承压 |
| CPI-PPI剪刀差扩大 | WARNING | 剪刀差连续3月扩大 | 上游挤压下游利润 |
| 北向资金持续净流出 | SECONDARY | 月度净买入连续3月为负 | 外资撤退信号 |
| BDI 极值反转 | WARNING | BDI YoY 从极值(>+80%或<-40%)回落/回升50%+ | 全球需求拐点 |
| 社零持续下降 | WARNING | 社零 YoY 连续3月下降 | 消费走弱（领先10月） |
| 财政收入拐点 | WARNING | 财政收入 YoY 在6月窗口内触底后回升 | 政策空间变化（领先10月） |

### 风险等级

| 等级 | 条件 | 含义 |
|------|------|------|
| LOW | 无信号 | 正常状态，维持当前策略 |
| MEDIUM | SECONDARY ≥ 1 或 WARNING ≥ 1 | 需关注，暂不调整仓位 |
| HIGH | PRIMARY ≥ 1 且 (SECONDARY ≥ 1 或 WARNING ≥ 1) | 警惕，适度降低仓位 |
| CRITICAL | PRIMARY ≥ 2 | 高危，大幅降低仓位 |

### 参数调优

所有信号阈值和预测权重存储在 `config/` 目录的 JSON 文件中，支持**手动编辑**和**程序自动微调**：

- `config/signal_config.json` — 信号检测阈值（回看窗口、降幅阈值、极值阈值、风险等级规则等）
- `config/prediction_config.json` — 预测引擎配置（指标权重、确认指标、自学习参数）

程序首次运行自动生成 JSON 文件，后续运行读取 JSON 中的值（优先于代码默认值）。你可以直接编辑 JSON 文件调整参数，下次运行生效。自学习系统会自动微调权重（详见"验证闭环"章节）。

```python
# 存款信号
YOY_LOOKBACK_MONTHS = 12          # YoY 回看窗口
YOY_DECLINE_THRESHOLD = 0.30      # YoY 相对降幅阈值（30%）
MOM_LOOKBACK_MONTHS = 12          # MoM 回看窗口
MOM_DECLINE_THRESHOLD = 0.50      # MoM 降幅阈值（50%）
DIVERGENCE_A_CONSECUTIVE = 3      # 背离-A 连续月数
DIVERGENCE_B_CONSECUTIVE = 2      # 背离-B 连续月数

# 宏观信号（第一批+第二批）
M2_MA_WINDOW = 3                  # M2 均线窗口
PMI_CONTRACTION_MONTHS = 3        # PMI 收缩判定月数
MARGIN_HIGH_WATERMARK = 20        # 两融YoY高位门槛（%）
MARGIN_DECLINE_THRESHOLD = 0.30   # 两融YoY降幅阈值
SHIBOR_SPIKE_THRESHOLD = 1.50     # SHIBOR飙升倍数
CPI_PPI_DIVERGENCE_MONTHS = 3     # 剪刀差扩大判定月数
NORTHBOUND_OUTFLOW_MONTHS = 3     # 北向流出判定月数

# 宏观信号（第三批）
BDI_EXTREME_HIGH = 80             # BDI YoY 极高位（%）
BDI_EXTREME_LOW = -40             # BDI YoY 极低位（%）
BDI_REVERSAL_WINDOW = 3           # BDI 反转回看月数
RETAIL_DECLINE_MONTHS = 3         # 社零连续下降判定月数
FISCAL_TURNING_WINDOW = 6         # 财政收入拐点判定窗口
```

## 分析维度

系统从四个维度监控市场状态：

### 1. 资金面（存款类信号）
追踪非银金融机构存款的增速变化和与股指的背离关系，捕捉资金入场/退场信号。

### 2. 信用周期（M2 + PMI + 用电量）
M2 增速是信用扩张的总量指标，PMI 是景气先行指标，用电量是实体经济的高频替代。三者交叉验证可判断经济基本面走向。

### 3. 市场流动性（两融 + SHIBOR + LPR + 北向）
两融余额衡量散户杠杆水平，SHIBOR 反映银行间资金面松紧，LPR 代表货币政策方向，北向资金跟踪外资动向。

### 4. 价格信号（CPI + PPI）
CPI-PPI 剪刀差反映产业链利润分配格局，剪刀差扩大时上游挤压下游，消费板块承压。

### 5. 全球贸易（BDI）
BDI 干散货指数是全球大宗商品贸易的晴雨表，与上证指数同步正相关（r=+0.36），反映全球风险偏好和贸易活跃度。在市场顶部/底部常出现极端值反转。

### 6. 消费与财政（社零 + 财政收入）
社消零售和财政收入增速与上证指数负相关（r=-0.50, r=-0.37），领先约10个月，体现A股"政策市"特征：宏观走弱→政策宽松预期→市场上涨。

## 图表输出

| 图表 | 文件 | 内容 |
|------|------|------|
| 存款+指数趋势 | main_trend_*.png | 非银存款与上证指数的长期走势对比 |
| 增速对比 | rate_comparison_*.png | MoM/YoY 增速变化率对比 |
| 历史信号回测 | signal_backtest_*.png | 已知顶部/底部标注 + 信号触发位置 |
| 宏观信用周期 | macro_credit_cycle_*.png | M2增速 + PMI + 上证指数三面板 |
| 市场流动性 | macro_liquidity_*.png | 两融 + SHIBOR + 北向资金 + 上证指数四面板 |
| 走势预测仪表盘 | prediction_dashboard_*.png | 预测指标条形图 + 趋势确认状态面板 |

## 定时任务

以管理员身份运行 `setup_schedule.bat`，将创建 Windows 计划任务：

- **任务名称**：StockDepositAnalysis
- **执行频率**：每周一 09:00
- **执行命令**：`python run.py --no-fetch`
- **删除任务**：`schtasks /delete /tn "StockDepositAnalysis" /f`

## 技术栈

- **Python 3.10+**
- **pandas**：数据处理与计算
- **matplotlib**：图表生成（中文字体自动适配）
- **akshare**：全量数据采集（指数 + 12个宏观指标）
- **requests + beautifulsoup4**：央行数据爬虫（预留接口）

## 已知限制

1. 北向资金：akshare `stock_hsgt_hist_em` 自 2024-08 后当日成交净买额为 null，84.6% 非空率，报告中已标注
2. 社融：akshare `macro_china_shrzgm` 存在 SSL 错误，尚未接入，需要替代数据源
3. 央行存款数据爬虫 `fetch_pbc_deposits()` 为预留接口，尚未对接实际页面结构，当前依赖 CSV 手动更新
4. 月度频率，对日内/周度级别的市场波动无感知
5. 历史回测显示对部分市场顶部（如2015年6月、2021年2月）的提前捕获能力有限，信号算法仍在持续优化
6. 预测系统基于历史相关性，极端市场环境下（如黑天鹅事件）预测可靠性会下降

## 走势预测系统

### 设计原理

基于第三批宏观指标的 Pearson 滞后交叉相关性分析（详见 `docs/batch3_analysis.md`），系统将指标分为两类：

- **预测指标**（领先 6+ 个月）：当前值可预测未来走势方向
- **趋势确认指标**（同步）：验证当前趋势是否延续

### 指标分类

#### 预测指标（4个）

| 指标 | 相关性 r | 滞后月数 | 方向 | 初始权重 | 说明 |
|------|---------|---------|------|---------|------|
| 社消零售 YoY | -0.5007 | 10月 | 负相关 | 37% | 消费走弱→政策宽松预期→股市涨 |
| 财政收入 YoY | -0.3681 | 10月 | 负相关 | 27% | 财政收缩→减税增支预期→股市涨 |
| 非银存款 YoY | +0.30 | 6月 | 正相关 | 22% | 资金直接入市 |
| M2 YoY | +0.20 | 6月 | 正相关 | 14% | 信用环境宽松 |

#### 趋势确认指标（5个）

| 指标 | 相关性 r | 说明 |
|------|---------|------|
| BDI 干散货 YoY | +0.3629 | 全球需求同步 |
| PMI 制造业 | +0.20 | 景气度确认 |
| 两融余额 YoY | — | 杠杆水位 |
| SHIBOR 隔夜 | — | 资金面即时 |
| 非银存款 MoM | — | 资金流入即时 |

### 预测流程

```
1. 分位数标准化：各预测指标当前值 → 过去60月分位数 → 归一化到 [-1, +1]
2. 方向反转：负相关指标取反（负值变正值 = 看涨信号）
3. 加权求和：Σ(分数 × 权重) / 总权重 → 预测分数
4. 趋势确认：5个确认指标中与预测方向一致的比例
5. 输出结论：
   - score > +0.2 → 看涨，score < -0.2 → 看跌，中间 → 震荡
   - 确认度 > 70% 高度确认，40-70% 部分确认，< 40% 矛盾信号
```

### 验证闭环

每次运行自动检查未验证的旧预测：

1. 回填实际 3 个月后上证指数收益率到 `predictions.csv`
2. 计算方向准确率和 MAE
3. 基于准确率微调权重：准确率 > 70% → 权重 +5%（上限 50%），< 50% → 权重 -5%（下限 5%）

### 预测记录

历史预测保存在 `data/predictions.csv`，包含预测分数、方向、置信度、各指标贡献、趋势确认度、实际收益率验证结果。

## License

MIT
