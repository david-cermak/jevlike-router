curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "smart-router",
    "messages": [
      {
        "role": "user",
        "content": "Say hello"
      }
    ]
  }'
