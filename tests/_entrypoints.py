"""测试专用的入口函数与 StateProvider(供 dotted-path 解析)。"""

from langchain_core.tools import BaseTool


def raise_boom(tools: list[BaseTool], scenario: dict) -> str:
    raise RuntimeError("boom: candidate 运行时异常")


class ResetCountingProvider:
    """记录 reset 调用次数的最小 StateProvider。"""

    def __init__(self) -> None:
        self.resets = 0
        self.value = {"orders": [{"id": 1, "status": "CREATED"}]}

    def reset(self, scenario: dict) -> None:
        self.resets += 1

    def snapshot(self, scenario: dict) -> dict:
        return self.value

    def normalize(self, state: dict) -> dict:
        return state


reset_provider = ResetCountingProvider()
