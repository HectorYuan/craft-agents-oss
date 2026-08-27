"""
ZenTest 测试分类定义

定义了 6 大测试类别，涵盖单元/集成/E2E/技能生态/平台适配器/安全审计。
"""

from enum import Enum, auto


class TestCategory(Enum):
    """ZenTest 测试分类"""

    UNIT = "unit"
    """纯函数/数据模型测试 — to_dict/from_dict/序列化/反序列化"""

    INTEGRATION = "integration"
    """多模块联动测试 — Memory→Manifest→LevelUp 等跨模块流程"""

    E2E = "e2e"
    """完整用户场景测试 — CLI→交互→持久化→重启→验证"""

    SKILL = "skill"
    """技能生态测试 — 包格式/安装卸载/兼容性/沙箱隔离"""

    PLATFORM = "platform"
    """平台适配器测试 — 接口契约/多平台隔离/异常传播"""

    SECURITY = "security"
    """安全审计测试 — 注入攻击/数据泄漏/依赖 CVE"""

    @classmethod
    def from_str(cls, value: str) -> "TestCategory":
        """从字符串解析分类，大小写不敏感"""
        normalized = value.strip().lower()
        for cat in cls:
            if cat.value == normalized:
                return cat
        raise ValueError(
            f"未知测试分类: '{value}'. 可选: {', '.join(c.value for c in cls)}"
        )

    @classmethod
    def all_values(cls) -> list[str]:
        """返回所有分类值列表"""
        return [c.value for c in cls]


class TestSeverity(Enum):
    """测试严重级别 — 用于 CI 门禁决策"""

    CRITICAL = auto()
    """失败阻断发布"""
    HIGH = auto()
    """失败需要人工审查"""
    MEDIUM = auto()
    """记录但不阻断"""
    LOW = auto()
    """信息性"""


# 每个分类的默认严重级别
CATEGORY_SEVERITY: dict[TestCategory, TestSeverity] = {
    TestCategory.UNIT: TestSeverity.CRITICAL,
    TestCategory.INTEGRATION: TestSeverity.CRITICAL,
    TestCategory.E2E: TestSeverity.HIGH,
    TestCategory.SKILL: TestSeverity.MEDIUM,
    TestCategory.PLATFORM: TestSeverity.MEDIUM,
    TestCategory.SECURITY: TestSeverity.HIGH,
}
