"""A LangChain deep agent that uses Threshold's tools through its MCP server (langchain-mcp-adapters, stdio).

    cd server && uv run python examples/mcp_deepagent.py "will an F-150 fit in the garage of scan <scan-id>"

The agent sees the same tools Claude Code does; nothing here imports a Threshold tool directly.
"""
import asyncio
import pathlib
import sys

from deepagents import create_deep_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from threshold.agent.llm import (
    chat,  # Claude with the key from $THRESHOLD_DATA_DIR/.env
)

SERVER = pathlib.Path(__file__).resolve().parents[1]


async def main(question: str) -> None:
    client = MultiServerMCPClient({"threshold": {
        "transport": "stdio", "command": "uv",
        "args": ["run", "--directory", str(SERVER), "python", "-m", "threshold.mcp"]}})
    tools = await client.get_tools()
    agent = create_deep_agent(model=chat(1024), tools=tools, system_prompt=(
        "You answer questions about scanned buildings with the threshold tools. Quote numbers only from tool "
        "results, with their confidence, and say what the scan could not measure. Answer in at most five lines."))
    async for chunk in agent.astream({"messages": [{"role": "user", "content": question}]}, stream_mode="updates"):
        for update in chunk.values():
            for m in (update or {}).get("messages", []) if isinstance(update, dict) else []:
                for call in getattr(m, "tool_calls", None) or []:
                    print(f"-> {call['name']}({call['args']})", flush=True)
                if m.type == "ai" and not getattr(m, "tool_calls", None):
                    print(m.text if hasattr(m, "text") else m.content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: mcp_deepagent.py "<question naming a scan id>"')
    asyncio.run(main(" ".join(sys.argv[1:])))
