# 股市宏观分析系统

基于**非银金融机构存款增速 + 27 个宏观指标**的股市见顶信号检测系统 + **走势预测引擎 v4.1**。通过追踪资金面、信用周期、实体经济和市场情绪四个维度的变化，实现市场阶段性顶部的自动预警；同时基于 3 个领先指标的历史相关性加权，生成 3 个月窗口的走势预测，并利用**自适应阈值 + 看跌增强确认 + 13 个确认指标**提升预测可靠性。

## 核心逻辑

```
居民存款（慢变量，领先5-7月）
    ↓  资金搬家
非银金融机构存款（快变量，领先0-3月）≈ 券商保证金 + 基金存款 + 信托/保险存款
    ↓  直接入场
上证指数（即时响应）
```

当非银存款增速从高位回落、或出现存款涨而指数跌的背离时，往往意味着资金正在撤离股市，是见顶的重要预警信号。系统同时监控 M2/PMI/BDI/社零/信贷脉冲/USDCNY汇率/成交量等 27 个宏观指标，通过多维度交叉验证提升信号可靠性。

## 项目结构

```
股市分析/
├── run.py                          # 主入口：一键执行全流程（6步）
├── init_data.py                    # 核心数据初始化（存款+指数→CSV）
├── init_macro_data.py              # 宏观指标数据初始化（全部25个宏观指标→CSV）
├── analyze_new_indicators.py       # 新指标滞后相关性分析脚本（独立运行）
├── requirements.txt                # Python 依赖
├── run.bat                         # 双击一键运行（生成 HTML 报告 + 图表 + 自动打开浏览器）
├── setup_schedule.bat              # Windows 定时任务安装（每周一自动运行）
│
├── src/                            # 核心模块
│   ├── config.py                   # 全局配置：JSON 加载器 + 路径 + 默认值回退
│   ├── scraper.py                  # 数据采集：akshare 指数 + 27个宏观指标（含信贷脉冲+USDCNY+成交量）
│   ├── data_manager.py             # CSV 读写、29个数据源外连接合并、增量更新
│   ├── indicators.py               # 衍生指标：MoM/YoY/滚动均值/剪刀差等
│   ├── signal_detector.py          # 信号检测引擎：15个信号 + 风险评级 + 回测
│   ├── prediction.py               # 走势预测引擎 + 自学习系统（偏差追踪 + 智能权重调整）
│   ├── chart_generator.py          # 图表生成：6张分析图表 + generate_all_charts() 包装
│   ├── html_builder.py             # HTML 报告构建器（CSS 深色主题 + Base64 图片内嵌 + 8 章节）
│   └── report_generator.py         # HTML 报告生成器（调用 html_builder，输出 .html）
│
├── config/                         # JSON 配置文件（可手动编辑 + 程序自动微调）
│   ├── signal_config.json          # 信号检测阈值（15个信号 + 风险等级 + 历史顶底）
│   └── prediction_config.json      # 预测引擎v4.1配置（权重 + 13个确认指标 + 自适应阈值 + 看跌确认 + 自学习参数）
│
├── docs/                           # 分析文档
│   └── indicator_evaluation_and_new_sources.md  # 全量指标评估 + 新数据源报告
│
├── data/                           # 数据目录（29个CSV）
│   ├── deposits.csv                # 存款月度数据（2015.01 - 最新）
│   ├── sh_index.csv                # 上证指数月度收盘价 + 成交量
│   ├── predictions.csv             # 走势预测记录（含验证结果）
│   ├── prediction_deviations.jsonl # 预测偏差日志（自学习输入）
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
│   ├── macro_fiscal.csv            # 财政收入当月同比增速
│   ├── macro_enterprise_boom.csv   # 企业景气指数（季度）
│   ├── macro_consumer_confidence.csv # 消费者信心指数
│   ├── macro_lpi.csv               # 物流景气指数
│   ├── macro_real_estate.csv       # 国房景气指数
│   ├── macro_unemployment.csv      # 城镇调查失业率
│   ├── macro_trade.csv             # 海关进出口（出口/进口同比+金额）
│   ├── macro_industry.csv          # 工业增加值同比
│   ├── macro_fa_investment.csv     # 固定资产投资同比
│   ├── macro_insurance.csv         # 保险保费收入同比
│   ├── macro_enterprise_price.csv  # 企业商品价格指数
│   ├── macro_gdp.csv               # GDP增速（季度）
│   ├── macro_credit.csv            # 信贷脉冲（新增信贷YoY + 人民币贷款YoY）
│   ├── macro_usdcny.csv             # 美元兑人民币汇率（中国银行中间价，月度均值+环比）
│   ├── macro_vegetable_basket.csv  # 菜篮子价格指数（日频→月度聚合）
│   └── macro_commodity_price.csv   # 大宗商品价格指数（日频→月度聚合）
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
│   └── YYYY-MM-DD_report.html      # HTML 单文件报告（深色主题，6 张 Base64 内嵌图表，8 章节）
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
- **报告**：`reports/` 目录下的 HTML 单文件报告（深色主题，含 6 张内嵌图表 + 走势预测章节）
- **日志**：`logs/` 目录下的日志文件

## 数据管线

### 数据来源

#### 核心指标（2个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 居民/非银存款 | 中国人民银行 | 月度 | household_deposit, non_bank_deposit | 万元 |
| 上证指数 | akshare `stock_zh_index_daily` | 月度 | sh_close | 日线→月末收盘 |

#### 宏观第一批（3个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| M2/M1/M0 | akshare `macro_china_money_supply` | 月度 | m2_amount, m2_yoy 等 | 信用周期核心 |
| PMI | akshare `macro_china_pmi` | 月度 | pmi_manufacturing, pmi_non_manufacturing | 景气先行指标 |
| 全社会用电量 | akshare `macro_china_society_electricity` | 月度 | electricity_total_yoy 等 | GDP高频替代 |

#### 宏观第二批（7个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 两融余额 | akshare `macro_china_market_margin_sh` | 日度→月度 | margin_balance, margin_yoy | 散户杠杆度量 |
| SHIBOR | akshare `macro_china_shibor_all` | 日度→月度 | shibor_on_avg, shibor_1w_avg | 资金面温度 |
| LPR | akshare `macro_china_lpr` | 日度→月度 | lpr_1y, lpr_5y | 货币政策风向标 |
| CPI | akshare `macro_china_cpi` | 月度 | cpi_yoy, cpi_mom | 消费价格 |
| PPI | akshare `macro_china_ppi` | 月度 | ppi_yoy | 工业品价格 |
| 北向资金 | akshare `stock_hsgt_hist_em` | 日度→月度 | northbound_net_buy | 外资风向标 |

#### 宏观第三批（3个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| BDI 干散货指数 | akshare `macro_china_freight_index` | 日度→月度 | bdi_value, bdi_yoy | 全球需求同步指标 |
| 社消零售总额 | akshare `macro_china_consumer_goods_retail` | 月度 | retail_yoy | 消费端景气度 |
| 财政收入 | akshare `macro_china_czsr` | 月度 | fiscal_yoy | 政策空间参考 |

#### 宏观第四批 — 冷门/替代指标（11个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 企业景气指数 | akshare `macro_china_enterprise_boom_index` | 季度 | enterprise_boom_index | 企业信心（r=0.277, 滞后8月） |
| 消费者信心指数 | akshare `macro_china_consumer_confidence_index` | 月度 | consumer_confidence_index | 消费者预期 |
| 物流景气指数 | akshare `macro_china_lpi` | 月度 | lpi_index | 经济活跃度（r=0.150, 滞后1月） |
| 国房景气指数 | akshare `macro_china_real_estate` | 月度 | real_estate_index | 房地产景气度 |
| 城镇调查失业率 | akshare `macro_china_urban_unemployment` | 月度 | unemployment_rate | 就业市场 |
| 海关进出口 | akshare `macro_china_trade` | 月度 | export_yoy, import_yoy 等 | 外贸景气度 |
| 工业增加值 | akshare `macro_china_industry` | 月度 | industrial_production_yoy | 工业活跃度（r=0.174, 滞后5月） |
| 固定资产投资 | akshare `macro_china_fa_investment` | 月度 | fa_investment_yoy | 投资端景气度 |
| 保险保费收入 | akshare `macro_china_insurance_premium` | 月度 | insurance_premium_yoy | 保险资金入市参考 |
| 企业商品价格指数 | akshare `macro_china_enterprise_price` | 月度 | enterprise_price_yoy | 上游价格压力 |
| GDP增速 | akshare `macro_china_gdp` | 季度 | gdp_yoy | 经济总量增速 |

#### 周度聚合数据（2个）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 菜篮子价格指数 | akshare `macro_china_vegetable_basket` | 日度→月度 | vegetable_basket_yoy | 食品通胀高频 |
| 大宗商品价格指数 | akshare `macro_china_commodity_price` | 日度→月度 | commodity_price_yoy | 商品通胀高频 |

#### 第六批：汇率指标（替代失效的北向资金）

| 数据 | 来源 | 更新频率 | 数据列 | 说明 |
|------|------|----------|--------|------|
| 美元兑人民币汇率 | akshare `currency_boc_safe` | 日度→月度 | usdcny（均值）, usdcny_mom（环比%） | 中国银行中间价，389条月度数据（1994-2026），接口非常稳定 |

> **设计决策：USDCNY 作为确认指标而非预测指标**
>
> USDCNY 水平值与上证3月收益 r=+0.45***（正相关：人民币贬值→利好出口→A股上涨），相关性在所有已测试指标中名列前茅。但设计上将其放在确认指标而非预测指标池，原因如下：
>
> 1. **预测指标正负平衡**：当前3个预测指标（非银存款正相关 46.4%、社零负相关 37.3%、M2负相关 16.3%）保持1正2负平衡。加入正相关 USDCNY 会打破平衡，使系统系统性偏向看涨。
> 2. **本质是同步/领先确认**：USDCNY 的强相关性主要反映人民币贬值周期与A股牛市的共现（2015、2020、2024），更像宏观环境确认而非独立预测源。黄金分析也证实 USDCNY 的 A 股信号通道与出口/外资流入紧密关联。
> 3. **权重分配冲突**：加入第4个预测指标后 M2 权重将被压缩至 ~8%（接近5%下限），失去意义。且 USDCNY 水平值（绝对数值如 6.84）用分位数标准化做预测不直观。
>
> **结论：让它做"裁判"比做"选手"更靠谱。** 作为确认指标，当看涨预测 + USDCNY 处于高位时确认度大幅提升；当看涨预测 + USDCNY 快速升值时提供反向警示，不干扰核心评分的稳定性。

### 数据格式

所有 CSV 统一格式：第一列为 `date`（YYYY-MM-DD），后续为指标列，编码 UTF-8-sig。

## 信号检测机制

系统定义了 **15 个信号**（4 个存款类 + 9 个宏观类 + 2 个 v3.0 新增）和 **4 级风险等级**：

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
| 信贷脉冲飙升 | WARNING | 新增信贷 YoY 2个月内飙升 >30百分点 | 政策强刺激信号 |
| 量价背离（缩量上涨）| WARNING | 指数连续3月上涨但成交量连续2月下降 | 上涨动能衰竭 |

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

### 7. 冷门替代指标（企业景气 + 物流 + 工业增加值）
第四批指标通过 0-12 月滞后 Pearson 相关性验证，虽未达严格预测阈值（|r|>0.3 p<0.05），但边际显著（0.05 < p < 0.10），作为确认指标纳入。企业景气指数（季度频率，r=0.277, 滞后8月）和物流景气指数（月度，r=0.150, 滞后1月）提供实体经济和供应链活跃度的交叉验证。

### 8. 通胀高频监测（菜篮子 + 大宗商品）
日度数据聚合为月度同比，用于捕捉食品和商品价格的边际变化，辅助 CPI/PPI 判断。

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

- **Python 3.10+**（开发环境 Python 3.14）
- **pandas**：数据处理与计算
- **matplotlib**：图表生成（中文字体自动适配）
- **akshare**：全量数据采集（指数 + 27个宏观指标）
- **scipy**：滞后 Pearson 相关性分析
- **jsonschema**：JSON 配置校验

## 已知限制

1. 北向资金：akshare `stock_hsgt_hist_em` 自 2024-08 后当日成交净买额为 null，已由 USDCNY 汇率指标替代其外资风向标功能
2. 社融：akshare `macro_china_shrzgm` 存在 SSL 错误，尚未接入，需要替代数据源
3. 以下 akshare 接口不可用：全社会客货运（失效）、零售价格指数（失效）、能繁母猪存栏（返回 None）、乘联会汽车销量（JSONDecodeError）
4. 月度频率，对日内/周度级别的市场波动无感知（菜篮子/大宗商品已聚合为月度）
5. 历史回测显示对部分市场顶部（如2015年6月、2021年2月）的提前捕获能力有限，信号算法仍在持续优化
6. 预测系统基于历史相关性，极端市场环境下（如黑天鹅事件）预测可靠性会下降
7. 第四批冷门指标均未达 |r|>0.3 p<0.05 的严格预测阈值，仅作为边际确认指标纳入
8. 财政收入（fiscal_yoy）已在 v4.1 中从预测指标移除（0% 准确率），仅作为修正机制的信号源保留

## 走势预测系统

### 设计原理

基于第三批宏观指标的 Pearson 滞后交叉相关性分析（详见 `docs/batch3_analysis.md`），系统将指标分为两类：

- **预测指标**（领先 6+ 个月）：当前值可预测未来走势方向
- **趋势确认指标**（同步）：验证当前趋势是否延续

### 指标分类

#### 预测指标（3个，v4.1 移除财政收入）

| 指标 | 相关性 r | 滞后月数 | 方向 | 权重 | 说明 |
|------|---------|---------|------|------|------|
| 非银存款 YoY | +0.30 | 6月 | 正相关 | 46.4% | 资金直接入市（分位数准确率67.3%，最强） |
| 社消零售 YoY | -0.50 | 10月 | 负相关 | 37.3% | 消费走弱→政策宽松预期→股市涨 |
| M2 YoY | +0.20 | 6月 | **负相关** | 16.3% | M2高→利好已定价→收益降低 |

> **v4.1 变更**：财政收入（fiscal_yoy）因0%准确率、0贡献从预测指标中移除。剩余3指标权重重新归一化（37.34%→46.40%、35.12%→37.34%、15.30%→16.26%）。USDCNY 汇率作为确认指标纳入（详见数据来源"第六批"章节的设计决策说明）。

#### 趋势确认指标（13个，v4.1 新增 USDCNY×2）

| 指标 | 相关性 r | 说明 |
|------|---------|------|
| BDI 干散货 YoY | +0.3629 | 全球需求同步 |
| PMI 制造业 | +0.20 | 景气度确认 |
| 两融余额 YoY | — | 杠杆水位 |
| SHIBOR 隔夜 | — | 资金面即时 |
| 非银存款 MoM | — | 资金流入即时 |
| 工业增加值 YoY | +0.174 | 工业活跃度边际确认（滞后5月） |
| 企业景气指数 | +0.277 | 企业信心边际确认（滞后8月，季度） |
| 物流景气指数 | +0.150 | 经济活动活跃度边际确认（滞后1月） |
| 信贷脉冲 | — | 信用扩张/收缩即时确认（v3.0 新增） |
| 均线斜率 | — | 趋势方向确认（v3.0 新增） |
| 成交量变化率 | — | 市场活跃度确认（v3.0 新增） |
| **USDCNY 水平值** | **+0.4463*** | **外资风向标：人民币贬值→利好出口→A股上涨（v4.1 新增）** |
| **USDCNY 环比** | **-0.3652*** | **汇率短期变化，负相关：升值加速→短期看跌（v4.1 新增）** |

### 预测流程（v4.1）

```
1. 分位数标准化：各预测指标当前值 → 过去60月分位数 → 归一化到 [-1, +1]
2. 方向反转：负相关指标取反（负值变正值 = 看涨信号）
3. 加权求和：Σ(分数 × 权重) / 总权重 → 原始预测分数
4. 自适应阈值：根据6月收益波动率判断市场状态
   - 趋势市(波动>4%): 牛熊阈值降低0.04 → 更容易发出方向性预测
   - 震荡市(波动≤4%): 牛熊阈值提高0.04 → 偏向中性预测
