#!/usr/bin/env python3
"""
Phase 2 Discord Bundle 告警演示
展示如何发送 Bundle 综合告警到 Discord
"""

import asyncio
import time
from datetime import datetime
from rich.console import Console

console = Console()


async def demo_bundle_alert_to_discord():
    """演示 Phase 2 Bundle 告警发送到 Discord"""

    console.print("="*70)
    console.print("[bold cyan]Phase 2 Discord Bundle 告警演示[/bold cyan]")
    console.print("="*70)
    console.print()

    # 1. 检查配置
    console.print("[bold]步骤 1: 检查 Discord 配置[/bold]")
    try:
        from config.settings import CONFIG_DISCORD, CONFIG_FEATURES

        if not CONFIG_FEATURES.get('use_p3_phase2'):
            console.print("[red]❌ Phase 2 未启用（use_p3_phase2 = False）[/red]")
            return

        if not CONFIG_DISCORD.get('enabled'):
            console.print("[yellow]⚠️  Discord 未启用[/yellow]")
            console.print("请修改 config/settings.py:")
            console.print('  CONFIG_DISCORD["enabled"] = True')
            return

        webhook_url = CONFIG_DISCORD.get('webhook_url', '')
        if not webhook_url:
            console.print("[red]❌ Discord Webhook URL 未配置[/red]")
            console.print("请参考 DISCORD_WEBHOOK_SETUP_GUIDE.md 配置 Webhook")
            return

        console.print(f"✓ Phase 2 已启用")
        console.print(f"✓ Discord 已启用")
        console.print(f"✓ Webhook URL 已配置: {webhook_url[:50]}...")
        console.print()

    except ImportError as e:
        console.print(f"[red]❌ 导入失败: {e}[/red]")
        return

    # 2. 创建演示信号
    console.print("[bold]步骤 2: 创建演示信号[/bold]")

    base_ts = time.time()
    test_signals = [
        {
            'type': 'liq',
            'symbol': 'DOGE_USDT',
            'ts': base_ts,
            'side': 'BUY',
            'level': 'CRITICAL',
            'price': 0.15000,
            'confidence': 92.0,
            'liquidation_type': 'market',
            'liquidation_amount': 50000.0,
        },
        {
            'type': 'whale',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 10,
            'side': 'BUY',
            'level': 'CONFIRMED',
            'price': 0.15010,
            'confidence': 88.0,
            'amount_usd': 45000.0,
            'trade_count': 1,
        },
        {
            'type': 'iceberg',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 20,
            'side': 'BUY',
            'level': 'CONFIRMED',
            'price': 0.15020,
            'confidence': 85.0,
            'intensity': 3.41,
            'refill_count': 3,
            'cumulative_filled': 15000.0,
            'visible_depth': 500.0,
        },
        {
            'type': 'iceberg',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 30,
            'side': 'SELL',
            'level': 'WARNING',
            'price': 0.15030,
            'confidence': 70.0,
            'intensity': 1.85,
            'refill_count': 2,
            'cumulative_filled': 8000.0,
            'visible_depth': 400.0,
        },
    ]

    console.print(f"✓ 创建了 {len(test_signals)} 个演示信号:")
    for sig in test_signals:
        emoji = "🟢" if sig['side'] == 'BUY' else "🔴"
        type_emoji = {"liq": "💥", "whale": "🐋", "iceberg": "🧊"}[sig['type']]
        console.print(f"  {emoji} {type_emoji} {sig['level']} {sig['type']} {sig['side']} @{sig['price']}")
    console.print()

    # 3. Phase 2 处理
    console.print("[bold]步骤 3: Phase 2 综合处理[/bold]")

    from core.unified_signal_manager import UnifiedSignalManager
    from core.bundle_advisor import BundleAdvisor

    manager = UnifiedSignalManager()

    # 收集信号
    signals = manager.collect_signals(
        icebergs=[s for s in test_signals if s['type'] == 'iceberg'],
        whales=[s for s in test_signals if s['type'] == 'whale'],
        liquidations=[s for s in test_signals if s['type'] == 'liq'],
    )
    console.print(f"✓ 收集到 {len(signals)} 个 SignalEvent")

    # Phase 2 处理
    start_time = time.time()
    result = manager.process_signals_v2(signals)
    processing_time = (time.time() - start_time) * 1000

    processed_signals = result['signals']
    advice = result['advice']

    console.print(f"✓ Phase 2 处理完成 (耗时: {processing_time:.2f}ms)")
    console.print(f"  - 处理后信号: {len(processed_signals)} 个")
    console.print(f"  - 综合建议: {advice['advice']}")
    console.print(f"  - 置信度: {advice['confidence']*100:.1f}%")
    console.print()

    # 4. 生成 Bundle 告警消息预览
    console.print("[bold]步骤 4: Bundle 告警消息预览[/bold]")

    advisor = BundleAdvisor()
    formatted_alert = advisor.format_bundle_alert(advice, processed_signals)

    console.print("─" * 70)
    console.print(formatted_alert)
    console.print("─" * 70)
    console.print()

    # 5. 发送到 Discord
    console.print("[bold]步骤 5: 发送到 Discord[/bold]")

    from core.discord_notifier import DiscordNotifier

    notifier = DiscordNotifier(CONFIG_DISCORD)
    await notifier.initialize()

    console.print("[cyan]正在发送 Bundle 告警...[/cyan]")

    try:
        success = await notifier.send_bundle_alert(
            symbol="DOGE/USDT",
            signals=processed_signals,
            advice=advice,
            market_state={
                'current_price': 0.15020,
                'cvd_total': 10000.0,
                'whale_flow': 5000.0,
            }
        )

        if success:
            console.print("[green]✅ Bundle 告警发送成功！[/green]")
            console.print()
            console.print("[bold]请检查你的 Discord 频道，应该能看到：[/bold]")
            console.print("  • 🔔 综合信号告警标题")
            console.print("  • 🚀 STRONG_BUY 建议（绿色）")
            console.print("  • 📈 BUY 信号统计（4 个）")
            console.print("  • 📉 SELL 信号统计（1 个）")
            console.print("  • 💡 判断理由说明")
            console.print("  • 📊 详细信号明细（含置信度调整）")
            console.print("  • ⏰ 时间戳")
        else:
            console.print("[red]❌ Bundle 告警发送失败[/red]")

            status = notifier.status
            if status.get('last_error'):
                console.print(f"错误信息: {status['last_error']}")

    except Exception as e:
        console.print(f"[red]❌ 发送出错: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        await notifier.close()

    console.print()
    console.print("="*70)
    console.print("[bold green]✅ Phase 2 Discord 演示完成！[/bold green]")
    console.print("="*70)


if __name__ == "__main__":
    try:
        asyncio.run(demo_bundle_alert_to_discord())
    except KeyboardInterrupt:
        console.print("\n[yellow]演示被用户中断[/yellow]")
    except Exception as e:
        console.print(f"\n[red]演示出错: {e}[/red]")
        import traceback
        traceback.print_exc()
