from typing import Any


class AgentMintError(Exception):
    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.data = data
