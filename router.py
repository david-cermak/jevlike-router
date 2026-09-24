import json
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent / "logs" / "router_debug.log"


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


class DebugRouter:
    """
    Temporary router.

    Eventually this will classify the request and select:
      easy   -> Ollama
      medium -> DeepSeek
      hard   -> another model

    For now it always selects Ollama and logs the full request.
    """

    OLLAMA_MODEL = "ollama/glm-4.7-flash"

    def _log(self, line, fh):
        print(line)
        fh.write(line + "\n")

    async def run(self, context):
        messages = context.structured_messages or context.raw_messages
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
            self._log(f"\n=== ROUTING TO: {self.OLLAMA_MODEL} ===", fh)
            self._log("=" * 80 + "\n", fh)
            fh.flush()

        context.candidate_models = [self.OLLAMA_MODEL]
        context.signals["selected_model"] = self.OLLAMA_MODEL
        return context


debug_router = DebugRouter()
