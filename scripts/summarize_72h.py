#!/usr/bin/env python3
"""
Flow Radar - 72h Validation Summary Script
流动性雷达 - 72小时验证汇总脚本

P3: 自动统计验证期间的信号分布和关键指标
"""

import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_events(events_dir: str = "./storage/events", days: int = 3) -> List[Dict]:
    """
    加载最近 N 天的事件数据

    Args:
        events_dir: 事件目录
        days: 天数

    Returns:
        List[Dict]: 事件列表
    """
    events = []
    dir_path = Path(events_dir)

    if not dir_path.exists():
        print(f"事件目录不存在: {events_dir}")
        return events

    # 生成最近 N 天的日期
    today = datetime.now()
    date_range = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

    for filepath in dir_path.glob("*.jsonl.gz"):
        # 检查文件名中的日期是否在范围内
        filename = filepath.stem.replace(".jsonl", "")
        file_date = filename.split("_")[-1]  # 假设格式: SYMBOL_YYYY-MM-DD

        if file_date not in date_range:
            continue

        try:
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            print(f"读取失败: {filepath} - {e}")

    return events


def load_runs(runs_dir: str = "./storage/runs") -> List[Dict]:
    """加载运行元信息"""
    runs = []
    dir_path = Path(runs_dir)

    if not dir_path.exists():
        return runs

    for filepath in sorted(dir_path.glob("*.json"), reverse=True):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                runs.append(json.load(f))
        except:
            pass

    return runs


def summarize_iceberg_signals(events: List[Dict]) -> Dict[str, Any]:
    """
    汇总冰山信号统计

    Returns:
        Dict: 包含各项统计指标
    """
    stats = {
        'total_icebergs': 0,
        'by_level': defaultdict(int),       # ACTIVITY/CONFIRMED 分布
        'by_symbol': defaultdict(int),      # 按币种分布
        'by_side': defaultdict(int),        # BUY/SELL 分布
        'by_hour': defaultdict(int),        # 按小时分布
        'confirmed_list': [],               # CONFIRMED 信号列表
        'activity_list': [],                # ACTIVITY 信号列表
        'upgrades': 0,                      # 升级次数
        'confirmed_rate': 0.0,              # CONFIRMED 比例
    }

    for event in events:
        if event.get('type') != 'iceberg':
            continue

        stats['total_icebergs'] += 1
        data = event.get('data', {})

        level = data.get('level', 'UNKNOWN')
        symbol = event.get('symbol', 'UNKNOWN')
        side = data.get('side', 'UNKNOWN')
        ts = event.get('ts', 0)

        stats['by_level'][level] += 1
        stats['by_symbol'][symbol] += 1
        stats['by_side'][side] += 1

        # 按小时分布
        if ts:
            hour = datetime.fromtimestamp(ts).strftime('%H')
            stats['by_hour'][hour] += 1

        # 收集信号详情
        signal_info = {
            'time': datetime.fromtimestamp(ts).isoformat() if ts else 'N/A',
            'symbol': symbol,
            'side': side,
            'price': data.get('price', 0),
            'cumulative_volume': data.get('cumulative_volume', 0),
            'confidence': data.get('confidence', 0),
            'refill_count': data.get('refill_count', 0),
        }

        if level == 'CONFIRMED':
            stats['confirmed_list'].append(signal_info)
        elif level == 'ACTIVITY':
            stats['activity_list'].append(signal_info)

    # 计算 CONFIRMED 比例
    if stats['total_icebergs'] > 0:
        stats['confirmed_rate'] = stats['by_level'].get('CONFIRMED', 0) / stats['total_icebergs'] * 100

    return stats


def summarize_throttle_events(events: List[Dict]) -> Dict[str, Any]:
    """汇总节流/静默事件"""
    stats = {
        'throttle_count': 0,
        'silent_count': 0,
        'upgrade_bypass_count': 0,
    }

    # 这里可以从日志或特定事件类型中提取
    # 目前返回占位数据
    return stats


def summarize_health_events(events: List[Dict]) -> Dict[str, Any]:
    """汇总健康状态事件"""
    stats = {
        'stale_count': 0,
        'disconnected_count': 0,
        'recovered_count': 0,
        'healthy_pct': 0.0,
    }

    for event in events:
        if event.get('type') != 'state':
            continue

        # 从状态事件中提取健康信息
        # 需要根据实际数据格式调整

    return stats


