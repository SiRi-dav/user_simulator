from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple
from urllib import request
from urllib.error import HTTPError, URLError


PostJson = Callable[[str, Dict[str, Any], float], Any]


class RealAssistantClient:
    """HTTP adapter for the enterprise assistant pipeline."""

    def __init__(self, config: Dict[str, Any] | None = None, post_json: PostJson | None = None):
        self.config = config or {}
        self.base_url = str(self.config.get("base_url") or "http://10.67.43.6:8338").rstrip("/")
        self.timeout = float(self.config.get("timeout", 120))
        self.default_cases = str(self.config.get("default_cases") or "无，目前知识不足以解决用户需求")
        self.common_sense_cases = str(self.config.get("common_sense_cases") or "无，目前用户需求仅需要常识解决")
        self.no_rag_cases = str(self.config.get("no_rag_cases") or "无，目前未配置案例检索结果")
        self._post_json = post_json or post_json_urllib

    def reply(self, dialogue_history: List[Dict[str, str]]) -> str:
        query, _ = self.call_query(dialogue_history)
        trigger, _ = self.call_trigger(dialogue_history, query)
        cases = self.build_cases(dialogue_history, query, trigger)
        policy, _ = self.call_policy(dialogue_history, cases)
        response, _ = self.call_response(dialogue_history, policy, cases)
        return str(response).strip()

    def call_query(self, dialogue: List[Dict[str, str]]) -> Tuple[Any, Any]:
        return self._call_step("/query", {"dialogue": dialogue})

    def call_trigger(self, dialogue: List[Dict[str, str]], query: Any) -> Tuple[Any, Any]:
        return self._call_step("/trigger", {"dialogue": dialogue, "query": query})

    def call_policy(self, dialogue: List[Dict[str, str]], cases: Any) -> Tuple[Any, Any]:
        return self._call_step("/policy", {"dialogue": dialogue, "cases": cases})

    def call_response(self, dialogue: List[Dict[str, str]], policy: Any, cases: Any) -> Tuple[Any, Any]:
        return self._call_step("/response", {"dialogue": dialogue, "policy": policy, "cases": cases})

    def build_cases(self, dialogue: List[Dict[str, str]], query: Any, trigger: Any) -> str:
        trigger_text = str(trigger or "")
        if "检索案例" in trigger_text:
            return self.no_rag_cases
        if "预案" in trigger_text:
            return self.common_sense_cases
        return self.default_cases

    def _call_step(self, path: str, payload: Dict[str, Any]) -> Tuple[Any, Any]:
        response = self._post_json(f"{self.base_url}{path}", payload, self.timeout)
        if isinstance(response, list):
            result = response[0] if response else ""
            elapsed = response[1] if len(response) > 1 else None
            return result, elapsed
        if isinstance(response, dict):
            result = response.get("result", response.get("response", response.get("text", response)))
            elapsed = response.get("time", response.get("elapsed"))
            return result, elapsed
        return response, None


def post_json_urllib(url: str, payload: Dict[str, Any], timeout: float) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Assistant API HTTP {exc.code} from {url}: {body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Assistant API request failed for {url}: {exc.reason}") from exc
    return json.loads(raw)
