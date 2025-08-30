from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import json, time, uuid, os, asyncio

APP_TOKEN = os.getenv("APP_TOKEN", "devtoken")
DB = "sessions.json"

def load_db():
    if not os.path.exists(DB): return {}
    with open(DB, "r", encoding="utf-8") as f: return json.load(f)

def save_db(d):
    with open(DB, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)

app = FastAPI()

def mcp_tools_manifest():
    return {
        "tools":[
            {
                "name":"init_session_log",
                "description":"Create a new Session Log and return a canonical JSON payload.",
                "input_schema":{
                    "type":"object",
                    "properties":{
                        "title":{"type":"string"},
                        "agenda":{"type":"array","items":{"type":"string"}},
                        "key_topics":{"type":"array","items":{"type":"string"}},
                        "key_terms":{"type":"array","items":{"type":"string"}}
                    }
                }
            },
            {
                "name":"heartbeat",
                "description":"Append HB#n to a session and return one-line status plus remaining agenda.",
                "input_schema":{
                    "type":"object",
                    "required":["session_id","status_note"],
                    "properties":{
                        "session_id":{"type":"string"},
                        "status_note":{"type":"string"}
                    }
                }
            },
            {
                "name":"cross_session_hits",
                "description":"Find recent sessions with overlapping topics/terms and return ids with reasons.",
                "input_schema":{
                    "type":"object",
                    "required":["session_id"],
                    "properties":{
                        "session_id":{"type":"string"},
                        "topics":{"type":"array","items":{"type":"string"}},
                        "terms":{"type":"array","items":{"type":"string"}},
                        "limit":{"type":"integer","default":8}
                    }
                }
            }
        ]
    }

@app.get("/sse")
async def sse_endpoint(request: Request, authorization: str | None = Header(default=None)):
    if APP_TOKEN and authorization and authorization.replace("Bearer ","") != APP_TOKEN:
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    async def gen():
        yield {"event":"manifest","data":json.dumps(mcp_tools_manifest())}
        while True:
            if await request.is_disconnected(): break
            yield {"event":"ping","data":"ok"}
            await asyncio.sleep(15)
    return EventSourceResponse(gen())

@app.post("/tool/init_session_log")
async def init_session_log(payload: dict, authorization: str | None = Header(default=None)):
    if APP_TOKEN and authorization and authorization.replace("Bearer ","") != APP_TOKEN:
        return JSONResponse({"error":"unauthorized"}, status_code=401)
    db = load_db()
    sid = f"{time.strftime('%Y-%m-%dT%H:%M')} — {payload.get('title') or 'Untitled'} — {uuid.uuid4().hex[:6]}"
    db[sid] = {
        "session_id": sid,
        "title": payload.get("title") or "Session Log",
        "agenda": payload.get("agenda") or [],
        "key_topics": payload.get("key_topics") or [],
        "key_terms": payload.get("key_terms") or [],
        "heartbeats": ["HB#0: Canvas initialized"],
        "created_at": time.time()
    }
    save_db(db)
    return {
        "session_id": sid,
        "canvas_markdown": f"""# Session Log

**Session ID:** {sid}

## Agenda
{''.join([f'1. {a}\\n' for a in db[sid]['agenda']]) or '- (none)'}
## Key Topics
{''.join([f'- {t}\\n' for t in db[sid]['key_topics']]) or '- (none)'}
## Key Terms (seed)
{''.join([f'- {t}\\n' for t in db[sid]['key_terms']]) or '- (none)'}
## Heartbeat Log (every 5 replies)
- HB#0: Canvas initialized

## Cross-Session Hits (when requested)
- (placeholder)

## Parking Lot
- Items to carry to next block if time expires

_Usage:_ After every 5 exchanges, append `HB#n:` with a one-line status + remaining agenda.
"""
    }

@app.post("/tool/heartbeat")
async def heartbeat(payload: dict, authorization: str | None = Header(default=None)):
    if APP_TOKEN and authorization and authorization.replace("Bearer ","") != APP_TOKEN:
        return JSONResponse({"error":"unauthorized"}, status_code=401)
    db = load_db()
    sid = payload["session_id"]
    if sid not in db: return JSONResponse({"error":"unknown session_id"}, status_code=404)
    hb_index = len(db[sid]["heartbeats"])
    line = f"HB#{hb_index}: {payload['status_note']}"
    db[sid]["heartbeats"].append(line)
    save_db(db)
    return {"session_id": sid, "hb_line": line, "remaining_agenda": db[sid]["agenda"]}

@app.post("/tool/cross_session_hits")
async def cross_hits(payload: dict, authorization: str | None = Header(default=None)):
    if APP_TOKEN and authorization and authorization.replace("Bearer ","") != APP_TOKEN:
        return JSONResponse({"error":"unauthorized"}, status_code=401)
    db = load_db()
    sid = payload["session_id"]
    base = db.get(sid, {})
    topics = set([*(payload.get("topics") or base.get("key_topics") or [])])
    terms = set([*(payload.get("terms") or base.get("key_terms") or [])])
    hits = []
    for k,v in sorted(db.items(), key=lambda kv: kv[1]["created_at"], reverse=True):
        if k == sid: continue
        score = len(topics.intersection(v.get("key_topics",[]))) + len(terms.intersection(v.get("key_terms",[])))
        if score>0:
            hits.append({"session_id": k, "score": int(score), "title": v.get("title",""), "why": {
                "topics": list(topics.intersection(v.get("key_topics",[]))),
                "terms": list(terms.intersection(v.get("key_terms",[])))
            }})
    return {"hits": hits[: int(payload.get("limit",8))]}
