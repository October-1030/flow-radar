#!/usr/bin/env python3
"""
Flow Radar - Run Metadata Recorder
流动性雷达 - 运行元信息记录

P3: 启动时记录运行元信息，用于验证追溯
"""

import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class RunMetadata:
    """运行元信息"""
    run_id: str                          # 唯一运行 ID
    start_time: float                    # 启动时间戳
    start_time_str: str                  # 启动时间 (可读)
    git_commit: str                      # Git commit SHA
    git_branch: str                      # Git 分支
    git_dirty: bool                      # 是否有未提交的修改
    symbols: List[str]                   # 监控的币种列表
    config_snapshot: Dict[str, Any]      # 配置快照
    python_version: str                  # Python 版本
    platform: str                        # 操作系统平台
    hostname: str                        # 主机名
    # 运行时统计 (结束时更新)
    end_time: Optional[float] = None
    end_time_str: Optional[str] = None
    total_runtime_seconds: Optional[float] = None
    total_signals: int = 0
    confirmed_signals: int = 0
    activity_signals: int = 0
    reconnect_count: int = 0
    throttle_count: int = 0
    silent_count: int = 0


class RunMetadataRecorder:
    """
    运行元信息记录器

    功能:
    - 启动时生成 run_id 并记录元信息
    - 保存到 storage/runs/{run_id}.json
    - 支持运行时更新统计
    """

    def __init__(self, symbols: List[str], output_dir: str = "./storage/runs"):
        self.symbols = symbols
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 生成 run_id
        self.run_id = self._generate_run_id()
        self.filepath = self.output_dir / f"{self.run_id}.json"

        # 创建元信息
        self.metadata = self._create_metadata()

    def _generate_run_id(self) -> str:
        """生成运行 ID: YYYYMMDD_HHMMSS_uuid4前8位"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"{ts}_{uid}"

    def _get_git_info(self) -> Dict[str, Any]:
        """获取 Git 信息"""
        info = {
            'commit': 'unknown',
            'branch': 'unknown',
            'dirty': False
        }

        try:
            # 获取 commit SHA
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info['commit'] = result.stdout.strip()[:12]

            # 获取分支名
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info['branch'] = result.stdout.strip()

            # 检查是否有未提交的修改
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info['dirty'] = len(result.stdout.strip()) > 0

        except Exception:
            pass

        return info

    def _get_config_snapshot(self) -> Dict[str, Any]:
        """获取配置快照"""
        try:
            from config.settings import (
                CONFIG_MARKET, CONFIG_ICEBERG, CONFIG_WEBSOCKET,
                CONFIG_DISCORD, CONFIG_ALERT_THROTTLE, CONFIG_HEALTH_CHECK,
                CONFIG_FEATURES
            )
            return {
                'market': CONFIG_MARKET,
                'iceberg': CONFIG_ICEBERG,
                'websocket': {k: v for k, v in CONFIG_WEBSOCKET.items() if k != 'ws_url'},
                'discord': {k: v for k, v in CONFIG_DISCORD.items() if k != 'webhook_url'},
                'alert_throttle': CONFIG_ALERT_THROTTLE,
                'health_check': CONFIG_HEALTH_CHECK,
                'features': CONFIG_FEATURES,
            }
        except ImportError:
            return {}

    def _create_metadata(self) -> RunMetadata:
        """创建运行元信息"""
        import platform
        import socket
        import sys

        git_info = self._get_git_info()
        now = time.time()

        return RunMetadata(
            run_id=self.run_id,
            start_time=now,
            start_time_str=datetime.fromtimestamp(now).isoformat(),
            git_commit=git_info['commit'],
            git_branch=git_info['branch'],
            git_dirty=git_info['dirty'],
            symbols=self.symbols,
            config_snapshot=self._get_config_snapshot(),
            python_version=sys.version.split()[0],
            platform=platform.system(),
            hostname=socket.gethostname(),
        )

    def save(self) -> bool:
        """保存元信息到文件"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.metadata), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[RunMetadata] 保存失败: {e}")
            return False

    def update_stats(self, **kwargs):
        """更新运行时统计"""
        for key, value in kwargs.items():
            if hasattr(self.metadata, key):
                setattr(self.metadata, key, value)
        self.save()

    def finalize(self, metrics: Dict[str, Any] = None):
        """
        结束运行，更新最终统计

        Args:
            metrics: 来自 MetricsCollector 的统计数据
        """
        now = time.time()
        self.metadata.end_time = now
        self.metadata.end_time_str = datetime.fromtimestamp(now).isoformat()
        self.metadata.total_runtime_seconds = now - self.metadata.start_time

        if metrics:
            self.metadata.total_signals = metrics.get('total_signals', 0)
            self.metadata.confirmed_signals = metrics.get('confirmed_count', 0)
            self.metadata.activity_signals = metrics.get('activity_count', 0)
            self.metadata.reconnect_count = metrics.get('reconnect_count', 0)
            self.metadata.throttle_count = metrics.get('throttle_count', 0)
            self.metadata.silent_count = metrics.get('silent_count', 0)

        self.save()

    def get_run_id(self) -> str:
        """获取运行 ID"""
        return self.run_id

    def get_filepath(self) -> Path:
        """获取元信息文件路径"""
        return self.filepath


def list_runs(output_dir: str = "./storage/runs") -> List[Dict]:
    """列出所有运行记录"""
    runs = []
    dir_path = Path(output_dir)

    if not dir_path.exists():
        return runs

    for filepath in sorted(dir_path.glob("*.json"), reverse=True):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                runs.append(data)
        except:
            pass

    return runs


def get_latest_run(output_dir: str = "./storage/runs") -> Optional[Dict]:
    """获取最新的运行记录"""
    runs = list_runs(output_dir)
    return runs[0] if runs else None


# 测试
if __name__ == "__main__":
    recorder = RunMetadataRecorder(symbols=["DOGE/USDT", "BTC/USDT"])
    print(f"Run ID: {recorder.run_id}")
    print(f"Git: {recorder.metadata.git_commit} ({recorder.metadata.git_branch})")
    print(f"Dirty: {recorder.metadata.git_dirty}")
    recorder.save()
    print(f"Saved to: {recorder.filepath}")
