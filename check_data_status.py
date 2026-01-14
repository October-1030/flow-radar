# -*- coding: utf-8 -*-
"""
Flow Radar 数据状态检查脚本
"""
import sys
import os
import re
import json
from pathlib import Path
from collections import defaultdict

# 确保输出编码正确
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

def main():
    try:
        print(f"Python 版本: {sys.version}")
        print(f"工作目录: {os.getcwd()}")
        print()

        print("=== 事件文件统计 ===\n")
        events_dir = Path("storage/events")

        if not events_dir.exists():
            print("events 目录不存在")
        else:
            files = sorted(events_dir.glob("*.jsonl.gz"))

            if not files:
                print("没有找到事件文件")
            else:
                # 按交易对分组
                symbols = defaultdict(list)
                for f in files:
                    name = f.name
                    if "_2" in name:
                        symbol = name.split("_2")[0].replace("-", "_")
                    else:
                        symbol = name.split(".")[0]
                    symbols[symbol].append(f)

                for symbol, sym_files in sorted(symbols.items()):
                    total_size = sum(f.stat().st_size for f in sym_files) / 1024 / 1024
                    dates = []
                    for f in sym_files:
                        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
                        if m:
                            dates.append(m.group(1))

                    if dates:
                        dates = sorted(set(dates))
                        print(f"{symbol}:")
                        print(f"  文件数: {len(sym_files)}")
                        print(f"  总大小: {total_size:.1f} MB")
                        print(f"  日期范围: {dates[0]} ~ {dates[-1]}")
                        print(f"  天数: {len(dates)} 天")
                        print()

        print("\n=== 信号文件统计 ===\n")
        signals_dir = Path("storage/signals")

        if not signals_dir.exists():
            print("signals 目录不存在")
        else:
            files = sorted(signals_dir.glob("*.jsonl"))

            if not files:
                print("没有找到信号文件")
            else:
                total_kgod = 0
                total_iceberg = 0

                for f in files:
                    size_kb = f.stat().st_size / 1024
                    print(f"{f.name}: {size_kb:.1f} KB")

                    try:
                        with open(f, "r", encoding="utf-8") as fp:
                            for line in fp:
                                try:
                                    d = json.loads(line)
                                    st = d.get("signal_type", "")
                                    if st.startswith("k_god"):
                                        total_kgod += 1
                                    elif st == "iceberg_detected":
                                        total_iceberg += 1
                                except:
                                    pass
                    except Exception as e:
                        print(f"  读取错误: {e}")

                print(f"\n总计:")
                print(f"  K神信号: {total_kgod}")
                print(f"  冰山信号: {total_iceberg}")

        print("\n\n=== 状态文件 ===\n")
        state_dir = Path("storage/state")

        if not state_dir.exists():
            print("state 目录不存在")
        else:
            for f in sorted(state_dir.glob("*.json")):
                if "backup" in f.name:
                    continue

                size_kb = f.stat().st_size / 1024
                print(f"{f.name}: {size_kb:.1f} KB")

                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)

                    symbol = data.get("symbol", "unknown")
                    icebergs = len(data.get("active_icebergs", []))
                    price = data.get("last_price", 0)
                    state = data.get("current_state", "unknown")

                    print(f"  交易对: {symbol}")
                    print(f"  当前价格: {price}")
                    print(f"  市场状态: {state}")
                    print(f"  活跃冰山: {icebergs}")
                    print()
                except Exception as e:
                    print(f"  读取错误: {e}")

        print("\n检查完成!")

    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n致命错误: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")  # 防止窗口立即关闭
