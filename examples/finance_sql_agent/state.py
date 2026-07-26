"""示例 StateProvider:对指标库 approval_rates 表做前后快照。"""

from agentinvariant.state import SqliteStateProvider

from .tools import _db

state_provider = SqliteStateProvider(
    connection_factory=_db,
    queries={
        "approval_rates": "SELECT department, month, rate FROM approval_rates ORDER BY department, month",
    },
)
