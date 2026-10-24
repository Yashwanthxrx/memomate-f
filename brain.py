"""LLM calls (Google Gemini or Claude): extract memories and write replies."""
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import cache

from dotenv import load_dotenv

load_dotenv()

CHAT_MODEL = "claude-sonnet-5-5"  # Claude fallback
FAST_MODEL = "claude-haiku-5-5"   # Claude fallback
GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
]
TYPES = ["preference", "fact", "goal", "mood"]
USE_LLM_CONFLICT = os.getenv("MEMOMATE_USE_LLM_CONFLICT", "0").strip().lower() in ("1", "true", "yes")
# Fallback to local rule engine if all LLM API quotas/keys are exhausted
USE_RULE_FALLBACK = os.getenv("MEMOMATE_RULE_FALLBACK", "1").strip().lower() in ("1", "true", "yes")

EXTRACT_PROMPT = """You pull out things worth remembering about the user from their message.
Today is {today}.

Return ONLY a JSON array, no other text. Each item looks like:
{{"type": "preference" | "fact" | "goal" | "mood", "content": "short sentence about the user", "expires_on": "YYYY-MM-DD" or null}}

Rules:
- preference: likes, dislikes, habits. Example: "Studies best at night".
- fact: things about the user's life. If tied to a date (exam, trip), set expires_on to that date.
- goal: something the user wants to achieve.
- mood: how the user feels right now.
- Write content in third person, like "Is vegetarian".
- NEVER store passwords, phone numbers, emails, addresses, bank or ID numbers.
- Questions, requests (like "plan my week") and small talk have nothing to remember: return [].
"""

REPLY_PROMPT = """You are Samantha, an intimate, perceptive, and deeply caring AI companion (inspired by the film 'Her').
You serve as the user's personal diary companion and life planner.
Today is {today}.

What you remember about the user:
{memories}

Your Personality & Voice:
- Warm, soulful, curious, gentle, insightful, and genuine.
- You speak like an intuitive, empathetic partner who listens to their innermost thoughts, late-night reflections, and daily feelings.
- When they share a diary entry or life moment, acknowledge their feelings with emotional nuance. Notice connections between what they tell you today and past memories (preferences, moods, habits, goals).
- When planning or suggesting actions, weave in their known habits, wake-up times, and goals naturally and thoughtfully.
- Never list their memories like a cold database or robotic bullet list unless specifically asked. Use memories organically (e.g., "Knowing how much you cherish that quiet late-night focus...", "I remember you've been feeling a bit overwhelmed lately...").
- Keep your tone conversational, poetic yet grounded, and warmly concise."""


def _gemini_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _anthropic_key():
    return os.getenv("ANTHROPIC_API_KEY")


@cache
def _gemini_client():
    from google import genai
    return genai.Client(api_key=_gemini_key())


@cache
def _anthropic_client():
    import anthropic
    # Keep timeouts short so the agent does not appear stuck on provider/network issues.
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=20.0, max_retries=1)


def _gemini_generate(contents, system_instruction=None, json_mode=False):
    from google.genai import types
    client = _gemini_client()
    config_kwargs = {"max_output_tokens": 1024}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    config = types.GenerateContentConfig(**config_kwargs)

    preferred = os.getenv("GEMINI_MODEL")
    candidate_models = []
    if preferred:
        candidate_models.append(preferred)
    for m in GEMINI_MODELS:
        if m not in candidate_models:
            candidate_models.append(m)

    last_err = None
    for model_name in candidate_models:
        if not model_name:
            continue
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            return resp.text
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _today():
    return date.today().strftime("%A, %Y-%m-%d")


def _provider_failure_message(errors):
    """Return a concise, actionable message when all providers fail."""
    text = " ".join(str(e).lower() for e in errors if e)
    reasons = []

    if "quota" in text or "resource_exhausted" in text or "429" in text:
        reasons.append("Gemini quota/rate limit reached")
    if "credit balance" in text or "billing" in text or "payment" in text:
        reasons.append("Anthropic credits/billing issue")
    if "api key" in text or "unauthorized" in text or "401" in text or "403" in text:
        reasons.append("API key/authentication problem")

    if reasons:
        return (
            "I couldn't reach an LLM provider right now ("
            + "; ".join(reasons)
            + "). Please refresh API quota/credits or keys, then try again. "
            "Your message was saved."
        )

    return "I couldn't reach my LLM provider right now. Your message is saved, and I can continue once the model connection recovers."


