from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


PostJson = Callable[[str, Dict[str, Any], float], Any]


class AssistantApiClient:
    """HTTP adapter for the real enterprise assistant pipeline."""

    def __init__(
        self,
        base_url: str = "http://10.67.43.6:8338",
        policy_base_url: str | None = None,
        response_base_url: str | None = None,
        timeout: float = 120,
        query_path: str = "/query",
        trigger_path: str = "/trigger",
        policy_path: str = "/policy",
        response_path: str = "/response",
        default_cases: str = "无，目前知识不足以解决用户需求",
        common_sense_cases: str = "无，目前用户需求仅需要常识解决",
        no_rag_cases: str = "无，目前未配置案例检索结果",
        allow_missing_policy: bool = True,
        missing_policy_value: Any = "",
        post_json: PostJson | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.policy_base_url = (policy_base_url or self.base_url).rstrip("/")
        self.response_base_url = (response_base_url or self.policy_base_url).rstrip("/")
        self.timeout = timeout
        self.query_path = query_path
        self.trigger_path = trigger_path
        self.policy_path = policy_path
        self.response_path = response_path
        self.default_cases = default_cases
        self.common_sense_cases = common_sense_cases
        self.no_rag_cases = no_rag_cases
        self.allow_missing_policy = allow_missing_policy
        self.missing_policy_value = missing_policy_value
        self._post_json = post_json or post_json_urllib

    def reply(self, dialogue_history: List[Dict[str, str]]) -> str:
        query, _ = self.call_query(dialogue_history)
        trigger, _ = self.call_trigger(dialogue_history, query)
        cases = self.build_cases(trigger)
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

    def build_cases(self, trigger: Any) -> str:
        trigger_text = str(trigger or "")
        if "检索案例" in trigger_text:
            return self.no_rag_cases
        if "预案" in trigger_text:
            return self.common_sense_cases
        return self.default_cases

    def _call_step(self, path: str, payload: Dict[str, Any], base_url: str | None = None) -> Tuple[Any, Any]:
        response = self._post_json(build_url(base_url or self.base_url, path), payload, self.timeout)
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
