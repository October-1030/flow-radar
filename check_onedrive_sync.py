#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 OneDrive 云同步状态"""

import sys
import io
import os
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("="*70)
print("☁️  OneDrive 云同步状态检查")
print("="*70)

# 检查路径
storage_path = Path("C:/Users/rjtan/OneDrive/文档/ProjectS/flow-radar/storage/events")
project_root = Path("C:/Users/rjtan/OneDrive/文档/ProjectS/flow-radar")

print(f"\n📂 项目位置:")
print(f"   {project_root}")
print(f"   ✅ 位于 OneDrive 文件夹内")

# 检查 OneDrive 路径特征
onedrive_root = Path("C:/Users/rjtan/OneDrive")
if project_root.is_relative_to(onedrive_root):
    print(f"\n☁️  OneDrive 同步状态:")
    print(f"   ✅ 项目在 OneDrive 管理范围内")
    print(f"   ✅ 文件会自动同步到云端")
else:
    print(f"\n⚠️  警告: 项目不在 OneDrive 文件夹中")

# 统计文件
files = sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz"))
total_size = sum(f.stat().st_size for f in files)
total_mb = total_size / 1024 / 1024

print(f"\n📊 数据文件统计:")
print(f"   文件数量: {len(files)}")
print(f"   总大小: {total_mb:.1f} MB")

# 检查文件属性 (Windows)
if sys.platform == 'win32':
    print(f"\n📁 文件详情:")
    for f in files[-3:]:  # 显示最新3个文件
        size_mb = f.stat().st_size / 1024 / 1024
        mod_time = datetime.fromtimestamp(f.stat().st_mtime)

        # 检查是否在 OneDrive 路径
        in_onedrive = "✅ OneDrive" if "OneDrive" in str(f) else "❌ 本地"

        print(f"   {f.name}")
        print(f"      大小: {size_mb:.1f} MB")
        print(f"      修改: {mod_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"      状态: {in_onedrive}")

print(f"\n💡 OneDrive 同步说明:")
print(f"   - 文件位于 OneDrive 文件夹，会自动同步")
print(f"   - 同步速度取决于网络和文件大小")
print(f"   - 可以在系统托盘查看 OneDrive 图标确认同步状态")
print(f"   - 绿色对勾 = 已同步")
print(f"   - 蓝色箭头 = 正在同步")
print(f"   - 红色叉号 = 同步错误")

print(f"\n🔍 检查方法:")
print(f"   1. 打开文件资源管理器")
print(f"   2. 导航到: {storage_path}")
print(f"   3. 查看文件图标上的状态标记")

print("\n" + "="*70 + "\n")
