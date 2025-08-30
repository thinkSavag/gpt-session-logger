from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI()

def mcp_tools_manifest():
    # One tool only: init_session_log
    return {
        "tools": [
            {
                "name": "init_session_log",
                "description": "Return a minimal Canvas block for a new Session Log.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"}  # optional, ignored for now
                    }
                }
            }
        ]
    }

# Health: make Render happy
@app.get("/")
async def root():
    return {"ok": True, "service": "session-logger-mcp", "mode": "skeleton"}

# MCP manifest over SSE
@app.get("/sse")
async def sse(request: Request):
    async def gen():
        yield {"event": "manifest", "data": json.dumps(mcp_tools_manifest())}
        while True:
            if await request.is_disconnected():
                break
            yield {"event": "ping", "data": "ok"}
            await asyncio.sleep(15)
    return EventSourceResponse(gen())

# Tool endpoint: return a Canvas with "hello world!"
@app.post("/tool/init_session_log")
async def init_session_log(payload: dict):
    return {
        "canvas_markdown": "# Session Log\n\nhello world!\n"
    }
