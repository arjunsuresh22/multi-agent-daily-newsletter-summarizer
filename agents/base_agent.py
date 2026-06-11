from __future__ import annotations
import anthropic
from tools.cost_tracker import CostTracker


def run_agentic_loop(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict] | None,
    tool_executor,
    max_tokens: int = 2048,
) -> str:
    """Standard agentic loop: call model, handle tool use, return final text."""
    while True:
        kwargs = dict(model=model, system=system, messages=messages, max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)
        CostTracker.get().add(model, response.usage.input_tokens, response.usage.output_tokens)

        if response.stop_reason in ("end_turn", "max_tokens"):
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = tool_executor(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
