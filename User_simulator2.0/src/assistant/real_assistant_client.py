from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple
import json
from urllib.parse import urlparse
from urllib import request
from urllib.error import HTTPError, URLError


PostJson = Callable[[str, Dict[str, Any], float], Any]


class RealAssistantClient:
    """HTTP adapter for the enterprise assistant pipeline."""

    def __init__(self, config: Dict[str, Any] | None = None, post_json: PostJson | None = None):
        self.config = config or {}
        self.base_url = str(self.config.get("base_url") or "http://10.67.43.6:8338").rstrip("/")
        self.policy_base_url = str(self.config.get("policy_base_url") or self.base_url).rstrip("/")
        self.response_base_url = str(self.config.get("response_base_url") or self.policy_base_url).rstrip("/")
        self.timeout = float(self.config.get("timeout", 120))
        self.default_cases = str(self.config.get("default_cases") or "无，目前知识不足以解决用户需求")
        self.common_sense_cases = str(self.config.get("common_sense_cases") or "无，目前用户需求仅需要常识解决")
        self.no_rag_cases = str(self.config.get("no_rag_cases") or "无，目前未配置案例检索结果")
        self.query_path = str(self.config.get("query_path") or "/query")
        self.trigger_path = str(self.config.get("trigger_path") or "/trigger")
        self.policy_path = str(self.config.get("policy_path") or "/policy")
        self.response_path = str(self.config.get("response_path") or "/response")
        self.allow_missing_policy = bool(self.config.get("allow_missing_policy", True))
        self.missing_policy_value = self.config.get("missing_policy_value", "")
        self._post_json = post_json or post_json_urllib

    def reply(self, dialogue_history: List[Dict[str, str]]) -> str:
        query, _ = self.call_query(dialogue_history)
        trigger, _ = self.call_trigger(dialogue_history, query)
        cases = self.build_cases(dialogue_history, query, trigger)
        policy, _ = self.call_policy(dialogue_history, cases)
        response, _ = self.call_response(dialogue_history, policy, cases)
        return str(response).strip()

    def call_query(self, dialogue: List[Dict[str, str]]) -> Tuple[Any, Any]:
        return self._call_step(self.query_path, {"dialogue": dialogue})

    def call_trigger(self, dialogue: List[Dict[str, str]], query: Any) -> Tuple[Any, Any]:
        return self._call_step(self.trigger_path, {"dialogue": dialogue, "query": query})

    def call_policy(self, dialogue: List[Dict[str, str]], cases: Any) -> Tuple[Any, Any]:
        try:
            return self._call_step(self.policy_path, {"dialogue": dialogue, "cases": cases}, self.policy_base_url)
        except AssistantApiError as exc:
            if self.allow_missing_policy and exc.status_code == 404:
                return self.missing_policy_value, None
            raise

    def call_response(self, dialogue: List[Dict[str, str]], policy: Any, cases: Any) -> Tuple[Any, Any]:
        return self._call_step(
            self.response_path,
            {"dialogue": dialogue, "policy": policy, "cases": cases},
            self.response_base_url,
        )

    def build_cases(self, dialogue: List[Dict[str, str]], query: Any, trigger: Any) -> str:
        trigger_text = str(trigger or "")
        if "检索案例" in trigger_text:
            return self.no_rag_cases
        if "预案" in trigger_text:
            return self.common_sense_cases
        return self.default_cases

    def _call_step(self, path: str, payload: Dict[str, Any], base_url: str | None = None) -> Tuple[Any, Any]:
        url = build_url(base_url or self.base_url, path)
        response = self._post_json(url, payload, self.timeout)
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
        raise AssistantApiError(exc.code, url, body) from exc
    except URLError as exc:
        raise RuntimeError(f"Assistant API request failed for {url}: {exc.reason}") from exc
    return json.loads(raw)


class AssistantApiError(RuntimeError):
    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"Assistant API HTTP {status_code} from {url}: {body[:500]}")


def build_url(base_url: str, path: str) -> str:
    if urlparse(path).scheme:
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url.rstrip('/')}{path}"