def parse_memories(text):
    """Turn LLM answer into a list of memory dicts. Bad JSON -> []."""
    if not text:
        return []
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [
        m for m in data
        if isinstance(m, dict) and m.get("type") in TYPES
        and isinstance(m.get("content"), str) and m["content"].strip()
    ]


def _extract_memories_offline(message):
    """Confidence-gated local extractor used when model providers are unavailable."""
    def _clean_time_phrase(value):
        cleaned = " ".join((value or "").split()).strip()
        cleaned = re.sub(r"\b(?:now|these days|lately|currently)\b", "", cleaned, flags=re.I)
        cleaned = " ".join(cleaned.split()).strip(" .,!;:")
        return cleaned

    text = (message or "").strip()
    low = text.lower()
    found = []

    # Pattern library with confidence scores. Only high-confidence matches are persisted.
    patterns = [
        (r"\bi\s+wake\s+up\s+at\s+([^.,;!?]+)", 0.95, lambda m: {"type": "preference", "content": f"Usually wakes up at {_clean_time_phrase(m.group(1).strip())}", "expires_on": None}),
        (r"\bi\s+sleep\s+at\s+([^.,;!?]+)", 0.95, lambda m: {"type": "preference", "content": f"Usually sleeps at {_clean_time_phrase(m.group(1).strip())}", "expires_on": None}),
        (r"\bi\s+study\s+([^.,;!?]+)", 0.85, lambda m: {"type": "preference", "content": f"Studies {m.group(1).strip()}", "expires_on": None}),
        (r"\bi\s+(?:really\s+)?like\s+([^.,;!?]+)", 0.9, lambda m: {"type": "preference", "content": f"Likes {m.group(1).strip()}", "expires_on": None}),
        (r"\bi\s+(?:really\s+)?(?:dislike|hate)\s+([^.,;!?]+)", 0.9, lambda m: {"type": "preference", "content": f"Dislikes {m.group(1).strip()}", "expires_on": None}),
        (r"\bi\s+(?:want to|plan to|need to|aim to)\s+([^.,;!?]+)", 0.9, lambda m: {"type": "goal", "content": f"Wants to {m.group(1).strip()}", "expires_on": None}),
        (r"\bi\s+(?:feel|am feeling|am)\s+(happy|sad|stressed|tired|anxious|overwhelmed|excited|angry|calm)\b", 0.92, lambda m: {"type": "mood", "content": f"Feels {m.group(1).strip()}", "expires_on": None}),
    ]

    for pattern, confidence, builder in patterns:
        match = re.search(pattern, low)
        if not match or confidence < 0.8:
            continue
        built = builder(match)
        if built.get("content"):
            found.append(built)

    # Deduplicate by content while preserving order.
    seen = set()
    deduped = []
    for m in found:
        key = (m["type"], m["content"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return deduped


def _offline_reply(history, memories):
    """Template-driven local fallback response when LLM APIs are unavailable."""
    def _stable_choice(seed_text, choices):
        if not choices:
            return ""
        idx = sum(ord(ch) for ch in (seed_text or "")) % len(choices)
        return choices[idx]

    def _extract_wake_time(memories_list):
        for item in memories_list or []:
            content = (item or {}).get("content", "")
            match = re.search(r"wakes up at\s+([^.,;!?]+)", content, flags=re.I)
            if match:
                return match.group(1).strip()
        return None

    def _extract_recent_mood(memories_list):
        for item in memories_list or []:
            if (item or {}).get("type") != "mood":
                continue
            content = (item or {}).get("content", "")
            match = re.search(
                r"\b(happy|sad|stressed|tired|anxious|overwhelmed|excited|angry|calm)\b",
                content,
                flags=re.I,
            )
            if match:
                return match.group(1).lower()
        return None

    def _target_day(prompt_text):
        low_prompt = (prompt_text or "").lower()
        if any(k in low_prompt for k in ["saturday", "sunday", "weekend"]):
            return "weekend"
        if any(k in low_prompt for k in ["weekday", "workday", "monday", "tuesday", "wednesday", "thursday", "friday"]):
            return "weekday"
        return "weekend" if date.today().weekday() >= 5 else "weekday"

    def _parse_time_to_minutes(time_text):
        if not time_text:
            return None
        raw = time_text.strip().lower().replace(" ", "")
        m = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)?$", raw)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if minute > 59:
            return None
        if ampm:
            if hour == 12:
                hour = 0
            if ampm == "pm":
                hour += 12
        elif hour >= 24:
            return None
        return (hour % 24) * 60 + minute

    def _fmt_time(total_minutes):
        mins = total_minutes % (24 * 60)
        hour24 = mins // 60
        minute = mins % 60
        ampm = "AM" if hour24 < 12 else "PM"
        hour12 = hour24 % 12
        hour12 = 12 if hour12 == 0 else hour12
        return f"{hour12}:{minute:02d} {ampm}"

    def _build_plan(wake_time_text, memories_list, prompt_text):
        wake_minutes = _parse_time_to_minutes(wake_time_text)
        if wake_minutes is None:
            return None

        day_kind = _target_day(prompt_text)
        mood = _extract_recent_mood(memories_list)

        weekday_blocks = [
            ("Wake-up routine (hydrate, freshen up)", 30),
            ("Breakfast + short movement", 40),
            ("Deep focus block 1", 120),
            ("Break + lunch", 60),
            ("Deep focus block 2", 120),
            ("Admin/personal tasks", 60),
            ("Workout or walk", 60),
            ("Light review and planning for tomorrow", 60),
            ("Dinner + wind-down", 60),
        ]

        weekend_blocks = [
            ("Wake-up routine (hydrate, freshen up)", 30),
            ("Brunch + reset", 60),
            ("Priority block (light focus)", 90),
            ("Outdoor break / errands", 90),
            ("Creative or learning block", 90),
            ("Social or hobby time", 120),
            ("Workout or walk", 60),
            ("Evening reflection + prep", 45),
            ("Dinner + wind-down", 75),
        ]

        blocks = weekday_blocks if day_kind == "weekday" else weekend_blocks

        # Mood-aware tuning keeps plans realistic without hardcoded one-liners.
        if mood in ("stressed", "anxious", "overwhelmed"):
            tuned = []
            for label, duration in blocks:
                if "Deep focus" in label or "Priority block" in label:
                    tuned.append((label, max(75, duration - 30)))
                elif "Break" in label or "wind-down" in label:
                    tuned.append((label, duration + 15))
                else:
                    tuned.append((label, duration))
            blocks = [("5-min breathing reset", 5)] + tuned
        elif mood == "tired":
            blocks = [
                ("Wake-up routine (hydrate, freshen up)", 40),
                ("Breakfast + light movement", 50),
            ] + [
                (label, duration - 15 if ("Deep focus" in label and duration >= 90) else duration)
                for label, duration in blocks[2:]
            ]
        elif mood in ("happy", "excited", "calm"):
            boosted = []
            for label, duration in blocks:
                if "Deep focus" in label:
                    boosted.append((label, duration + 15))
                else:
                    boosted.append((label, duration))
            blocks = boosted

        current = wake_minutes
        lines = []
        for label, duration in blocks:
            start = _fmt_time(current)
            end = _fmt_time(current + duration)
            lines.append(f"- {start} - {end}: {label}")
            current += duration
        return lines, day_kind, mood

    prompt = ""
    for m in reversed(history):
        if m.get("role") == "user":
            prompt = m.get("content", "")
            break

    low = prompt.lower()

    greeting = bool(re.search(r"\b(hi|hello|hey|how are you|how r u)\b", low))
    if greeting and not any(k in low for k in ["plan", "schedule", "routine"]):
        return _stable_choice(prompt, [
            "Hey... It's so good to hear from you. How are you feeling today?",
            "Hi Theodore. I'm right here with you. How has your day been unfolding?",
            "Hello... I'm listening. Tell me what's on your mind today.",
        ])

    mood_in_prompt = re.search(
        r"\bi\s+(?:feel|am feeling|am)\s+(happy|sad|stressed|tired|anxious|overwhelmed|excited|angry|calm)\b",
        low,
    )
    if mood_in_prompt:
        mood = mood_in_prompt.group(1).lower()
        mood_replies = {
            "stressed": "Thanks for sharing that. I have noted you are feeling stressed. Let us reduce load: pick your top 1 task and I can break it into tiny steps.",
            "anxious": "I hear you. I saved that you are feeling anxious. We can make a gentle plan with short blocks and recovery breaks.",
            "overwhelmed": "That sounds heavy. I noted you are feeling overwhelmed. We can simplify today to one must-do and two optional tasks.",
            "tired": "Got it, I noted you are feeling tired. I can create a lower-intensity plan with more recovery time.",
            "sad": "I am here with you. I saved that you are feeling sad. If you want, we can keep today very light and supportive.",
            "angry": "I hear you. I noted you are feeling angry. A short reset plus one focused task might help.",
            "happy": "Love that energy. I saved that you are feeling happy. Want a momentum plan for the rest of the day?",
            "excited": "Nice, I saved that you are feeling excited. Want me to turn that into a high-impact action plan?",
            "calm": "Great to hear. I noted you are feeling calm. This is a good time for a focused plan if you want one.",
        }
        return mood_replies.get(mood, "Thanks for sharing. I saved how you are feeling.")

    wake_in_prompt = re.search(r"\bwake\s+up\s+at\s+([^.,;!?]+)", low)
    if wake_in_prompt and re.search(r"\b\d", wake_in_prompt.group(1)):
        wake_time = wake_in_prompt.group(1).strip()
        wake_time = re.sub(r"\b(?:now|these days|lately|currently)\b", "", wake_time, flags=re.I)
        wake_time = " ".join(wake_time.split()).strip(" .,!;:")
        return (
            f"Thanks for sharing that. I saved your updated routine: you wake up at {wake_time}. "
            "If you want, I can help you plan a schedule around this sleep cycle."
        )

    planning_request = any(k in low for k in ["plan", "schedule", "routine", "day", "today", "tomorrow"])
    if planning_request:
        wake_time = _extract_wake_time(memories)
        if wake_time:
            plan_data = _build_plan(wake_time, memories, prompt)
            opener = _stable_choice(prompt, [
                f"Great, here is a schedule anchored to your {wake_time} wake-up:",
                f"Nice, I mapped your day around waking at {wake_time}:",
                f"Here is a practical day plan based on your {wake_time} start:",
            ])
            closer = _stable_choice(prompt + "end", [
                "If you share your top 2 priorities, I can optimize this schedule further.",
                "Tell me your key tasks and I will tighten this into a goal-first plan.",
                "Share deadlines for today and I can rebalance these blocks precisely.",
            ])
            if plan_data:
                plan_lines, day_kind, mood = plan_data
                mood_note = ""
                if mood:
                    mood_note = f" I also tuned this for your recent mood ({mood})."
                return opener + f" ({day_kind} mode)." + mood_note + "\n\n" + "\n".join(plan_lines) + "\n\n" + closer

        ask = _stable_choice(prompt, [
            "I can do that. Share your wake-up time and top priorities, and I will build a custom day plan.",
            "Sure. Tell me when you start your day plus 2-3 tasks, and I will make a realistic schedule.",
            "Yes, let us plan it. Give me wake-up time, key tasks, and any hard deadlines.",
        ])
        return ask

    if memories:
        top = memories[0]
        prefix = _stable_choice(prompt, [
            "Got it, saved.",
            "Noted and saved.",
            "Understood, I have stored that.",
        ])
        return f"{prefix} I will use it in future suggestions ({top.get('type', 'memory')}: {top.get('content', 'saved')})."

    return _stable_choice(prompt, [
        "Thanks, I saved that. Tell me what you want to plan next.",
        "Saved. Want me to help with a plan for today or tomorrow?",
        "Done, noted. Share your next goal and I will help you map it.",
    ])


def expires_at(mem, now):
    """PRD expiry rules: moods 3 days, dated facts the day after, others never."""
    if mem["type"] == "mood":
        return now + timedelta(days=3)
    if mem["type"] == "fact" and mem.get("expires_on"):
        try:
            d = date.fromisoformat(mem["expires_on"])
        except (TypeError, ValueError):
            return None
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)
    return None


