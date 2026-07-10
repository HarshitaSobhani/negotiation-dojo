import os
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from auth import get_current_user, hash_password, verify_password
from db import Message, Negotiation, User, get_db, init_db
from negotiation import CATEGORIES, chat_turn, generate_debrief, generate_persona

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])

init_db()


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class StartRequest(BaseModel):
    category: str
    scenario_text: str


class MessageRequest(BaseModel):
    message: str


@app.post("/api/auth/signup")
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=req.email).first():
        raise HTTPException(400, "email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    return {"email": user.email}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "invalid email or password")
    request.session["user_id"] = user.id
    return {"email": user.email}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email}


@app.get("/api/categories")
def categories():
    return [{"id": k, "label": k.replace("_", " ").title()} for k in CATEGORIES]


@app.post("/api/negotiations")
def create_negotiation(req: StartRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.category not in CATEGORIES:
        raise HTTPException(400, "unknown category")
    if not req.scenario_text.strip():
        raise HTTPException(400, "scenario_text is required")

    persona = generate_persona(req.category, req.scenario_text)
    negotiation = Negotiation(
        user_id=user.id,
        category=req.category,
        scenario_text=req.scenario_text,
        persona_target=persona["target"],
        persona_walk_away=persona["walk_away"],
        persona_personality=persona["personality"],
    )
    db.add(negotiation)
    db.commit()
    return {
        "id": negotiation.id,
        "category": negotiation.category,
        "scenario_text": negotiation.scenario_text,
    }


def _load_active_negotiation(negotiation_id: int, user: User, db: Session) -> Negotiation:
    negotiation = db.get(Negotiation, negotiation_id)
    if not negotiation or negotiation.user_id != user.id:
        raise HTTPException(404, "negotiation not found")
    if negotiation.ended_at:
        raise HTTPException(400, "negotiation already ended")
    return negotiation


@app.post("/api/negotiations/{negotiation_id}/messages")
def send_message(
    negotiation_id: int,
    req: MessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    negotiation = _load_active_negotiation(negotiation_id, user, db)

    db.add(Message(negotiation_id=negotiation.id, role="user", content=req.message))
    db.flush()

    history = [{"role": m.role, "content": m.content} for m in negotiation.messages]
    persona = {
        "target": negotiation.persona_target,
        "walk_away": negotiation.persona_walk_away,
        "personality": negotiation.persona_personality,
    }
    reply = chat_turn(negotiation.category, negotiation.scenario_text, persona, history)

    db.add(Message(negotiation_id=negotiation.id, role="assistant", content=reply))
    db.commit()
    return {"reply": reply}


@app.post("/api/negotiations/{negotiation_id}/end")
def end_negotiation(
    negotiation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    negotiation = _load_active_negotiation(negotiation_id, user, db)

    history = [{"role": m.role, "content": m.content} for m in negotiation.messages]
    persona = {
        "target": negotiation.persona_target,
        "walk_away": negotiation.persona_walk_away,
        "personality": negotiation.persona_personality,
    }
    debrief = generate_debrief(negotiation.category, negotiation.scenario_text, persona, history)

    negotiation.final_number = debrief.get("final_number")
    negotiation.outcome = debrief["outcome"]
    negotiation.debrief = debrief["debrief"]
    negotiation.ended_at = datetime.utcnow()
    db.commit()

    return {
        "target": negotiation.persona_target,
        "walk_away": negotiation.persona_walk_away,
        "personality": negotiation.persona_personality,
        "final_number": negotiation.final_number,
        "outcome": negotiation.outcome,
        "debrief": negotiation.debrief,
    }


@app.get("/api/negotiations")
def list_negotiations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    negotiations = (
        db.query(Negotiation)
        .filter_by(user_id=user.id)
        .order_by(Negotiation.created_at.desc())
        .all()
    )
    return [
        {
            "id": n.id,
            "category": n.category,
            "scenario_text": n.scenario_text,
            "outcome": n.outcome,
            "created_at": n.created_at.isoformat(),
            "ended_at": n.ended_at.isoformat() if n.ended_at else None,
        }
        for n in negotiations
    ]


@app.get("/api/negotiations/{negotiation_id}")
def get_negotiation(negotiation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    negotiation = db.get(Negotiation, negotiation_id)
    if not negotiation or negotiation.user_id != user.id:
        raise HTTPException(404, "negotiation not found")

    result = {
        "id": negotiation.id,
        "category": negotiation.category,
        "scenario_text": negotiation.scenario_text,
        "messages": [{"role": m.role, "content": m.content} for m in negotiation.messages],
        "ended": negotiation.ended_at is not None,
    }
    if negotiation.ended_at:
        result["reveal"] = {
            "target": negotiation.persona_target,
            "walk_away": negotiation.persona_walk_away,
            "personality": negotiation.persona_personality,
            "final_number": negotiation.final_number,
            "outcome": negotiation.outcome,
            "debrief": negotiation.debrief,
        }
    return result


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
