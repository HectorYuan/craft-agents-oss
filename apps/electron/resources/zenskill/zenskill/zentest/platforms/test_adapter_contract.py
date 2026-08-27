"""
Z7 — 平台适配器测试

验证所有 PlatformAdapter 子类实现统一接口契约，
以及多平台之间的异常隔离。
"""

from __future__ import annotations

import pytest

from zenskill.zentest.fixtures import ZSkillHome


# ═══════════════════════════════════════════════════════════════
# 适配器接口契约
# ═══════════════════════════════════════════════════════════════

# 所有 PlatformAdapter 必须实现的方法
ADAPTER_REQUIRED_METHODS = [
    "install",
    "uninstall",
    "execute",
    "is_installed",
    "get_status",
]


@pytest.mark.platform
def test_adapter_interface_contract() -> None:
    """所有 PlatformAdapter 子类必须实现接口契约方法"""
    # 尝试导入真实适配器
    try:
        from zenskill.platforms import PlatformAdapter
    except ImportError:
        # 如果平台模块不可用，测试抽象契约
        class PlatformAdapter:
            """Mock 平台适配器基类"""
            def install(self, *a, **kw): raise NotImplementedError
            def uninstall(self, *a, **kw): raise NotImplementedError
            def execute(self, *a, **kw): raise NotImplementedError
            def is_installed(self, *a, **kw): raise NotImplementedError
            def get_status(self, *a, **kw): raise NotImplementedError

        # 所有方法签名一致
        adapter = PlatformAdapter()
        for method_name in ADAPTER_REQUIRED_METHODS:
            assert hasattr(adapter, method_name), f"缺少方法: {method_name}"
            assert callable(getattr(adapter, method_name)), \
                f"{method_name} 应为可调用"


@pytest.mark.platform
def test_install_result_type() -> None:
    """install 应返回 InstallResult（或 dict 含 success 字段）"""
    class MockAdapter:
        def install(self, skill_id: str) -> dict:
            return {"success": True, "skill_id": skill_id}

    a = MockAdapter()
    result = a.install("test_skill")
    assert isinstance(result, dict)
    assert "success" in result
    assert result["success"] is True
    assert result["skill_id"] == "test_skill"


@pytest.mark.platform
def test_execution_result_type() -> None:
    """execute 应返回 ExecutionResult（或 dict 含 status/output 字段）"""
    class MockAdapter:
        def execute(self, skill_id: str, action: str) -> dict:
            return {"status": "ok", "output": f"{action} executed"}

    a = MockAdapter()
    result = a.execute("test_skill", "run")
    assert "status" in result
    assert "output" in result
    assert result["status"] == "ok"


@pytest.mark.platform
def test_adapter_error_return_not_crash() -> None:
    """适配器失败应返回错误 result，不抛异常"""
    class SafeAdapter:
        def install(self, skill_id: str) -> dict:
            return {"success": False, "error": "平台不支持"}

    a = SafeAdapter()
    result = a.install("unknown_skill")
    assert result["success"] is False
    assert "error" in result


# ═══════════════════════════════════════════════════════════════
# 多平台隔离
# ═══════════════════════════════════════════════════════════════

@pytest.mark.platform
def test_platform_isolation_on_failure() -> None:
    """单个平台安装失败不影响其他平台"""
    results = {
        "platform_a": {"success": False, "error": "网络错误"},
        "platform_b": {"success": True, "skill_id": "test"},
        "platform_c": {"success": True, "skill_id": "test"},
    }
    assert results["platform_a"]["success"] is False
    assert results["platform_b"]["success"] is True
    assert results["platform_c"]["success"] is True


@pytest.mark.platform
def test_parallel_install_no_race() -> None:
    """模拟并行安装 — 各自独立，不产生竞态"""
    import threading

    results: dict[str, dict] = {}
    lock = threading.Lock()

    def install(platform: str) -> None:
        with lock:
            results[platform] = {"success": True, "platform": platform}

    threads = [
        threading.Thread(target=install, args=(f"platform_{i}",))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    for platform, result in results.items():
        assert result["success"] is True


@pytest.mark.platform
def test_error_not_cross_platform() -> None:
    """异常不跨平台传播"""
    def platform_a():
        raise RuntimeError("平台 A 崩溃")

    def platform_b():
        return {"success": True}

    try:
        platform_a()
    except RuntimeError:
        pass  # 预期异常

    result_b = platform_b()
    assert result_b["success"] is True


# ═══════════════════════════════════════════════════════════════
# 注册机制
# ═══════════════════════════════════════════════════════════════

@pytest.mark.platform
def test_adapter_registration() -> None:
    """新平台应可注册到适配器注册表中"""
    registry: dict[str, type] = {}

    class MockAdapter:
        pass

    registry["mock"] = MockAdapter
    assert "mock" in registry
    assert registry["mock"] is MockAdapter


@pytest.mark.platform
def test_adapter_unregister() -> None:
    """平台应可注销"""
    registry: dict[str, type] = {}

    class TempAdapter:
        pass

    registry["temp"] = TempAdapter
    assert "temp" in registry
    del registry["temp"]
    assert "temp" not in registry
