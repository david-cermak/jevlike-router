class DebugRouter:
    """
    Temporary router.

    Eventually this will classify the request and select:
      easy   -> Ollama
      medium -> DeepSeek
      hard   -> another model

    For now it always selects Ollama and prints the request.
    """

    OLLAMA_MODEL = "ollama/glm-4.7-flash"

    async def run(self, context):
        messages = context.structured_messages or context.raw_messages

        print("\n" + "=" * 80)
        print("=== REQUEST TO ROUTER ===")
        print("=" * 80)

        print("\nMESSAGES:")
        for i, message in enumerate(messages):
            print(f"\n--- message {i} ---")
            print(f"role: {message.get('role')}")
            print(f"content: {message.get('content')}")

            if "tool_calls" in message:
                print(f"tool_calls: {message['tool_calls']}")

        print("\nCANDIDATE MODELS (before):", context.candidate_models)
        print("\n=== ROUTING TO:", self.OLLAMA_MODEL, "===")
        print("=" * 80 + "\n")

        context.candidate_models = [self.OLLAMA_MODEL]
        context.signals["selected_model"] = self.OLLAMA_MODEL
        return context


debug_router = DebugRouter()
