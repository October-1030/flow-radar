# Flow Radar - 流动性雷达

加密货币交易监控系统，通过分析表面信号和隐藏订单流来识别市场真实意图。

## 功能特点

### 三大核心系统

| 系统 | 功能 | 启动命令 |
|------|------|----------|
| **Command Center** | 战情指挥中心，显示完整市场数据 | `start_DOGE.bat` |
| **Iceberg Detector** | 冰山单检测，识别隐藏大单 | `start_iceberg_DOGE.bat` |
| **综合判断系统** | 整合表面+暗盘，智能判断+声音提醒 | `start_alert_DOGE.bat` |

### 综合判断系统 (推荐)

整合了所有功能，一个窗口搞定：

```
表面信号 (Surface)
├── 战略地图: 1D/4H/15M 趋势
├── 综合分数: 0-100
├── 鲸鱼流: 大额交易净流入
├── 散户流: 小额交易方向
└── 资金费率: 市场情绪

暗盘信号 (Hidden)
├── 冰山买单: 隐藏买入量
├── 冰山卖单: 隐藏卖出量
├── 买卖比: 买方/卖方力量对比
└── 最强信号: 最大隐藏订单

综合判断
├── 洗盘吸筹: 表面空 + 暗盘多 → 可以关注
├── 诱多出货: 表面多 + 暗盘空 → 不要追高
├── 真实下跌: 都在卖 → 不要抄底
├── 真实上涨: 都在买 → 可以买入
└── 暗中吸筹: 表面平静 + 暗盘买 → 关注机会
```

## 安装

```bash
# 克隆项目
git clone https://github.com/October-1030/flow-radar.git
cd flow-radar

# 安装依赖
pip install ccxt rich aiohttp
```

## 快速开始

### Windows 用户

直接双击启动脚本：

```
start_DOGE.bat           # 战情指挥中心
start_alert_DOGE.bat     # 综合判断系统 (推荐)
start_iceberg_DOGE.bat   # 冰山检测器
```

### 命令行启动

```bash
# 综合判断系统 (推荐)
python alert_monitor.py -s DOGE/USDT

# 战情指挥中心
python command_center.py -s DOGE/USDT

# 冰山检测器
python iceberg_detector.py -s DOGE/USDT
```

### 监控其他币种

```bash
python alert_monitor.py -s BTC/USDT
python alert_monitor.py -s ETH/USDT
python alert_monitor.py -s SOL/USDT
```

## 判断逻辑

### 分数计算 (0-100)

```
基础分: 50
+ MTF趋势: 每个多头时间框架 +10，空头 -10
+ OBI (订单簿失衡): -20 到 +20
+ 鲸鱼流: 根据净流入金额 -15 到 +15
+ CVD (累计成交量差): -10 到 +10
```

### 信号判断

| 表面信号 | 暗盘信号 | 结论 | 建议 |
|----------|----------|------|------|
| 分数≤35 偏空 | 买单>卖单 偏多 | 洗盘吸筹 | 可以关注 |
| 分数≥60 偏多 | 卖单>买单 偏空 | 诱多出货 | 不要追高 |
| 分数≤35 偏空 | 卖单>买单 偏空 | 真实下跌 | 不要抄底 |
| 分数≥60 偏多 | 买单>卖单 偏多 | 真实上涨 | 可以买入 |
| 分数中性 | 买单>卖单 偏多 | 暗中吸筹 | 关注机会 |
| 分数中性 | 卖单>买单 偏空 | 暗中出货 | 小心风险 |

### 操作建议等级

```
🟢 明确买入信号:
   "可以买入!"   → 立即考虑买入，表面+暗盘都确认
   "可以关注!"   → 关注机会，准备买入，暗盘有支撑

🟡 观望信号:
   "观望偏多"    → 不急着买，但可以准备，等确认信号
   "观望"        → 等待，不操作
   "观望偏空"    → 不急着卖，但要小心

🔴 明确警告信号:
   "不要追高!"   → 绝对不要买！表面涨但暗盘在出货
   "不要抄底!"   → 绝对不要买！表面和暗盘都在卖
   "小心!"       → 有风险，考虑减仓或卖出
```

### 典型案例

**诱多出货 (最危险)**
```
分数: 97 (超强多)  ← 看起来要暴涨！
暗盘: 净卖5000万U  ← 实际在疯狂出货！
结论: 诱多出货！不要追高！

散户看到分数97冲进去 → 被套
系统看到暗盘出货 → 警告你别买
```

**洗盘吸筹 (机会)**
```
分数: 25 (偏空)    ← 看起来要跌！
暗盘: 净买3000万U  ← 实际在疯狂抄底！
结论: 洗盘吸筹！可以关注！

散户看到分数25恐慌卖出 → 卖在底部
系统看到暗盘吸筹 → 提示你关注
```

### 声音提醒

- **高音上升**: 买入信号 (分数突破60/70 + 暗盘确认)
- **低音下降**: 卖出信号 (分数跌破35/25)
- **急促警告**: 危险信号 (分数高但暗盘在出货)

## 数据来源

- **交易所**: OKX (可在 config/settings.py 修改)
- **数据类型**:
  - 现货订单簿 (20档)
  - 最近成交记录 (100笔)
  - K线数据 (1D/4H/15M)
  - 合约数据 (资金费率/持仓量/多空比)

## 文件结构

```
flow-radar/
├── command_center.py      # 战情指挥中心
├── iceberg_detector.py    # 冰山检测器
├── alert_monitor.py       # 综合判断系统
├── config/
│   └── settings.py        # 配置文件
├── core/
│   ├── indicators.py      # 指标计算
│   └── derivatives.py     # 合约数据
├── start_DOGE.bat         # 快捷启动脚本
├── start_alert_DOGE.bat
└── start_iceberg_DOGE.bat
```

## 配置说明

编辑 `config/settings.py`:

```python
CONFIG_MARKET = {
    'exchange': 'okx',           # 交易所
    'symbol': 'DOGE/USDT',       # 默认交易对
    'whale_threshold_usd': 10000, # 鲸鱼交易阈值 (USD)
    'orderbook_depth': 20,       # 订单簿深度
}

CONFIG_ICEBERG = {
    'intensity_threshold': 2.0,   # 冰山强度阈值
    'min_cumulative_volume': 1000, # 最小累计成交量
    'min_refill_count': 3,        # 最小补单次数
    'detection_window': 300,      # 检测窗口 (秒)
}
```

## 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。加密货币交易具有高风险，请谨慎决策，自行承担交易风险。

## License

MIT
