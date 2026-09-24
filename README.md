# jevlike-router

LiteLLM-based smart router for coding harnesses.

## Status

`DebugRouter` logs each request’s messages and routes:

| Request                         | Backend                         |
|---------------------------------|---------------------------------|
| Title generation (opencode)     | Ollama (`ollama/glm-4.7-flash`) |
| Everything else                 | DeepSeek (`deepseek/deepseek-v4-flash`) |

Detection: messages containing `You are a title generator` or `Generate a title for this conversation`.

Planned later:

| Difficulty | Backend   |
|------------|-----------|
| easy       | Ollama    |
| medium     | DeepSeek  |
| hard       | TBD       |

Clients call the proxy with model `smart-router`.

## Logging

Two components in `router.py`, wired separately in `config.yaml`:

| Component | Registered as | Writes | Covers |
|-----------|---------------|--------|--------|
| `debug_router` | `router_settings.plugins` | `logs/router_debug.log` | Client → proxy: full messages, candidate models, route decision |
| `proxy_hooks` | `litellm_settings.callbacks` | `logs/router_traffic.log` | Proxy → provider (post-routing summary) and provider → client (responses, streamed or not, plus failures) |

A routing plugin can only narrow `candidate_models`; it cannot see responses or
change the outgoing request. `proxy_hooks` is a `CustomLogger`, so it covers the
rest of the round trip. Both logs share a `call_id` so a request and its
response line up.

`router_traffic.log` is compact by design: role counts and character totals
instead of full message dumps, with long fields clipped at `MAX_FIELD_CHARS`.
Streamed replies are reassembled into one entry, so split `tool_calls`
arguments are logged as complete JSON.

`ProxyHooks.async_pre_call_hook` returns `data` unchanged today. It is the seam
where a future cheap-model route can shrink `data["messages"]` before the
upstream call — note that `data["tools"]` must stay intact or the harness's
tool loop breaks.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'litellm[proxy]'
```

## Environment

| Variable              | Role                                      |
|-----------------------|-------------------------------------------|
| `LITELLM_MASTER_KEY`  | Proxy master key (`config.yaml`)          |
| `LITELLM_API_KEY`     | Same value; used by clients / test script |
| `DEEPSEEK_API_KEY`    | DeepSeek API key for non-title traffic    |

Example:

```bash
export LITELLM_MASTER_KEY=sk-test
export LITELLM_API_KEY=sk-test
export DEEPSEEK_API_KEY=sk-...
```

Ollama must be running at `http://127.0.0.1:11434` with `glm-4.7-flash` available.

## Run

```bash
source .venv/bin/activate
litellm --config config.yaml
```

Proxy listens on `http://0.0.0.0:4000`.

Smoke test (with `LITELLM_API_KEY` set):

```bash
./test_local_proxy.sh
```

On each request the proxy terminal / `logs/router_debug.log` should print `ROUTE REASON` and `=== ROUTING TO: ... ===` (`deepseek/...` for normal chat, `ollama/...` for title generation).

`logs/router_traffic.log` should gain a matching `UPSTREAM REQUEST` entry and a
`RESPONSE` / `RESPONSE (stream)` / `RESPONSE FAILED` entry with the same
`call_id`.
