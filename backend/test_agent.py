import os
import sys
import asyncio
from pathlib import Path

# Setup paths
media_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../media"))
os.environ["MEDIA_DIR"] = media_dir

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.agents.librarian import get_librarian_agent

async def test_agent():
    print(f"Testing Agent with MEDIA_DIR: {media_dir}")
    inbox_dir = os.path.join(media_dir, "inbox")
    os.makedirs(inbox_dir, exist_ok=True)
    
    # Create a dummy messy file
    dummy_file = os.path.join(inbox_dir, "the.matrix.1999.1080p.mkv")
    Path(dummy_file).touch()
    print(f"Created messy file at: {dummy_file}")
    
    agent_executor = get_librarian_agent()
    inputs = {"messages": [("user", "Please organize my inbox directory.")]}
    
    print("\n--- Agent Execution Stream ---")
    try:
        async for chunk in agent_executor.astream(inputs, stream_mode="updates"):
            for node, values in chunk.items():
                if node == "tools":
                    tool_msgs = values.get("messages", [])
                    for tool_msg in tool_msgs:
                        print(f"[TOOL EXECUTED] {tool_msg.name}:\n{tool_msg.content}\n")
                elif node == "agent":
                    agent_msgs = values.get("messages", [])
                    for agent_msg in agent_msgs:
                        if hasattr(agent_msg, 'tool_calls') and agent_msg.tool_calls:
                            for tc in agent_msg.tool_calls:
                                print(f"[AGENT THOUGHT] Decided to use tool '{tc['name']}' with args: {tc['args']}\n")
                        else:
                            print(f"[AGENT SUMMARY] {agent_msg.content}\n")
    except Exception as e:
        print(f"Agent failed: {e}")
        
    print("\n--- Final Directory State ---")
    matrix_dir = os.path.join(media_dir, "The Matrix (1999)")
    if os.path.exists(matrix_dir):
        print(f"Library target dir exists: {matrix_dir}")
        print("Files inside:", os.listdir(matrix_dir))
    else:
        print("Move operation apparently failed.")

if __name__ == "__main__":
    asyncio.run(test_agent())
