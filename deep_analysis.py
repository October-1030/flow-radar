#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度盘面分析 - 价格与冰山订单关系"""

import sys
import io
import gzip
import json
from pathlib import Path
from datetime import datetime
import statistics

# 设置Windows控制台UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_all_states():
    """加载所有状态数据"""
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")
    all_states = []

    for file_path in sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz")):
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event.get('type') == 'state':
                            data = event.get('data', {})
                            all_states.append({
                                'ts': event.get('ts'),
                                'time': datetime.fromtimestamp(event.get('ts')),
                                'state': data.get('state_name', 'Unknown'),
                                'score': data.get('score', 0),
                                'iceberg_ratio': data.get('iceberg_ratio', 0),
                                'price': data.get('price', 0),
                                'confidence': data.get('confidence', 0),
                                'recommendation': data.get('recommendation', ''),
                                'cvd': data.get('cvd_total', 0),
                                'divergence': data.get('divergence', '')
                            })
                    except:
                        continue
        except:
            continue

    all_states.sort(key=lambda x: x['ts'])
    return all_states

def analyze_price_iceberg_correlation(states):
    """分析价格与冰山订单的关系"""
    print("\n" + "="*80)
    print("🔬 价格 vs 冰山订单深度分析")
    print("="*80)

    # 按冰山买单比例分组
    strong_buy = [s for s in states if s['iceberg_ratio'] > 0.75]  # 超强买方
    moderate_buy = [s for s in states if 0.55 <= s['iceberg_ratio'] <= 0.75]  # 偏多
    neutral = [s for s in states if 0.45 < s['iceberg_ratio'] < 0.55]  # 中性
    moderate_sell = [s for s in states if 0.25 <= s['iceberg_ratio'] <= 0.45]  # 偏空
    strong_sell = [s for s in states if s['iceberg_ratio'] < 0.25]  # 超强卖方

    print(f"\n📊 冰山订单分段统计:")
    print(f"   超强买方 (>75%): {len(strong_buy):3d} 次 - 平均价格: ${statistics.mean([s['price'] for s in strong_buy]):.5f}" if strong_buy else "   超强买方 (>75%): 0 次")
    print(f"   偏多 (55-75%):   {len(moderate_buy):3d} 次 - 平均价格: ${statistics.mean([s['price'] for s in moderate_buy]):.5f}" if moderate_buy else "   偏多 (55-75%):   0 次")
    print(f"   中性 (45-55%):   {len(neutral):3d} 次 - 平均价格: ${statistics.mean([s['price'] for s in neutral]):.5f}" if neutral else "   中性 (45-55%):   0 次")
    print(f"   偏空 (25-45%):   {len(moderate_sell):3d} 次 - 平均价格: ${statistics.mean([s['price'] for s in moderate_sell]):.5f}" if moderate_sell else "   偏空 (25-45%):   0 次")
    print(f"   超强卖方 (<25%): {len(strong_sell):3d} 次 - 平均价格: ${statistics.mean([s['price'] for s in strong_sell]):.5f}" if strong_sell else "   超强卖方 (<25%): 0 次")

    # 分析价格变化与冰山订单的对应关系
    print(f"\n💡 关键发现:")

    # 计算不同冰山比例下的价格涨跌
    if strong_buy:
        sb_prices = [s['price'] for s in strong_buy]
        sb_change = ((sb_prices[-1] - sb_prices[0]) / sb_prices[0]) * 100 if len(sb_prices) > 1 else 0
        print(f"   超强买方期间价格变化: {sb_change:+.2f}%")

    # 寻找冰山订单与价格背离
    divergences = []
    for i in range(1, len(states)):
        prev = states[i-1]
        curr = states[i]

        price_change = ((curr['price'] - prev['price']) / prev['price']) * 100
        iceberg_change = (curr['iceberg_ratio'] - prev['iceberg_ratio']) * 100

        # 价格下跌但冰山买单增加 = 吸筹
        if price_change < -0.1 and iceberg_change > 5:
            divergences.append({
                'type': '吸筹机会',
                'time': curr['time'],
                'price': curr['price'],
                'price_change': price_change,
                'iceberg_ratio': curr['iceberg_ratio']
            })

        # 价格上涨但冰山买单减少 = 出货
        elif price_change > 0.1 and iceberg_change < -5:
            divergences.append({
                'type': '出货警告',
                'time': curr['time'],
                'price': curr['price'],
                'price_change': price_change,
                'iceberg_ratio': curr['iceberg_ratio']
            })

    if divergences:
        print(f"\n⚠️  价格与冰山订单背离事件 ({len(divergences)} 次):")
        for div in divergences[-5:]:  # 显示最近5次
            emoji = "🟢" if div['type'] == '吸筹机会' else "🔴"
            print(f"   {emoji} [{div['time'].strftime('%m-%d %H:%M')}] ${div['price']:.5f} - {div['type']}")
            print(f"      价格变化: {div['price_change']:+.2f}% | 冰山买单比: {div['iceberg_ratio']*100:.1f}%")

