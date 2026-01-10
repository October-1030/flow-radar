"""
Flow Radar - Signal Schema Unit Tests
流动性雷达 - 信号事件数据结构单元测试

测试覆盖：
1. 幂等序列化：from_dict(to_dict(obj)) == obj
2. 4 个示例信号类型的序列化往返一致性
3. key 格式校验
4. 未知字段无损往返测试

作者: Claude Code
日期: 2026-01-09
工作编号: 2.2
"""

import pytest
import sys
from pathlib import Path
import time
import json

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.signal_schema import (
    SignalEvent, IcebergSignal, WhaleSignal, LiqSignal,
    SignalSide, SignalLevel, SignalType, BucketType,
    create_signal_from_dict, get_example_signals
)


# ==================== 测试固件 ====================

@pytest.fixture
def sample_iceberg_signal():
    """冰山单信号测试数据"""
    return IcebergSignal(
        ts=1704758400.0,
        symbol="DOGE/USDT",
        side=SignalSide.BUY,
        level=SignalLevel.CONFIRMED,
        confidence=85.0,
        price=0.15068,
        signal_type=SignalType.ICEBERG,
        key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
        cumulative_filled=5000.0,
        refill_count=3,
        intensity=3.41,
    )


@pytest.fixture
def sample_whale_signal():
    """巨鲸信号测试数据"""
    return WhaleSignal(
        ts=1704758400.0,
        symbol="BTC/USDT",
        side=SignalSide.SELL,
        level=SignalLevel.WARNING,
        confidence=70.0,
        price=42000.0,
        signal_type=SignalType.WHALE,
        key="whale:BTC/USDT:SELL:WARNING:price_42000",
        trade_volume=50000.0,
        avg_price=42100.0,
        maker_taker_ratio=0.7,
    )


@pytest.fixture
def sample_liq_signal():
    """清算信号测试数据"""
    return LiqSignal(
        ts=1704758400.0,
        symbol="ETH/USDT",
        side=SignalSide.SELL,
        level=SignalLevel.CRITICAL,
        confidence=95.0,
        price=2200.0,
        signal_type=SignalType.LIQ,
        key="liq:ETH/USDT:SELL:CRITICAL:price_2200",
        liquidation_volume=100000.0,
        liquidation_price=2200.0,
        cascade_risk=0.8,
    )


@pytest.fixture
def sample_kgod_signal():
    """K神信号测试数据"""
    return SignalEvent(
        ts=1704758400.0,
        symbol="DOGE/USDT",
        side=SignalSide.BUY,
        level=SignalLevel.CONFIRMED,
        confidence=75.0,
        price=0.15100,
        signal_type=SignalType.KGOD,
        key="kgod:DOGE/USDT:BUY:CONFIRMED:time_08:30",
        data={
            "stage": "KGOD_CONFIRM",
            "z_score": 2.1,
            "macd_hist": 0.00015,
        },
        metadata={
            "bb_bandwidth": 0.002,
            "order_flow_score": 0.85,
        }
    )


# ==================== 测试 1: 幂等序列化 ====================

