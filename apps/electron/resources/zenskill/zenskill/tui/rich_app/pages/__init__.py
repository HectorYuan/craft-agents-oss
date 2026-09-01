"""Rich TUI 页面组件。

每个页面遵循统一接口:
- __init__(console, data)
- render(**kwargs) -> None
"""

from .dashboard import DashboardPage
from .doctor import DoctorPage
from .growth import GrowthPage
from .gtd import GTDPage
from .help import HelpPage
from .knowledge import KnowledgePage
from .mirror import MirrorPage
from .search import SearchPage
from .settings import SettingsPage
from .skills import SkillsPage
from .status import StatusPage

__all__ = [
    "DashboardPage",
    "DoctorPage",
    "GrowthPage",
    "GTDPage",
    "HelpPage",
    "KnowledgePage",
    "MirrorPage",
    "SearchPage",
    "SettingsPage",
    "SkillsPage",
    "StatusPage",
]
