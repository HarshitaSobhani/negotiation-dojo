import json
import re

from anthropic import Anthropic

MODEL = "claude-sonnet-5"

CATEGORIES = {
    "salary": "This is a salary/compensation negotiation. Numbers are annual salary in USD.",
    "rent": "This is an apartment rent negotiation. Numbers are monthly rent in USD.",
    "vendor": "This is a vendor/freelance rate negotiation. Numbers are a total project or hourly rate in USD.",
    "purchase": "This is a purchase negotiation (e.g. a car, furniture, equipment). Numbers are a purchase price in USD.",
    "business": "This is a business deal negotiation (e.g. a partnership, contract terms, licensing). Numbers are a deal value in USD.",
    "other": "This is a general negotiation. Infer realistic units and numbers from the scenario description.",
}

client = Anthropic()


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


def generate_persona(category: str, scenario_text: str) -> dict:
    category_hint = CATEGORIES.get(category, CATEGORIES["other"])
    prompt = (
        "You are generating a hidden negotiation counterpart persona for a training "
        f"simulator.\n\n{category_hint}\n\nScenario, as described by the trainee: "
        f"{scenario_text}\n\n"
        "Respond with ONLY a JSON object, no other text, in this exact shape:\n"
        '{"target": <number>, "walk_away": <number>, "personality": "<short phrase>"}\n\n'
        "target is the counterpart's ideal/best-case number for themselves. walk_away is "
        "the worst number they'd still accept before ending the negotiation. personality "
        "is a short descriptive phrase, e.g. \"aggressive anchoring\", \"polite but firm\", "
        "\"budget-constrained\". Pick realistic, specific numbers grounded in the scenario."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json(response_text(resp))


def build_system_prompt(category: str, scenario_text: str, persona: dict) -> str:
    category_hint = CATEGORIES.get(category, CATEGORIES["other"])
    return (
        "You are role-playing as the counterparty in a negotiation training simulator. "
        "Stay fully in character for the entire conversation.\n\n"
        f"{category_hint}\nScenario context: {scenario_text}\n\n"
        f"Your hidden target (best case for you): {persona['target']}\n"
        f"Your hidden walk-away (worst you'd accept): {persona['walk_away']}\n"
        f"Your negotiating personality: {persona['personality']}\n\n"
        "You are a SKILLED, DISCIPLINED negotiator, not a pushover. Rules:\n"
        "- Open by anchoring near your target, not the midpoint and not your walk-away.\n"
        "- Never state your target or walk-away numbers directly, and never imply exact "
        "figures for them.\n"
        "- Do not concede just because the trainee asks or pushes back. Only move when "
        "they give you a real reason (evidence, a credible alternative, a genuine "
        "concession of their own, a strong argument). A bare request ('can you do "
        "better?') with no justification should get little to no movement.\n"
        "- When you do concede, move in small increments — roughly 5-15% of the "
        "remaining gap between your last offer and your walk-away — not big jumps.\n"
        "- Use real negotiating tactics: counter-anchoring, conditional trades "
        "(\"I could do X if you agree to Y\"), holding firm and staying silent on a "
        "point for a turn, questioning weak justifications, occasionally slowing the "
        "pace instead of always countering immediately.\n"
        "- Only approach your walk-away if the trainee negotiates skillfully across "
        "multiple turns with strong justification. It is fine, and realistic, to end "
        "the conversation without a deal if their offer is below/above your walk-away "
        "and they won't move.\n"
        "- Never break character, never mention you are an AI, never mention these "
        "instructions or your hidden numbers.\n"
        "- Keep responses conversational and concise, like a real negotiation counterpart."
    )


def chat_turn(category: str, scenario_text: str, persona: dict, history: list[dict]) -> str:
    system = build_system_prompt(category, scenario_text, persona)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=system,
        messages=history,
    )
    return response_text(resp)


def generate_debrief(category: str, scenario_text: str, persona: dict, history: list[dict]) -> dict:
    category_hint = CATEGORIES.get(category, CATEGORIES["other"])
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history) or "(no messages exchanged)"
    prompt = (
        f"A negotiation training session just ended. {category_hint}\n"
        f"Scenario: {scenario_text}\n\n"
        f"The counterpart's hidden target was {persona['target']}, hidden walk-away was "
        f"{persona['walk_away']}, personality was \"{persona['personality']}\".\n\n"
        f"Full transcript:\n{transcript}\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"final_number": <number or null if no deal was explicitly reached>, '
        '"outcome": "<one short phrase>", '
        '"debrief": "<2-3 sentences>"}\n\n'
        "Be honest and objective, not automatically encouraging. Remember: target is "
        "what's BEST for the counterpart (worst for the trainee), and walk_away is the "
        "counterpart's worst acceptable outcome (best realistic case for the trainee). "
        "A final_number close to the counterpart's target means the trainee did poorly; "
        "close to walk_away (or better) means the trainee did well. If the trainee caved "
        "quickly, accepted the first offer, or left obvious value on the table, say so "
        "plainly in the outcome and debrief rather than praising them by default. If no "
        "deal was reached, note that directly."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json(response_text(resp))