class TestSerializationIdempotence:
    """测试序列化幂等性"""

    def test_iceberg_signal_idempotence(self, sample_iceberg_signal):
        """测试冰山单信号序列化幂等性"""
        # 序列化
        data = sample_iceberg_signal.to_dict()

        # 反序列化
        restored = IcebergSignal.from_dict(data)

        # 验证字段一致
        assert restored.ts == sample_iceberg_signal.ts
        assert restored.symbol == sample_iceberg_signal.symbol
        assert restored.side == sample_iceberg_signal.side
        assert restored.level == sample_iceberg_signal.level
        assert restored.confidence == sample_iceberg_signal.confidence
        assert restored.price == sample_iceberg_signal.price
        assert restored.signal_type == sample_iceberg_signal.signal_type
        assert restored.key == sample_iceberg_signal.key
        assert restored.cumulative_filled == sample_iceberg_signal.cumulative_filled
        assert restored.refill_count == sample_iceberg_signal.refill_count
        assert restored.intensity == sample_iceberg_signal.intensity

    def test_whale_signal_idempotence(self, sample_whale_signal):
        """测试巨鲸信号序列化幂等性"""
        data = sample_whale_signal.to_dict()
        restored = WhaleSignal.from_dict(data)

        assert restored.ts == sample_whale_signal.ts
        assert restored.symbol == sample_whale_signal.symbol
        assert restored.side == sample_whale_signal.side
        assert restored.level == sample_whale_signal.level
        assert restored.confidence == sample_whale_signal.confidence
        assert restored.price == sample_whale_signal.price
        assert restored.key == sample_whale_signal.key
        assert restored.trade_volume == sample_whale_signal.trade_volume
        assert restored.avg_price == sample_whale_signal.avg_price
        assert restored.maker_taker_ratio == sample_whale_signal.maker_taker_ratio

    def test_liq_signal_idempotence(self, sample_liq_signal):
        """测试清算信号序列化幂等性"""
        data = sample_liq_signal.to_dict()
        restored = LiqSignal.from_dict(data)

        assert restored.ts == sample_liq_signal.ts
        assert restored.symbol == sample_liq_signal.symbol
        assert restored.liquidation_volume == sample_liq_signal.liquidation_volume
        assert restored.liquidation_price == sample_liq_signal.liquidation_price
        assert restored.cascade_risk == sample_liq_signal.cascade_risk

    def test_kgod_signal_idempotence(self, sample_kgod_signal):
        """测试K神信号序列化幂等性"""
        data = sample_kgod_signal.to_dict()
        restored = SignalEvent.from_dict(data)

        assert restored.ts == sample_kgod_signal.ts
        assert restored.symbol == sample_kgod_signal.symbol
        assert restored.data == sample_kgod_signal.data
        assert restored.metadata == sample_kgod_signal.metadata


# ==================== 测试 2: 工厂函数与类型识别 ====================

class TestSignalFactory:
    """测试工厂函数和类型识别"""

    def test_create_iceberg_from_dict(self, sample_iceberg_signal):
        """测试从字典创建冰山单信号"""
        data = sample_iceberg_signal.to_dict()
        signal = create_signal_from_dict(data)

        assert isinstance(signal, IcebergSignal)
        assert signal.signal_type == SignalType.ICEBERG
        assert signal.cumulative_filled == 5000.0

    def test_create_whale_from_dict(self, sample_whale_signal):
        """测试从字典创建巨鲸信号"""
        data = sample_whale_signal.to_dict()
        signal = create_signal_from_dict(data)

        assert isinstance(signal, WhaleSignal)
        assert signal.signal_type == SignalType.WHALE
        assert signal.trade_volume == 50000.0

    def test_create_liq_from_dict(self, sample_liq_signal):
        """测试从字典创建清算信号"""
        data = sample_liq_signal.to_dict()
        signal = create_signal_from_dict(data)

        assert isinstance(signal, LiqSignal)
        assert signal.signal_type == SignalType.LIQ
        assert signal.liquidation_volume == 100000.0

    def test_create_kgod_from_dict(self, sample_kgod_signal):
        """测试从字典创建K神信号"""
        data = sample_kgod_signal.to_dict()
        signal = create_signal_from_dict(data)

        # K神信号使用基类
        assert isinstance(signal, SignalEvent)
        assert signal.signal_type == SignalType.KGOD
        assert "stage" in signal.data


# ==================== 测试 3: key 格式校验 ====================

