"""Codex 平台适配器 (ZSR12 → P1-1 重构)

实现已迁移至 zenskill/platforms/deploy.py 的 DeployAdapter 体系，
本模块保留导入路径兼容。默认部署目录改为 ~/.codex/skills/，
可通过 ~/.zenskill/platforms.yaml 的 deploy.codex.target_dir 覆盖。
"""

from .deploy import CodexAdapter

__all__ = ["CodexAdapter"]
