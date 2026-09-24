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