def identify_key_signals(states):
    """识别关键买卖信号"""
    print("\n" + "="*80)
    print("🎯 关键交易信号识别")
    print("="*80)

    buy_signals = []
    sell_signals = []

    for i in range(1, len(states)):
        curr = states[i]

        # 强买入信号：暗中吸筹 + 高冰山买单 + 看涨背离
        if (curr['state'] == '暗中吸筹' and
            curr['iceberg_ratio'] > 0.75 and
            curr['divergence'] == 'bullish' and
            curr['confidence'] > 60):
            buy_signals.append({
                'time': curr['time'],
                'price': curr['price'],
                'score': curr['score'],
                'iceberg_ratio': curr['iceberg_ratio'],
                'confidence': curr['confidence'],
                'reason': '强吸筹信号'
            })

        # 真实上涨确认
        elif curr['state'] == '真实上涨':
            buy_signals.append({
                'time': curr['time'],
                'price': curr['price'],
                'score': curr['score'],
                'iceberg_ratio': curr['iceberg_ratio'],
                'confidence': curr['confidence'],
                'reason': '真实上涨'
            })

        # 卖出信号：诱多出货或暗中出货
        if curr['state'] in ['诱多出货', '暗中出货']:
            sell_signals.append({
                'time': curr['time'],
                'price': curr['price'],
                'score': curr['score'],
                'iceberg_ratio': curr['iceberg_ratio'],
                'confidence': curr['confidence'],
                'reason': curr['state']
            })

    print(f"\n🟢 买入信号 ({len(buy_signals)} 个):")
    if buy_signals:
        for sig in buy_signals[-10:]:
            print(f"   [{sig['time'].strftime('%m-%d %H:%M')}] ${sig['price']:.5f}")
            print(f"      {sig['reason']} | 分数:{sig['score']} | 冰山买单:{sig['iceberg_ratio']*100:.1f}% | 置信:{sig['confidence']:.0f}%")
    else:
        print("   暂无明确买入信号")

    print(f"\n🔴 卖出信号 ({len(sell_signals)} 个):")
    if sell_signals:
        for sig in sell_signals[-10:]:
            print(f"   [{sig['time'].strftime('%m-%d %H:%M')}] ${sig['price']:.5f}")
            print(f"      {sig['reason']} | 分数:{sig['score']} | 冰山买单:{sig['iceberg_ratio']*100:.1f}% | 置信:{sig['confidence']:.0f}%")
    else:
        print("   暂无卖出警告 ✅")

def calculate_holding_profit(states):
    """计算持仓收益分析"""
    print("\n" + "="*80)
    print("💰 假设交易收益分析")
    print("="*80)

    # 模拟：在第一个强买入信号买入，当前价格卖出
    strong_accumulation = [s for s in states if s['state'] == '暗中吸筹' and s['iceberg_ratio'] > 0.8]

    if strong_accumulation and len(states) > 0:
        entry = strong_accumulation[0]
        current = states[-1]

        profit_pct = ((current['price'] - entry['price']) / entry['price']) * 100

        print(f"\n📈 策略：在第一个强吸筹信号买入")
        print(f"   买入时间: {entry['time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   买入价格: ${entry['price']:.5f}")
        print(f"   买入理由: {entry['state']} (冰山买单 {entry['iceberg_ratio']*100:.1f}%)")
        print(f"")
        print(f"   当前时间: {current['time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   当前价格: ${current['price']:.5f}")
        print(f"   当前状态: {current['state']}")
        print(f"")
        print(f"   持仓收益: {profit_pct:+.2f}%")
        print(f"   持仓时长: {((current['ts'] - entry['ts']) / 3600):.1f} 小时")

        if profit_pct > 0:
            print(f"\n   ✅ 策略有效！跟随冰山买单获利")
        else:
            print(f"\n   ⏳ 耐心持有，冰山买单仍在 {current['iceberg_ratio']*100:.1f}%")