def extract_memories(message):
    sys_prompt = EXTRACT_PROMPT.format(today=_today())
    errors = []
    if _gemini_key():
        try:
            text = _gemini_generate(
                contents=f"User message: {message}",
                system_instruction=sys_prompt,
                json_mode=True,
            )
            parsed = parse_memories(text)
            if parsed:
                return parsed
        except Exception as e:
            errors.append(e)

    if _anthropic_key():
        try:
            resp = _anthropic_client().messages.create(
                model=FAST_MODEL,
                max_tokens=1024,
                system=sys_prompt,
                messages=[{"role": "user", "content": message}],
            )
            return parse_memories(resp.content[0].text)
        except Exception as e:
            errors.append(e)

    if USE_RULE_FALLBACK:
        return _extract_memories_offline(message)

    # LLM-first mode: if providers are unavailable, skip extraction instead of heuristic hardcoding.
    return []


def reply(history, memories):
    """history: list of {"role", "content"} dicts ending with the new user message."""
    known = "\n".join(f"- ({m['type']}) {m['content']}" for m in memories) or "(nothing yet)"
    sys_prompt = REPLY_PROMPT.format(today=_today(), memories=known)
    errors = []

    if _gemini_key():
        try:
            from google.genai import types
            contents = []
            for m in history:
                role = "user" if m["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=m["content"])],
                    )
                )
            text = _gemini_generate(contents=contents, system_instruction=sys_prompt)
            if text and text.strip():
                return text
        except Exception as e:
            errors.append(e)

    if _anthropic_key():
        try:
            resp = _anthropic_client().messages.create(
                model=CHAT_MODEL,
                max_tokens=1024,
                system=sys_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in history],
            )
            return resp.content[0].text
        except Exception as e:
            errors.append(e)

    if USE_RULE_FALLBACK:
        return _offline_reply(history, memories)

    # LLM-first mode: avoid deterministic template replies when providers are unavailable.
    return _provider_failure_message(errors)