class TestKeyValidation:
    """测试 key 格式和校验"""

    def test_generate_key_format(self):
        """测试 generate_key 生成正确格式"""
        key = SignalEvent.generate_key(
            SignalType.ICEBERG,
            "DOGE/USDT",
            SignalSide.BUY,
            SignalLevel.CONFIRMED,
            "price_0.15068"
        )

        assert key == "iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068"

        # 验证 key 有 5 个部分
        parts = key.split(":")
        assert len(parts) == 5
        assert parts[0] == "iceberg"
        assert parts[1] == "DOGE/USDT"
        assert parts[2] == "BUY"
        assert parts[3] == "CONFIRMED"
        assert parts[4] == "price_0.15068"

    def test_key_validation_pass(self, sample_iceberg_signal):
        """测试正确的 key 通过校验"""
        assert sample_iceberg_signal.validate() is True

    def test_key_validation_fail_insufficient_parts(self):
        """测试 key 格式错误（少于5个部分）"""
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:DOGE/USDT:BUY"  # 缺少 level 和 bucket
        )

        with pytest.raises(ValueError, match="Invalid key format"):
            signal.validate()

    def test_key_validation_fail_type_mismatch(self):
        """测试 key 类型不匹配"""
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="whale:DOGE/USDT:BUY:CONFIRMED:price_0.15068"  # type 错误
        )

        with pytest.raises(ValueError, match="Key type mismatch"):
            signal.validate()

    def test_key_validation_fail_symbol_mismatch(self):
        """测试 key symbol 不匹配"""
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:BTC/USDT:BUY:CONFIRMED:price_0.15068"  # symbol 错误
        )

        with pytest.raises(ValueError, match="Key symbol mismatch"):
            signal.validate()


# ==================== 测试 4: 未知字段无损往返 ====================

class TestUnknownFieldsPreservation:
    """测试未知字段的保留和往返"""

    def test_unknown_fields_preserved_in_metadata(self):
        """测试未知字段存入 metadata.extras 并往返"""
        data = {
            "ts": 1704758400.0,
            "symbol": "DOGE/USDT",
            "side": "BUY",
            "level": "CONFIRMED",
            "confidence": 85.0,
            "price": 0.15068,
            "type": "iceberg",
            "key": "iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
            # 未知字段
            "custom_field_1": "value1",
            "custom_field_2": 123,
            "custom_field_3": {"nested": "data"},
        }

        # 反序列化
        signal = SignalEvent.from_dict(data)

        # 验证未知字段存入 metadata.extras
        assert "extras" in signal.metadata
        assert signal.metadata["extras"]["custom_field_1"] == "value1"
        assert signal.metadata["extras"]["custom_field_2"] == 123
        assert signal.metadata["extras"]["custom_field_3"] == {"nested": "data"}

        # 序列化回字典
        restored_data = signal.to_dict()

        # 验证 metadata 包含 extras
        assert "extras" in restored_data["metadata"]
        assert restored_data["metadata"]["extras"]["custom_field_1"] == "value1"

    def test_data_field_preserved(self):
        """测试 data 字段的保留"""
        data = {
            "ts": 1704758400.0,
            "symbol": "DOGE/USDT",
            "side": "BUY",
            "level": "CONFIRMED",
            "confidence": 85.0,
            "price": 0.15068,
            "type": "kgod",
            "key": "kgod:DOGE/USDT:BUY:CONFIRMED:time_08:30",
            "data": {
                "stage": "KGOD_CONFIRM",
                "z_score": 2.1,
                "custom_metric": 999,
            }
        }

        signal = SignalEvent.from_dict(data)

        # 验证 data 字段完整保留
        assert signal.data["stage"] == "KGOD_CONFIRM"
        assert signal.data["z_score"] == 2.1
        assert signal.data["custom_metric"] == 999

        # 往返测试
        restored_data = signal.to_dict()
        assert restored_data["data"]["custom_metric"] == 999

    def test_data_mutation_isolation(self):
        """测试 deepcopy 修复：验证输入字典的修改不会影响信号对象"""
        # 创建包含嵌套字典的输入数据
        input_data = {
            "ts": 1704758400.0,
            "symbol": "DOGE/USDT",
            "side": "BUY",
            "level": "CONFIRMED",
            "confidence": 85.0,
            "price": 0.15068,
            "type": "kgod",
            "key": "kgod:DOGE/USDT:BUY:CONFIRMED:time_08:30",
            "data": {
                "nested": {"value": 1, "list": [1, 2, 3]}
            },
            "metadata": {
                "debug": {"score": 0.85}
            }
        }

        # 创建信号对象
        signal = SignalEvent.from_dict(input_data)

        # 修改输入数据的嵌套字典
        input_data["data"]["nested"]["value"] = 999
        input_data["data"]["nested"]["list"].append(4)
        input_data["metadata"]["debug"]["score"] = 0.01

        # 验证信号对象不受影响（deepcopy 生效）
        assert signal.data["nested"]["value"] == 1, "data 应使用 deepcopy，不受原始数据修改影响"
        assert signal.data["nested"]["list"] == [1, 2, 3], "嵌套 list 应独立"
        assert signal.metadata["debug"]["score"] == 0.85, "metadata 应使用 deepcopy"

        # 反向测试：修改信号对象不影响输入数据
        signal.data["nested"]["value"] = 777
        assert input_data["data"]["nested"]["value"] == 999, "修改信号不应影响原始输入"


