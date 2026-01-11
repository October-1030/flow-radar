#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

start = datetime(2025, 12, 29, 16, 40, 13)
now = datetime.now()
elapsed = (now - start).total_seconds() / 3600
remaining = 72 - elapsed

print(f"开始时间: {start.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"已运行: {elapsed:.1f} 小时 ({elapsed/24:.1f} 天)")
print(f"剩余时间: {remaining:.1f} 小时 ({remaining/24:.1f} 天)")
print(f"预计完成: {start.replace(hour=start.hour, minute=start.minute) if remaining < 0 else datetime.fromtimestamp(now.timestamp() + remaining*3600).strftime('%Y-%m-%d %H:%M:%S')}")