def expert_recommendation(states):
    """专业操作建议"""
    print("\n" + "="*80)
    print("👨‍💼 专业盯盘建议")
    print("="*80)

    current = states[-1]
    recent = states[-20:] if len(states) > 20 else states

    avg_iceberg = statistics.mean([s['iceberg_ratio'] for s in recent])
    avg_score = statistics.mean([s['score'] for s in recent])

    print(f"\n📊 近期市场特征 (最近{len(recent)}个数据点):")
    print(f"   平均冰山买单: {avg_iceberg*100:.1f}%")
    print(f"   平均分数: {avg_score:.1f}")
    print(f"   主要状态: {current['state']}")

    print(f"\n💡 专业判断:")

    if avg_iceberg > 0.75 and current['state'] == '暗中吸筹':
        print(f"   🟢 【强烈吸筹】")
        print(f"      - 大户持续建仓，冰山买单高达 {current['iceberg_ratio']*100:.1f}%")
        print(f"      - 表面分数仅 {current['score']} 分，价格被压制")
        print(f"      - 这是典型的洗盘吸筹，散户恐慌卖出，大户接盘")
        print(f"")
        print(f"   📋 操作建议:")
        print(f"      1. 可以考虑分批建仓")
        print(f"      2. 设置止损在关键支撑位")
        print(f"      3. 等待表面信号转强（分数>60）作为确认")
        print(f"      4. 目标：当冰山买单持续+分数突破，可能快速上涨")

    elif avg_iceberg > 0.65 and current['score'] >= 60:
        print(f"   🟢 【真实上涨】")
        print(f"      - 表面和暗盘都在买入")
        print(f"      - 分数 {current['score']} + 冰山买单 {current['iceberg_ratio']*100:.1f}%")
        print(f"      - 趋势已确认")
        print(f"")
        print(f"   📋 操作建议:")
        print(f"      1. 已持仓可继续持有")
        print(f"      2. 未持仓可逢回调买入")
        print(f"      3. 关注冰山买单是否持续>65%")

    elif avg_iceberg < 0.45 and current['score'] >= 60:
        print(f"   🔴 【诱多出货】")
        print(f"      - 表面分数 {current['score']} 看起来强势")
        print(f"      - 但冰山买单仅 {current['iceberg_ratio']*100:.1f}%，大户在卖")
        print(f"      - 散户追高，大户出货")
        print(f"")
        print(f"   📋 操作建议:")
        print(f"      1. 绝对不要追高！")
        print(f"      2. 已持仓考虑止盈")
        print(f"      3. 等待冰山买单回升再说")

    elif avg_iceberg < 0.45 and current['score'] <= 35:
        print(f"   🔴 【真实下跌】")
        print(f"      - 表面和暗盘都在卖")
        print(f"      - 不是洗盘，是真跌")
        print(f"")
        print(f"   📋 操作建议:")
        print(f"      1. 不要抄底！")
        print(f"      2. 等待冰山买单出现（>65%）")
        print(f"      3. 等待止跌信号")

    else:
        print(f"   🟡 【观望】")
        print(f"      - 当前市场方向不明确")
        print(f"      - 等待更清晰的信号")

    print(f"\n⚠️  风险提示:")
    print(f"   - CVD当前: {current['cvd']:,.0f}")
    print(f"   - 背离状态: {current['divergence']}")
    print(f"   - 置信度: {current['confidence']:.1f}%")
    print(f"   - 加密货币波动大，注意风险控制")
    print(f"   - 建议仓位不超过总资金的 10-20%")

def main():
    print("正在加载数据...")
    states = load_all_states()

    if not states:
        print("没有找到数据！")
        return

    print(f"加载了 {len(states)} 个数据点")

    # 执行各项分析
    analyze_price_iceberg_correlation(states)
    identify_key_signals(states)
    calculate_holding_profit(states)
    expert_recommendation(states)

    print("\n" + "="*80)
    print("分析完成！")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