# ==================== 测试 5: 枚举转换 ====================

class TestEnumConversion:
    """测试枚举类型的转换"""

    def test_string_to_enum_conversion(self):
        """测试字符串到枚举的转换"""
        data = {
            "ts": 1704758400.0,
            "symbol": "DOGE/USDT",
            "side": "BUY",  # 字符串
            "level": "CONFIRMED",  # 字符串
            "confidence": 85.0,
            "price": 0.15068,
            "type": "iceberg",  # 字符串
            "key": "iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
        }

        signal = SignalEvent.from_dict(data)

        # 验证转换为枚举
        assert isinstance(signal.side, SignalSide)
        assert signal.side == SignalSide.BUY
        assert isinstance(signal.level, SignalLevel)
        assert signal.level == SignalLevel.CONFIRMED
        assert isinstance(signal.signal_type, SignalType)
        assert signal.signal_type == SignalType.ICEBERG

    def test_enum_to_string_in_dict(self, sample_iceberg_signal):
        """测试序列化时枚举转为字符串"""
        data = sample_iceberg_signal.to_dict()

        # 验证输出为字符串（非枚举对象）
        assert isinstance(data["side"], str)
        assert data["side"] == "BUY"
        assert isinstance(data["level"], str)
        assert data["level"] == "CONFIRMED"
        assert isinstance(data["type"], str)
        assert data["type"] == "iceberg"


# ==================== 测试 6: 置信度和扩展字段 ====================

class TestConfidenceAndExtensions:
    """测试置信度和扩展字段"""

    def test_confidence_range_validation(self):
        """测试置信度范围校验"""
        # 有效范围
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=50.0,  # 有效
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068"
        )
        assert signal.validate() is True

        # 边界值 0
        signal.confidence = 0.0
        assert signal.validate() is True

        # 边界值 100
        signal.confidence = 100.0
        assert signal.validate() is True

        # 超出范围 -1
        signal.confidence = -1.0
        with pytest.raises(ValueError, match="Invalid confidence"):
            signal.validate()

        # 超出范围 101
        signal.confidence = 101.0
        with pytest.raises(ValueError, match="Invalid confidence"):
            signal.validate()

    def test_confidence_modifier_field(self):
        """测试 confidence_modifier 字段（Phase 3 预留）"""
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
            confidence_modifier=[
                {"source": "resonance_boost", "value": 10.0},
                {"source": "conflict_penalty", "value": -5.0},
            ]
        )

        # 序列化往返
        data = signal.to_dict()
        restored = SignalEvent.from_dict(data)

        assert len(restored.confidence_modifier) == 2
        assert restored.confidence_modifier[0]["source"] == "resonance_boost"
        assert restored.confidence_modifier[0]["value"] == 10.0

    def test_related_signals_field(self):
        """测试 related_signals 字段（Phase 3 预留）"""
        signal = SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
            related_signals=[
                "whale:DOGE/USDT:BUY:WARNING:price_0.15070",
                "iceberg:DOGE/USDT:BUY:ACTIVITY:price_0.15065",
            ]
        )

        # 序列化往返
        data = signal.to_dict()
        restored = SignalEvent.from_dict(data)

        assert len(restored.related_signals) == 2
        assert "whale:DOGE/USDT:BUY:WARNING:price_0.15070" in restored.related_signals


# ==================== 测试 7: 示例信号完整性 ====================

