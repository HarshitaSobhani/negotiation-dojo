# Negotiation Dojo

Practice negotiations against an AI counterpart that stays in character. Pick a
scenario, negotiate over chat, then end the session to reveal the counterpart's
hidden numbers and get a debrief.

## Run

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
.venv/bin/uvicorn main:app --reload
```

Open http://127.0.0.1:8000 — the backend also serves the frontend directly.

## How it works

- Picking a scenario calls the Anthropic API (`claude-fable-5`) once to generate
  a hidden persona (target number, walk-away number, personality trait). It's
  kept server-side only, in memory, keyed by session id.
- Each chat turn sends the full hidden persona + conversation history as the
  system prompt, instructing the model to stay in character and never reveal
  its numbers.
- "End Negotiation" reveals the stored numbers and asks the model for a short
  debrief based on the transcript.
