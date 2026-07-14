from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMClient(ABC):
    @abstractmethod
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        raise NotImplementedError
