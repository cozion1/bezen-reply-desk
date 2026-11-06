"""BEZEN Reply Desk: the web app and API, served from one Vultr VM."""
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm, paypal, pipeline, store
from .samples import SAMPLES

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
MAX_REPLIES = int(os.environ.get("MAX_REPLIES", "200"))

app = FastAPI(title="BEZEN Reply Desk")
store.init()


class NewReply(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    company: str = Field(default="", max_length=120)
    stage: str = Field(default="", max_length=80)
    last_message: str = Field(default="", max_length=300)
    allowed: str = Field(default="", max_length=200)
    price: str = Field(default="", max_length=12, pattern=r"^$|^\d{1,6}(\.\d{2})?$")
    offer: str = Field(default="", max_length=120)


class Decision(BaseModel):
    message: str = Field(default="", max_length=3000)
    by: str = Field(default="Team member", max_length=60)
    reason: str = Field(default="", max_length=300)


@app.get("/api/health")
def health():
    return {"ok": True, "model": f"{llm.provider()}:{llm.model_name()}", "host": "vultr-vm",
            "paypal": "sandbox" if paypal.enabled() else "off"}


@app.get("/api/replies")
def list_replies():
    return store.all_replies()


@app.get("/api/replies/{rid}")
def get_reply(rid: int):
    r = store.get(rid)
    if not r:
        raise HTTPException(404, "reply not found")
    return r


@app.post("/api/replies")
def add_reply(body: NewReply, bg: BackgroundTasks):
    if len(store.all_replies()) >= MAX_REPLIES:
        raise HTTPException(429, "demo inbox is full; press Reset demo")
    lead = {k: v for k, v in body.model_dump().items() if k != "text" and v}
    rid = store.add_reply(body.text, lead)
    bg.add_task(pipeline.process, rid)
    return store.get(rid)


@app.post("/api/replies/{rid}/approve")
def approve(rid: int, body: Decision):
    r = store.get(rid)
    if not r or r["status"] != "awaiting_approval":
        raise HTTPException(409, "this reply is not waiting for approval")
    if (r.get("reading") or {}).get("route") == "human" and not body.message.strip():
        raise HTTPException(422, "a human reply must be written by the person taking it")
    return pipeline.approve(rid, body.message or r["reading"].get("draft", ""), body.by)


@app.post("/api/replies/{rid}/reject")
def reject(rid: int, body: Decision):
    r = store.get(rid)
    if not r or r["status"] != "awaiting_approval":
        raise HTTPException(409, "this reply is not waiting for approval")
    return pipeline.reject(rid, body.by, body.reason)


@app.post("/api/replies/{rid}/payment")
def refresh_payment(rid: int):
    r = store.get(rid)
    if not r or not (r.get("reading") or {}).get("payment"):
        raise HTTPException(404, "no payment on this reply")
    try:
        return pipeline.refresh_payment(rid)
    except Exception as e:  # PayPal errors are reported, not hidden
        raise HTTPException(502, str(e))


@app.post("/api/demo/load")
def load_samples(bg: BackgroundTasks):
    store.clear()
    for text, lead in SAMPLES:
        rid = store.add_reply(text, lead)
        bg.add_task(pipeline.process, rid)
    return {"loaded": len(SAMPLES)}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
