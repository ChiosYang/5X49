import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.librarian import get_librarian_agent


router = APIRouter()


@router.get("/api/agents/clean-inbox")
async def clean_inbox_stream():
    """Stream the thoughtful execution of the librarian agent as it cleans the inbox."""

    async def event_generator():
        yield "data: " + json.dumps({"type": "info", "message": "Summoning Librarian Agent..."}) + "\n\n"

        try:
            agent_executor = get_librarian_agent()
            inputs = {"messages": [("user", "Please organize my inbox directory.")]}

            async for chunk in agent_executor.astream(inputs, stream_mode="updates"):
                for node, values in chunk.items():
                    if node == "tools":
                        tool_msgs = values.get("messages", [])
                        for tool_msg in tool_msgs:
                            msg = {
                                "type": "tool_execution",
                                "tool_name": tool_msg.name,
                                "content": tool_msg.content,
                            }
                            yield f"data: {json.dumps(msg)}\n\n"

                    elif node == "agent":
                        agent_msgs = values.get("messages", [])
                        for agent_msg in agent_msgs:
                            if hasattr(agent_msg, "tool_calls") and agent_msg.tool_calls:
                                for tc in agent_msg.tool_calls:
                                    msg = {
                                        "type": "thought",
                                        "message": f"I need to use '{tc['name']}' with arguments: {tc['args']}",
                                    }
                                    yield f"data: {json.dumps(msg)}\n\n"
                            else:
                                msg = {
                                    "type": "thought",
                                    "message": agent_msg.content,
                                }
                                yield f"data: {json.dumps(msg)}\n\n"

            yield "data: " + json.dumps({"type": "done", "message": "Agent finished task."}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
            yield "data: " + json.dumps({"type": "done", "message": "Terminated with error."}) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
