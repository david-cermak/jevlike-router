# jevlike-router

LiteLLM-based smart router for coding harnesses.

## Status

Temporary pass-through: `DebugRouter` prints each request’s messages and always routes to local Ollama (`ollama/glm-4.7-flash`).

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

Example:

```bash
export LITELLM_MASTER_KEY=sk-test
export LITELLM_API_KEY=sk-test
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

On each request the proxy terminal should print `=== REQUEST TO ROUTER ===` and `=== ROUTING TO: ollama/glm-4.7-flash ===`.