5. 方向判定：score > effective_bull → 看涨，score < effective_bear → 看跌
6. 趋势确认：13个确认指标中与预测方向一致的比例
7. 看跌增强确认：看跌预测需确认度 ≥ 40%，否则降级为中性
8. 输出结论：
   - 看涨/看跌/中性（含市场状态和自适应阈值信息）
   - 确认度 > 70% 高度确认，40-70% 部分确认，< 40% 矛盾信号
```

### 验证闭环

每次运行自动检查未验证的旧预测：

1. 回填实际 3 个月后上证指数收益率到 `predictions.csv`
2. 计算方向准确率和 MAE
3. 基于准确率微调权重（按指标独立调整）：准确率 > 65% → 权重 +5%（上限 50%），< 45% → 权重 -5%（下限 5%），需 ≥5 个样本
4. 偏差记录到 `data/prediction_deviations.jsonl`（标记误导指标 + 原因推测）
5. 默认每 3 次运行执行一次权重调整（可配置）

### 权重计算方法（v2.0）

权重基于**全样本(2015-2026) 0-12月滞后 Pearson r × 3月累计收益率**计算，拆分训练集(2015-2021)和验证集(2022-2026)检验方向稳定性：

- 训练集计算各指标最优滞后期的相关性系数
- 验证集检验方向是否一致（FLIP 指标施加 |r|×0.5 惩罚）
- 按 |r| 比例归一化分配权重
- 配置元数据：`prediction_config.json` 含 `r_p`、`direction_stable`、`test_r`、`test_p`、`correlation_note` 字段

### 回测结果（v3.0，122条已验证预测）

| 指标 | v2.0 | v3.0 | 变化 |
|------|------|------|------|
| 三分类准确率 | 40.2% | 47.5% | +7.3% |
| 二分类准确率 | 52.5% | 56.6% | +4.1% |
| 看涨胜率 | 54.8% | 58.7% | +3.9% |
| 看涨平均收益 | +2.03% | +2.14% | +0.11% |
| 看跌数 | 23 | 18 | -5 (减少误判) |
| Q5 平均收益 | +3.91% | +3.91% | 不变 |
| Q5 胜率 | 80.0% | 80.0% | 不变 |

v3.0 主要改进：看跌增强确认将低确认度看跌预测降级为中性，三分类准确率提升 7.3 个百分点。五分位收益 Q1→Q5 非严格单调（Q2/Q4 存在波动），但 Q5 极端信号高度可靠。

### 预测记录

历史预测保存在 `data/predictions.csv`，包含预测分数、方向、置信度、各指标贡献、趋势确认度、实际收益率验证结果。

## License

MIT
