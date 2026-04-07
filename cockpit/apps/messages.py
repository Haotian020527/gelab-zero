"""Messages app API — send, read, delete conversations."""

from __future__ import annotations

import time
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    contact: str
    text: str


class ReadConversationRequest(BaseModel):
    contact: str


class DeleteConversationRequest(BaseModel):
    contact: str


# ---------------------------------------------------------------------------

@router.get("/status")
def get_messages_status():
    sm = get_state_manager()
    return sm.get("messages")


@router.get("/conversations")
def list_conversations():
    sm = get_state_manager()
    msgs = sm.get("messages")
    convos = msgs.get("conversations", [])
    return [{"contact": c["contact"], "last_message": c["last_message"],
             "time": c["time"], "unread": c["unread"]} for c in convos]


@router.post("/send")
def send_message(req: SendMessageRequest):
    sm = get_state_manager()
    msgs = sm.get("messages")
    convos = msgs.get("conversations", [])

    # Find or create conversation
    found = False
    for conv in convos:
        if conv["contact"] == req.contact:
            conv["messages"].append({
                "from": "me",
                "text": req.text,
                "time": time.strftime("%H:%M"),
            })
            conv["last_message"] = req.text
            conv["time"] = time.strftime("%H:%M")
            conv["unread"] = False
            found = True
            break

    if not found:
        convos.insert(0, {
            "contact": req.contact,
            "last_message": req.text,
            "time": time.strftime("%H:%M"),
            "unread": False,
            "messages": [{"from": "me", "text": req.text, "time": time.strftime("%H:%M")}],
        })

    sm.update("messages", conversations=convos, current_screen="messages_conversation")
    sm.set_active_app("messages")

    return {"status": "ok", "sent_to": req.contact, "text": req.text,
            "notification": "消息已发送"}


@router.post("/read")
def read_conversation(req: ReadConversationRequest):
    sm = get_state_manager()
    msgs = sm.get("messages")
    convos = msgs.get("conversations", [])

    for conv in convos:
        if conv["contact"] == req.contact:
            conv["unread"] = False
            sm.update("messages", conversations=convos,
                      current_screen="messages_conversation",
                      message_status="read")
            unread_count = sum(1 for c in convos if c["unread"])
            return {"status": "ok", "contact": req.contact,
                    "messages": conv["messages"],
                    "message_status": "read",
                    "unread_count": unread_count}

    return {"status": "error", "message": f"未找到与 {req.contact} 的对话"}


@router.post("/delete")
def delete_conversation(req: DeleteConversationRequest):
    sm = get_state_manager()
    msgs = sm.get("messages")
    convos = msgs.get("conversations", [])

    original_len = len(convos)
    convos = [c for c in convos if c["contact"] != req.contact]

    if len(convos) == original_len:
        return {"status": "error", "message": f"未找到与 {req.contact} 的对话"}

    sm.update("messages", conversations=convos, current_screen="messages_home")
    return {"status": "ok", "deleted": req.contact,
            "conversation_list": [c["contact"] for c in convos]}


@router.get("/unread_count")
def get_unread_count():
    sm = get_state_manager()
    msgs = sm.get("messages")
    count = sum(1 for c in msgs.get("conversations", []) if c["unread"])
    return {"unread_count": count}