def generate_report(days: int = 3) -> str:
    """
    生成 72h 验证报告

    Args:
        days: 统计天数

    Returns:
        str: 报告内容
    """
    events = load_events(days=days)
    runs = load_runs()

    iceberg_stats = summarize_iceberg_signals(events)
    throttle_stats = summarize_throttle_events(events)
    health_stats = summarize_health_events(events)

    # 构建报告
    lines = []
    lines.append("=" * 60)
    lines.append(f"Flow Radar {days * 24}h 验证报告")
    lines.append(f"生成时间: {datetime.now().isoformat()}")
    lines.append("=" * 60)

    # 运行信息
    if runs:
        latest_run = runs[0]
        lines.append("")
        lines.append("【运行信息】")
        lines.append(f"  Run ID: {latest_run.get('run_id', 'N/A')}")
        lines.append(f"  Git Commit: {latest_run.get('git_commit', 'N/A')}")
        lines.append(f"  启动时间: {latest_run.get('start_time_str', 'N/A')}")
        if latest_run.get('end_time_str'):
            lines.append(f"  结束时间: {latest_run.get('end_time_str', 'N/A')}")
            runtime = latest_run.get('total_runtime_seconds', 0)
            lines.append(f"  运行时长: {runtime / 3600:.1f} 小时")

    # 冰山信号统计
    lines.append("")
    lines.append("【冰山信号统计】")
    lines.append(f"  总信号数: {iceberg_stats['total_icebergs']}")
    lines.append(f"  CONFIRMED: {iceberg_stats['by_level'].get('CONFIRMED', 0)}")
    lines.append(f"  ACTIVITY: {iceberg_stats['by_level'].get('ACTIVITY', 0)}")
    lines.append(f"  CONFIRMED 比例: {iceberg_stats['confirmed_rate']:.1f}%")

    # 按币种分布
    lines.append("")
    lines.append("【按币种分布】")
    for symbol, count in sorted(iceberg_stats['by_symbol'].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {symbol}: {count}")

    # 按方向分布
    lines.append("")
    lines.append("【按方向分布】")
    for side, count in iceberg_stats['by_side'].items():
        lines.append(f"  {side}: {count}")

    # 按小时分布
    lines.append("")
    lines.append("【按小时分布 (UTC+8)】")
    hour_line = "  "
    for h in range(24):
        hour_str = f"{h:02d}"
        count = iceberg_stats['by_hour'].get(hour_str, 0)
        hour_line += f"{hour_str}:{count:2d} "
        if (h + 1) % 8 == 0:
            lines.append(hour_line)
            hour_line = "  "

    # Top 10 CONFIRMED 信号
    lines.append("")
    lines.append("【Top 10 CONFIRMED 信号】")
    for i, sig in enumerate(iceberg_stats['confirmed_list'][:10], 1):
        lines.append(f"  {i}. [{sig['time']}] {sig['symbol']} {sig['side']} "
                    f"@{sig['price']:.6f} Vol:{sig['cumulative_volume']:.0f}U "
                    f"Conf:{sig['confidence']:.0f}%")

    # 节流统计
    lines.append("")
    lines.append("【节流/静默统计】")
    lines.append(f"  节流次数: {throttle_stats['throttle_count']}")
    lines.append(f"  静默次数: {throttle_stats['silent_count']}")
    lines.append(f"  升级绕过: {throttle_stats['upgrade_bypass_count']}")

    # 健康状态
    lines.append("")
    lines.append("【健康状态】")
    lines.append(f"  STALE 次数: {health_stats['stale_count']}")
    lines.append(f"  DISCONNECTED 次数: {health_stats['disconnected_count']}")
    lines.append(f"  RECOVERED 次数: {health_stats['recovered_count']}")
    lines.append(f"  HEALTHY 占比: {health_stats['healthy_pct']:.1f}%")

    # 验收检查
    lines.append("")
    lines.append("【验收检查】")
    total_signals = iceberg_stats['total_icebergs']
    confirmed = iceberg_stats['by_level'].get('CONFIRMED', 0)

    checks = [
        ("信号数量 >= 20", total_signals >= 20, f"{total_signals}"),
        ("CONFIRMED >= 5", confirmed >= 5, f"{confirmed}"),
        ("CONFIRMED 比例 > 10%", iceberg_stats['confirmed_rate'] > 10, f"{iceberg_stats['confirmed_rate']:.1f}%"),
    ]

    for name, passed, value in checks:
        status = "✓" if passed else "✗"
        lines.append(f"  {status} {name}: {value}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='72h 验证汇总脚本')
    parser.add_argument('--days', '-d', type=int, default=3, help='统计天数 (默认: 3)')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径')
    args = parser.parse_args()

    report = generate_report(days=args.days)
    print(report)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {args.output}")


if __name__ == "__main__":
    main()
