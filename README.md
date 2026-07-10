# Negotiation Dojo

Practice negotiations against an AI counterpart that stays in character. Sign
in, describe a scenario, negotiate over chat, then end the session to reveal
the counterpart's hidden numbers and get an honest debrief. Past negotiations
are saved to your account.

## Run

Requires a running Postgres server (`brew services start postgresql@17` or
similar) and a database:

```bash
createdb negotiation_dojo
```

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
export SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export DATABASE_URL=postgresql+psycopg2:///negotiation_dojo  # optional, this is the default
.venv/bin/uvicorn main:app --reload
```

Open http://127.0.0.1:8000 — the backend also serves the frontend directly.
Tables are created automatically on startup.

## How it works

- Sign up / log in with email + password (bcrypt-hashed, session cookie via
  `SESSION_SECRET`).
- Starting a negotiation sends your free-text scenario description + a
  category hint to the Anthropic API (`claude-sonnet-5`) once, to generate a
  hidden persona (target number, walk-away number, personality trait). It's
  kept server-side only, stored in Postgres alongside the negotiation.
- Each chat turn sends the full hidden persona + conversation history as the
  system prompt, instructing the model to negotiate like a skilled,
  disciplined counterpart — anchor near its target, concede slowly and only
  with justification, and hold firm rather than always caving.
- "End Negotiation" reveals the stored numbers and asks the model for an
  honest debrief (not automatically flattering) based on the transcript.
- All negotiations (transcript + reveal) persist per-user and are viewable
  under "History".