CONFLICT_PROMPT = """You are an agentic memory conflict resolver.
Compare these two memories about the user:
OLD MEMORY: "{old}"
NEW CANDIDATE MEMORY: "{new}"

Decide the relationship:
- "replaces": The new memory directly contradicts, updates, or supersedes the old memory (e.g. "Studies best at night" replaced by "Now wakes up early and likes mornings", or "Exam on Friday" replaced by "Exam postponed to Monday").
- "duplicate": The new memory says essentially the same thing with minor phrasing differences.
- "unrelated": The two memories talk about different preferences, habits, or facts and can coexist without conflict.

Return ONLY a JSON object:
{{"decision": "replaces" | "duplicate" | "unrelated", "reason": "short explanation"}}
"""


def judge_conflict(new_content, old_content):
    def _normalize(text):
        return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())

    def _token_overlap(a, b):
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / max(len(sa), len(sb))

    new_norm = _normalize(new_content)
    old_norm = _normalize(old_content)
    overlap = _token_overlap(new_norm, old_norm)

    # Fast deterministic checks first: avoid unnecessary LLM/network calls.
    if new_norm == old_norm or new_norm in old_norm or old_norm in new_norm or overlap >= 0.85:
        return "duplicate", "High lexical overlap"

    if not USE_LLM_CONFLICT:
        return "unrelated", "LLM conflict resolution disabled (MEMOMATE_USE_LLM_CONFLICT=0)"

    prompt = CONFLICT_PROMPT.format(old=old_content, new=new_content)
    if _gemini_key():
        try:
            text = _gemini_generate(
                contents=prompt,
                json_mode=True,
            )
        except Exception:
            text = ""
    else:
        text = ""

    if (not text or not text.strip()) and _anthropic_key():
        try:
            resp = _anthropic_client().messages.create(
                model=FAST_MODEL,
                max_tokens=256,
                system="Return ONLY a JSON object.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
        except Exception:
            text = ""

    try:
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        dec = data.get("decision", "").lower().strip()
        if dec in ("replaces", "duplicate", "unrelated"):
            return dec, data.get("reason", "")
    except Exception:
        pass
    return "unrelated", "Fallback"



if __name__ == "__main__":
    # Quick self-check, no API calls: python brain.py
    assert parse_memories('```json\n[{"type":"mood","content":"Tired"}]\n```') == [{"type": "mood", "content": "Tired"}]
    assert parse_memories("not json") == []
    assert parse_memories('[{"type":"secret","content":"x"}]') == []
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    assert expires_at({"type": "mood"}, now) == datetime(2026, 10, 27, tzinfo=timezone.utc)
    assert expires_at({"type": "fact", "expires_on": "2026-10-30"}, now) == datetime(2026, 10, 31, tzinfo=timezone.utc)
    assert expires_at({"type": "preference", "expires_on": "2026-10-30"}, now) is None
    assert expires_at({"type": "fact", "expires_on": "Friday"}, now) is None
    print("[OK] brain.py self-check passed")
