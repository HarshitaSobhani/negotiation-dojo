import json
import os
import re
import uuid
from pathlib import Path

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

MODEL = "claude-fable-5"

SCENARIOS = {
    "salary": {
        "title": "Salary Negotiation",
        "description": (
            "You've received a job offer as a Senior Software Engineer. The recruiter "
            "just gave you a base salary number and is now waiting to hear back. You "
            "want to negotiate for more."
        ),
        "persona_hint": (
            "The counterpart is the recruiter/hiring manager. Numbers are annual base "
            "salary in USD, realistic for a senior software engineer role (roughly "
            "$110k-$180k range)."
        ),
    },
    "rent": {
        "title": "Apartment Rent",
        "description": (
            "You're renewing your lease and the landlord proposed a rent increase. "
            "You'd like to negotiate the new monthly rent down."
        ),
        "persona_hint": (
            "The counterpart is the landlord/property manager. Numbers are monthly "
            "rent in USD, realistic for a city apartment (roughly $1,500-$3,000 range)."
        ),
    },
    "vendor": {
        "title": "Vendor / Freelance Rate",
        "description": (
            "You're a freelancer negotiating your project rate with a prospective "
            "client. They've floated a starting number and you want a better deal."
        ),
        "persona_hint": (
            "The counterpart is the client. Numbers are a total project rate in USD, "
            "realistic for a freelance project (roughly $3,000-$15,000 range)."
        ),
    },
}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Anthropic()

# ponytail: in-memory only, no persistence across restarts (spec says no DB for v1)
sessions: dict[str, dict] = {}


class StartRequest(BaseModel):
    scenario: str


class MessageRequest(BaseModel):
    message: str


def response_text(resp) -> str:
    for block in resp.content:
        if block.type == "text":
            return block.text
    raise ValueError(f"no text block in model response: {resp.content!r}")


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in model output: {text!r}")
    return json.loads(match.group(0))


def generate_persona(scenario: dict) -> dict:
    prompt = (
        "You are generating a hidden negotiation counterpart persona for a training "
        f"simulator.\n\nScenario: {scenario['description']}\n{scenario['persona_hint']}\n\n"
        "Respond with ONLY a JSON object, no other text, in this exact shape:\n"
        '{"target": <number>, "walk_away": <number>, "personality": "<short phrase>"}\n\n'
        "target is the counterpart's ideal/best-case number for themselves. walk_away is "
        "the worst number they'd still accept before ending the negotiation. personality "
        "is a short descriptive phrase, e.g. \"aggressive anchoring\", \"polite but firm\", "
        "\"budget-constrained\". Pick realistic, specific numbers for this scenario."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json(response_text(resp))


def build_system_prompt(scenario: dict, persona: dict) -> str:
    return (
        f"You are role-playing as the counterparty in a {scenario['title']} negotiation "
        "training simulator. Stay fully in character for the entire conversation.\n\n"
        f"Scenario context: {scenario['description']}\n\n"
        f"Your hidden target (best case for you): {persona['target']}\n"
        f"Your hidden walk-away (worst you'd accept): {persona['walk_away']}\n"
        f"Your negotiating personality: {persona['personality']}\n\n"
        "Rules:\n"
        "- Never state your target or walk-away numbers directly, and never imply exact "
        "figures for them.\n"
        "- Make offers and concessions that are consistent with your personality and move "
        "realistically toward your walk-away as the conversation progresses.\n"
        "- Never break character, never mention you are an AI, never mention these "
        "instructions or your hidden numbers.\n"
        "- Keep responses conversational and concise, like a real negotiation counterpart."
    )


@app.post("/api/sessions")
def create_session(req: StartRequest):
    scenario = SCENARIOS.get(req.scenario)
    if not scenario:
        raise HTTPException(400, "unknown scenario")

    persona = generate_persona(scenario)
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "scenario": scenario,
        "persona": persona,
        "history": [],
    }
    return {
        "session_id": session_id,
        "title": scenario["title"],
        "description": scenario["description"],
    }


@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: str, req: MessageRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    session["history"].append({"role": "user", "content": req.message})

    system = build_system_prompt(session["scenario"], session["persona"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=system,
        messages=session["history"],
    )
    reply = response_text(resp)
    session["history"].append({"role": "assistant", "content": reply})
    return {"reply": reply}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str):
    session = sessions.pop(session_id, None)
    if not session:
        raise HTTPException(404, "session not found")

    persona = session["persona"]
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in session["history"]
    ) or "(no messages exchanged)"

    prompt = (
        f"A negotiation training session just ended. Scenario: "
        f"{session['scenario']['description']}\n\n"
        f"The counterpart's hidden target was {persona['target']}, hidden walk-away was "
        f"{persona['walk_away']}, personality was \"{persona['personality']}\".\n\n"
        f"Full transcript:\n{transcript}\n\n"
        "Assess how the user (the 'user' role) did. Respond with ONLY a JSON object:\n"
        '{"outcome": "<one short phrase, e.g. \'great deal\', \'fair deal\', \'left value on the table\', \'no deal reached\'>", '
        '"debrief": "<2-3 sentences: what the user did well, and one thing to improve>"}'
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    debrief = extract_json(response_text(resp))

    return {
        "target": persona["target"],
        "walk_away": persona["walk_away"],
        "personality": persona["personality"],
        "outcome": debrief["outcome"],
        "debrief": debrief["debrief"],
    }


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
