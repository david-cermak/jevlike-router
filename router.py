import json
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent / "logs" / "router_debug.log"

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


debug_router = DebugRouter()
