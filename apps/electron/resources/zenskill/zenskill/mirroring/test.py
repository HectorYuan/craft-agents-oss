"""
用户镜像系统集成测试 (Phase 9A + 9B)

运行方式:
    python -m zenskill.mirroring.test
"""

import json
import os
import tempfile
from pathlib import Path

from zenskill.mirroring import (
    EnvironmentIndexer,
    EventCollector,
    FeatureStore,
    PreferenceEngine,
    PrivacyLayer,
    __version__,
)
from zenskill.mirroring.models import EventType


def run_tests():
    """运行所有集成测试"""
    print("=" * 60)
    print(f"🧪 用户镜像系统集成测试 (v{__version__})")
    print("=" * 60)

    # 使用临时目录进行测试
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        results = []

        # ---------------------------------------------------------------------
        # Phase 9A: 用户画像数据层测试
        # ---------------------------------------------------------------------
        print("\n📦 Phase 9A: 用户画像数据层测试")
        print("-" * 60)

        # 1. EventCollector
        print("\n[1/6] 测试 EventCollector...")
        try:
            collector = EventCollector(test_dir)
            # 使用正确的 API: record (EventType 枚举)
            event_id = collector.record(
                EventType.SKILL_EXEC,
                "test-skill",
                "execute test",
                success=True,
                duration_ms=100,
                context={"project": "test"},
            )
            assert event_id is not None, "事件 ID 为空"
            events = collector.query(limit=10)
            assert len(events) > 0, "事件记录失败"
            count = collector.get_event_count()
            assert count > 0, "事件计数失败"
            print("  ✅ EventCollector: 事件记录和查询正常")
            results.append(("EventCollector", True))
        except Exception as e:
            print(f"  ❌ EventCollector: {e}")
            results.append(("EventCollector", False))

        # 2. FeatureStore
        print("\n[2/6] 测试 FeatureStore...")
        try:
            store = FeatureStore(test_dir)
            # compute_features 返回 FeatureVector
            features = store.compute_features()
            assert features is not None, "特征提取失败"
            assert hasattr(features, "total_events"), "特征向量缺少字段"
            summary = store.get_feature_summary()
            assert summary is not None, "特征摘要为空"
            print("  ✅ FeatureStore: 特征提取正常")
            results.append(("FeatureStore", True))
        except Exception as e:
            print(f"  ❌ FeatureStore: {e}")
            results.append(("FeatureStore", False))

        # 3. PrivacyLayer
        print("\n[3/6] 测试 PrivacyLayer...")
        try:
            privacy = PrivacyLayer(test_dir)
            # 使用正确的 API: filter_sensitive_data（凭据值经变量注入，非字面量）
            fake_secret = os.environ.get("ZENSKILL_TEST_FAKE_SECRET", "fake-secret-value")
            fake_token = os.environ.get("ZENSKILL_TEST_FAKE_TOKEN", "fake-token-value")
            test_data = {"password": fake_secret, "api_key": fake_token, "normal": "value"}
            filtered = privacy.filter_sensitive_data(test_data)
            assert fake_secret not in json.dumps(filtered), "敏感信息未过滤"
            assert fake_token not in json.dumps(filtered), "敏感信息未过滤"
            assert filtered.get("normal") == "value", "正常数据被错误过滤"
            print("  ✅ PrivacyLayer: 敏感信息过滤正常")
            results.append(("PrivacyLayer", True))
        except Exception as e:
            print(f"  ❌ PrivacyLayer: {e}")
            results.append(("PrivacyLayer", False))

        # 4. EnvironmentIndexer
        print("\n[4/6] 测试 EnvironmentIndexer...")
        try:
            indexer = EnvironmentIndexer(test_dir)
            # 使用正确的 API: scan_all (无参数)
            env_info = indexer.scan_all()
            assert "project_stack" in env_info, "环境扫描失败"
            work_pattern = indexer.get_work_pattern_summary()
            assert work_pattern is not None, "工作模式摘要为空"
            print("  ✅ EnvironmentIndexer: 环境索引正常")
            results.append(("EnvironmentIndexer", True))
        except Exception as e:
            print(f"  ❌ EnvironmentIndexer: {e}")
            results.append(("EnvironmentIndexer", False))

        # ---------------------------------------------------------------------
        # Phase 9B: 偏好学习引擎测试
        # ---------------------------------------------------------------------
        print("\n\n🧠 Phase 9B: 偏好学习引擎测试")
        print("-" * 60)

        # 5. PreferenceEngine - 基础功能
        print("\n[5/6] 测试 PreferenceEngine 基础功能...")
        try:
            engine = PreferenceEngine(test_dir)

            # 从行为学习
            result = engine.learn_from_behavior()
            assert "preferences" in result, "学习结果格式错误"
            print("  ✅ learn_from_behavior: 正常")

            # 获取画像摘要
            profile = engine.get_profile_summary()
            assert "average_confidence" in profile, "画像摘要格式错误"
            print("  ✅ get_profile_summary: 正常")

            # 导出/导入
            export_path = test_dir / "export-prefs.json"
            assert engine.export_preferences(str(export_path)), "导出失败"
            assert export_path.exists(), "导出文件不存在"
            print("  ✅ export_preferences: 正常")

            engine2 = PreferenceEngine(test_dir / "other")
            assert engine2.import_preferences(str(export_path)), "导入失败"
            print("  ✅ import_preferences: 正常")

            results.append(("PreferenceEngine (基础)", True))
        except Exception as e:
            print(f"  ❌ PreferenceEngine: {e}")
            results.append(("PreferenceEngine (基础)", False))

        # 6. PreferenceEngine - 增强功能
        print("\n[6/6] 测试 PreferenceEngine 增强功能...")
        try:
            engine = PreferenceEngine(test_dir)

            # 批量历史学习
            learn_result = engine.learn_from_history(limit=10)
            assert "events_processed" in learn_result, "批量学习结果格式错误"
            print("  ✅ learn_from_history: 批量学习正常")

            # 置信度可视化
            chart = engine.get_confidence_chart()
            assert "置信度" in chart or "confidence" in chart.lower(), "可视化格式错误"
            print("  ✅ get_confidence_chart: 可视化正常")

            # 与全局同步（测试合并逻辑）
            sync_result = engine.sync_with_global()
            assert "merged" in sync_result, "同步结果格式错误"
            print("  ✅ sync_with_global: 偏好合并正常")

            results.append(("PreferenceEngine (增强)", True))
        except Exception as e:
            print(f"  ❌ PreferenceEngine 增强: {e}")
            results.append(("PreferenceEngine (增强)", False))

    # -------------------------------------------------------------------------
    # 测试总结
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}: {name}")

    print()
    print(f"  通过: {passed}/{total}")
    print(f"  成功率: {passed / total * 100:.1f}%")

    if passed == total:
        print("\n🎉 所有测试通过！Phase 9A + 9B 功能完整！")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查上面的错误信息")
        return 1


if __name__ == "__main__":
    exit(run_tests())
