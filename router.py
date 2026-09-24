import json
from datetime import datetime, timezone
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger


LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_PATH = LOG_DIR / "router_debug.log"
TRAFFIC_LOG_PATH = LOG_DIR / "router_traffic.log"

# Tool call arguments carry whole files; keep the traffic log readable.
MAX_FIELD_CHARS = 4000

TITLE_MARKERS = (
    "You are a title generator",
    "Generate a title for this conversation",
)


def _format(value):
    """Pretty-print any message field; fall back to repr for odd types."""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except TypeError:
        return repr(value)


def _message_as_dict(message):
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    if hasattr(message, "dict"):
        return message.dict()
    if hasattr(message, "__dict__"):
        return dict(message.__dict__)
    return {"_raw": message}


def _message_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text") or "")
        return "\n".join(parts)
    return str(content)


def _attr(obj, name, default=None):
    """Read a field off a dict or a pydantic/stream object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _clip(value, limit=MAX_FIELD_CHARS):
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [+{len(text) - limit} chars]"


def _role_summary(messages):
    counts = {}
    for message in messages or []:
        role = _message_as_dict(message).get("role", "?")
        counts[role] = counts.get(role, 0) + 1
    return ", ".join(f"{role}={n}" for role, n in sorted(counts.items()))


def _content_chars(messages):
    return sum(
        len(_message_text(_message_as_dict(message).get("content")))
        for message in messages or []
    )


def _last_user_text(messages):
    for message in reversed(messages or []):
        msg = _message_as_dict(message)
        if msg.get("role") == "user":
            return _message_text(msg.get("content"))
    return ""


def _tool_names(tools):
    names = []
    for tool in tools or []:
        fn = _message_as_dict(_message_as_dict(tool).get("function") or {})
        names.append(fn.get("name") or "?")
    return names


def _render_tool_calls(tool_calls):
    lines = []
    for i, call in enumerate(tool_calls or []):
        call = _message_as_dict(call)
        fn = _message_as_dict(call.get("function") or {})
        lines.append(f"  [{i}] {fn.get('name')} id={call.get('id')}")
        lines.append(f"      args: {_clip(fn.get('arguments'))}")
    return lines


def _write_traffic(lines):
    blob = "\n".join(lines)
    print(blob)
    TRAFFIC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRAFFIC_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(blob + "\n")
        fh.flush()


def _header(title):
    return [
        "",
        "-" * 80,
        f"=== {title} @ {datetime.now(timezone.utc).isoformat()} ===",
    ]


class _StreamCollector:
    """Reassembles a streamed completion so it can be logged as one message."""

    def __init__(self):
        self.model = None
        self.finish_reason = None
        self.usage = None
        self.chunks = 0
        self.content = []
        self.reasoning = []
        self.tool_calls = {}

    def add(self, chunk):
        self.chunks += 1
        self.model = _attr(chunk, "model") or self.model
        self.usage = _attr(chunk, "usage") or self.usage

        for choice in _attr(chunk, "choices") or []:
            self.finish_reason = _attr(choice, "finish_reason") or self.finish_reason
            delta = _attr(choice, "delta")
            if delta is None:
                continue

            text = _attr(delta, "content")
            if text:
                self.content.append(text)
            reasoning = _attr(delta, "reasoning_content")
            if reasoning:
                self.reasoning.append(reasoning)

            for call in _attr(delta, "tool_calls") or []:
                slot = self.tool_calls.setdefault(
                    _attr(call, "index") or 0,
                    {"id": None, "function": {"name": None, "arguments": ""}},
                )
                slot["id"] = _attr(call, "id") or slot["id"]
                fn = _attr(call, "function")
                if fn is None:
                    continue
                slot["function"]["name"] = (
                    _attr(fn, "name") or slot["function"]["name"]
                )
                slot["function"]["arguments"] += _attr(fn, "arguments") or ""

    def lines(self):
        out = [
            f"model: {self.model}",
            f"finish_reason: {self.finish_reason}",
            f"chunks: {self.chunks}",
        ]
        if self.usage is not None:
            out.append(f"usage: {_format(_message_as_dict(self.usage))}")
        if self.reasoning:
            out.append(f"reasoning: {_clip(''.join(self.reasoning))}")
        if self.content:
            out.append(f"content: {_clip(''.join(self.content))}")
        if self.tool_calls:
            out.append("tool_calls:")
            ordered = [self.tool_calls[k] for k in sorted(self.tool_calls)]
            out.extend(_render_tool_calls(ordered))
        return out


class DebugRouter:
    """
    Routes by request type:

      title generation -> Ollama
      everything else  -> DeepSeek

    Eventually this will classify difficulty and select:
      easy   -> Ollama
      medium -> DeepSeek
      hard   -> another model
    """

    OLLAMA_MODEL = "ollama/glm-4.7-flash"
    DEEPSEEK_MODEL = "deepseek/deepseek-v4-flash"

    def _is_title_generation(self, messages):
        for message in messages or []:
            text = _message_text(_message_as_dict(message).get("content"))
            if any(marker in text for marker in TITLE_MARKERS):
                return True
        return False

    def _select_model(self, messages):
        if self._is_title_generation(messages):
            return self.OLLAMA_MODEL, "title_generation"
        return self.DEEPSEEK_MODEL, "default"

    def _log(self, line, fh):
        print(line)
        fh.write(line + "\n")

    async def run(self, context):
        messages = context.structured_messages or context.raw_messages
        selected, reason = self._select_model(messages)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        with LOG_PATH.open("a", encoding="utf-8") as fh:
            self._log("\n" + "=" * 80, fh)
            self._log(
                f"=== REQUEST TO ROUTER @ {datetime.now(timezone.utc).isoformat()} ===",
                fh,
            )
            self._log("=" * 80, fh)

            self._log(f"\nmessages count: {len(messages) if messages else 0}", fh)
            self._log("\nMESSAGES:", fh)

            for i, message in enumerate(messages or []):
                msg = _message_as_dict(message)
                self._log(f"\n--- message {i} ---", fh)
                self._log(f"keys: {sorted(msg.keys())}", fh)

                for key in sorted(msg.keys()):
                    value = msg[key]
                    formatted = _format(value)
                    # Keep single-line scalars readable; expand nested structures.
                    if "\n" in formatted:
                        self._log(f"{key}:\n{formatted}", fh)
                    else:
                        self._log(f"{key}: {formatted}", fh)

            self._log(
                f"\nCANDIDATE MODELS (before): {_format(context.candidate_models)}",
                fh,
            )
            self._log(f"\nROUTE REASON: {reason}", fh)
            self._log(f"=== ROUTING TO: {selected} ===", fh)
            self._log("=" * 80 + "\n", fh)
            fh.flush()

        context.candidate_models = [selected]
        context.signals["selected_model"] = selected
        context.signals["route_reason"] = reason
        return context


class ProxyHooks(CustomLogger):
    """
    Proxy call hooks.

    `DebugRouter` only sees what the client sends. These hooks cover the rest
    of the round trip: the request as it leaves for the provider (after the
    router picked a deployment) and the response on its way back to the
    client, streamed or not.

    `async_pre_call_hook` is also the seam where a future cheap-model route
    can shrink `data["messages"]` before the upstream call.
    """

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        try:
            messages = data.get("messages") or []
            tools = _tool_names(data.get("tools"))

            lines = _header("UPSTREAM REQUEST")
            lines.append(f"call_id: {data.get('litellm_call_id')}")
            lines.append(f"call_type: {call_type}")
            lines.append(f"model: {data.get('model')}")
            lines.append(f"stream: {bool(data.get('stream'))}")
            lines.append(
                f"messages: {len(messages)} ({_role_summary(messages)}) "
                f"chars={_content_chars(messages)}"
            )
            if tools:
                lines.append(f"tools: {len(tools)} [{', '.join(tools)}]")
            last_user = _last_user_text(messages)
            if last_user:
                lines.append(f"last user: {_clip(last_user, 300)}")
            _write_traffic(lines)
        except Exception as exc:
            _write_traffic([f"[hook error] pre_call: {exc!r}"])
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        try:
            lines = _header("RESPONSE")
            lines.append(f"call_id: {data.get('litellm_call_id')}")
            lines.append(f"model: {_attr(response, 'model')}")

            usage = _attr(response, "usage")
            if usage is not None:
                lines.append(f"usage: {_format(_message_as_dict(usage))}")

            for i, choice in enumerate(_attr(response, "choices") or []):
                message = _message_as_dict(_attr(choice, "message") or {})
                lines.append(
                    f"choice {i}: finish_reason={_attr(choice, 'finish_reason')}"
                )
                if message.get("reasoning_content"):
                    lines.append(
                        f"reasoning: {_clip(message['reasoning_content'])}"
                    )
                if message.get("content"):
                    lines.append(f"content: {_clip(_message_text(message['content']))}")
                if message.get("tool_calls"):
                    lines.append("tool_calls:")
                    lines.extend(_render_tool_calls(message["tool_calls"]))
            _write_traffic(lines)
        except Exception as exc:
            _write_traffic([f"[hook error] post_call_success: {exc!r}"])

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict, response, request_data
    ):
        collector = _StreamCollector()
        try:
            async for chunk in response:
                try:
                    collector.add(chunk)
                except Exception:
                    # Never let logging break the stream reaching the client.
                    pass
                yield chunk
        finally:
            try:
                lines = _header("RESPONSE (stream)")
                lines.append(f"call_id: {request_data.get('litellm_call_id')}")
                lines.extend(collector.lines())
                _write_traffic(lines)
            except Exception as exc:
                _write_traffic([f"[hook error] streaming_iterator: {exc!r}"])

    async def async_post_call_failure_hook(
        self, request_data, original_exception, user_api_key_dict, traceback_str=None
    ):
        try:
            lines = _header("RESPONSE FAILED")
            lines.append(f"call_id: {request_data.get('litellm_call_id')}")
            lines.append(f"model: {request_data.get('model')}")
            lines.append(f"exception: {type(original_exception).__name__}")
            lines.append(f"detail: {_clip(original_exception, 1000)}")
            _write_traffic(lines)
        except Exception as exc:
            _write_traffic([f"[hook error] post_call_failure: {exc!r}"])
        return None


debug_router = DebugRouter()
proxy_hooks = ProxyHooks()
