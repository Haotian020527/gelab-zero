"""Phone app API — calls, contacts, call log."""

from __future__ import annotations

import time
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/phone", tags=["phone"])


class DialRequest(BaseModel):
    number: str = ""
    contact: str = ""


class AddContactRequest(BaseModel):
    name: str
    number: str


class EditContactRequest(BaseModel):
    name: str
    new_number: str = ""
    new_name: str = ""


# ---------------------------------------------------------------------------

@router.get("/status")
def get_phone_status():
    sm = get_state_manager()
    return sm.get("phone")


@router.post("/dial")
def dial(req: DialRequest):
    sm = get_state_manager()
    phone = sm.get("phone")

    # Resolve contact name to number if needed
    number = req.number
    contact = req.contact
    if contact and not number:
        contacts = phone.get("contacts", [])
        for c in contacts:
            if c["name"] == contact:
                number = c["number"]
                break
        if not number:
            return {"status": "error", "message": f"联系人 {contact} 未找到"}

    sm.update("phone",
              in_call=True,
              call_number=number,
              call_contact=contact or number,
              call_duration_sec=0,
              current_screen="phone_calling")
    sm.set_active_app("phone")

    # Add to call log
    call_log = phone.get("call_log", [])
    call_log.insert(0, {
        "name": contact or number,
        "number": number,
        "type": "outgoing",
        "time": time.strftime("%H:%M"),
    })
    sm.update("phone", call_log=call_log[:20])

    return {"status": "ok", "calling": contact or number, "number": number}


@router.post("/answer")
def answer():
    sm = get_state_manager()
    sm.update("phone", in_call=True, current_screen="phone_in_call")
    return {"status": "ok", "in_call": True}


@router.post("/hangup")
def hangup():
    sm = get_state_manager()
    sm.update("phone",
              in_call=False,
              call_number="",
              call_contact="",
              call_duration_sec=0,
              current_screen="phone_home")
    return {"status": "ok", "in_call": False}


@router.get("/call_log")
def get_call_log():
    sm = get_state_manager()
    return sm.get("phone").get("call_log", [])


@router.get("/contacts")
def get_contacts():
    sm = get_state_manager()
    return sm.get("phone").get("contacts", [])


@router.post("/contacts/add")
def add_contact(req: AddContactRequest):
    sm = get_state_manager()
    phone = sm.get("phone")
    contacts = phone.get("contacts", [])

    # Check duplicate
    for c in contacts:
        if c["name"] == req.name:
            return {"status": "error", "message": f"联系人 {req.name} 已存在"}

    contacts.append({"name": req.name, "number": req.number})
    sm.update("phone", contacts=contacts, current_screen="phone_contacts")
    return {"status": "ok", "name": req.name, "number": req.number}


@router.post("/contacts/edit")
def edit_contact(req: EditContactRequest):
    sm = get_state_manager()
    phone = sm.get("phone")
    contacts = phone.get("contacts", [])

    for c in contacts:
        if c["name"] == req.name:
            if req.new_number:
                c["number"] = req.new_number
            if req.new_name:
                c["name"] = req.new_name
            sm.update("phone", contacts=contacts, current_screen="phone_contact_detail")
            return {"status": "ok", "contact": c}

    return {"status": "error", "message": f"联系人 {req.name} 未找到"}


@router.post("/contacts/search")
def search_contacts(query: str = ""):
    sm = get_state_manager()
    phone = sm.get("phone")
    contacts = phone.get("contacts", [])
    results = [c for c in contacts if query.lower() in c["name"].lower() or query in c["number"]]
    sm.update("phone", current_screen="phone_contacts_search")
    return {"status": "ok", "results": results, "count": len(results)}