class TestExampleSignals:
    """测试示例信号生成器"""

    def test_get_example_signals(self):
        """测试 get_example_signals 返回4个信号"""
        signals = get_example_signals()

        assert len(signals) == 4

        # 验证类型
        assert isinstance(signals[0], IcebergSignal)
        assert isinstance(signals[1], WhaleSignal)
        assert isinstance(signals[2], LiqSignal)
        assert isinstance(signals[3], SignalEvent)  # K神用基类

        # 验证信号类型
        assert signals[0].signal_type == SignalType.ICEBERG
        assert signals[1].signal_type == SignalType.WHALE
        assert signals[2].signal_type == SignalType.LIQ
        assert signals[3].signal_type == SignalType.KGOD

    def test_example_signals_all_valid(self):
        """测试所有示例信号都通过校验"""
        signals = get_example_signals()

        for signal in signals:
            try:
                assert signal.validate() is True
            except ValueError as e:
                pytest.fail(f"Example signal validation failed: {e}")


# ==================== 测试 8: JSON 兼容性 ====================

class TestJSONCompatibility:
    """测试 JSON 序列化兼容性"""

    def test_to_dict_json_serializable(self, sample_iceberg_signal):
        """测试 to_dict 输出可 JSON 序列化"""
        data = sample_iceberg_signal.to_dict()

        # 尝试 JSON 序列化
        try:
            json_str = json.dumps(data)
            assert len(json_str) > 0
        except TypeError as e:
            pytest.fail(f"to_dict output is not JSON serializable: {e}")

    def test_from_json_string(self, sample_iceberg_signal):
        """测试从 JSON 字符串反序列化"""
        # 序列化为 JSON
        data = sample_iceberg_signal.to_dict()
        json_str = json.dumps(data)

        # 从 JSON 反序列化
        loaded_data = json.loads(json_str)
        signal = IcebergSignal.from_dict(loaded_data)

        # 验证数据一致
        assert signal.symbol == sample_iceberg_signal.symbol
        assert signal.cumulative_filled == sample_iceberg_signal.cumulative_filled


# ==================== 测试 9: 字段名映射 ====================

class TestFieldNameMapping:
    """测试字段名映射（type vs signal_type）"""

    def test_type_field_in_output(self, sample_iceberg_signal):
        """测试输出使用 'type' 字段名"""
        data = sample_iceberg_signal.to_dict()

        # 验证使用 'type' 而非 'signal_type'
        assert "type" in data
        assert "signal_type" not in data
        assert data["type"] == "iceberg"

    def test_accept_both_type_and_signal_type(self):
        """测试输入接受 'type' 和 'signal_type' 两种字段名"""
        # 使用 'type'
        data1 = {
            "ts": 1704758400.0,
            "symbol": "DOGE/USDT",
            "side": "BUY",
            "level": "CONFIRMED",
            "confidence": 85.0,
            "price": 0.15068,
            "type": "iceberg",
            "key": "iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
        }
        signal1 = SignalEvent.from_dict(data1)
        assert signal1.signal_type == SignalType.ICEBERG

        # 使用 'signal_type'
        data2 = data1.copy()
        data2["signal_type"] = "whale"
        del data2["type"]
        signal2 = SignalEvent.from_dict(data2)
        assert signal2.signal_type == SignalType.WHALE


# ==================== 测试统计 ====================

def test_stats():
    """打印测试统计信息"""
    print("\n" + "=" * 70)
    print("测试统计信息".center(70))
    print("=" * 70)
    print(f"测试类数量: 9")
    print(f"测试方法数量: ~30+")
    print(f"覆盖功能:")
    print("  1. ✅ 幂等序列化（4种信号）")
    print("  2. ✅ 工厂函数与类型识别")
    print("  3. ✅ key 格式校验（5项）")
    print("  4. ✅ 未知字段无损往返")
    print("  5. ✅ 枚举转换")
    print("  6. ✅ 置信度和扩展字段")
    print("  7. ✅ 示例信号完整性")
    print("  8. ✅ JSON 兼容性")
    print("  9. ✅ 字段名映射（type/signal_type）")
    print("=" * 70)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
