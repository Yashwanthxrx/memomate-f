"""LangGraph Agent for MemoMate: Full Agentic Memory Workflow.

Implements the multi-step StateGraph:
[START] -> Privacy Guard -> Intent Router ->
    ├── (Forget Command) -> Forget Node -> [END]
    └── (Chat/Diary/Plan) -> Memory Extractor -> Conflict Resolver (FR3) ->
                             Semantic Recall (FR2) -> Response Generator -> [END]
"""
import re
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import brain
import db
from embeddings import embed


class AgentState(TypedDict):
    user_id: str
    history: List[Dict[str, str]]
    input_text: str
    clean_text: str
    is_forget: bool
    privacy_notices: List[str]
    extracted_memories: List[Dict[str, Any]]
    conflict_notices: List[str]
    recalled_memories: List[Dict[str, Any]]
    memories_used: List[Dict[str, Any]]
    final_response: str
    notices: List[str]


# --- Nodes ---

def privacy_guard_node(state: AgentState) -> Dict[str, Any]:
    """FR6: Privacy Guard - block passwords, phone numbers, digit sequences (6+), and emails."""
    text = state["input_text"]
    notices = list(state.get("notices", []))
    flagged = False

    # 1. Regex for phone numbers or 6+ digit numbers (passwords, bank accounts, ID numbers)
    digit_pattern = r"\b\d{6,}\b|\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    if re.search(digit_pattern, text):
        flagged = True
        text = re.sub(digit_pattern, "[SENSITIVE DATA REDACTED]", text)

    # 2. Regex for emails
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    if re.search(email_pattern, text):
        flagged = True
        text = re.sub(email_pattern, "[EMAIL REDACTED]", text)

    if flagged:
        notices.append("🛡️ Privacy Guard: Detected and blocked sensitive numbers/credentials.")

    return {
        "clean_text": text,
        "notices": notices,
    }


def route_intent(state: AgentState) -> str:
    """Route between Forget Flow (FR5) and Memory Pipeline (FR1/FR2/FR3)."""
    text = state["input_text"].lower().strip()
    if text.startswith("forget ") or "forget that i" in text or "forget my" in text or text.startswith("delete memory"):
        return "forget_node"
    return "memory_extractor_node"


def forget_node(state: AgentState) -> Dict[str, Any]:
    """FR5: Forget command - vector searches target memory and deletes it."""
    user_id = state["user_id"]
    text = state["input_text"].strip()
    notices = list(state.get("notices", []))

    # Strip prefixes like "forget ", "forget that ", "forget my "
    target_query = re.sub(r"^(?:please\s+)?(?:forget\s+(?:that\s+I\s+|my\s+|about\s+)?|delete\s+memory\s+)", "", text, flags=re.I).strip()
    if not target_query:
        target_query = text

    # Search for matching memory via vector search
    query_vec = embed(target_query, input_type="query")
    candidates = db.vector_search_memories(user_id, query_vec, limit=1)

    if candidates and candidates[0].get("score", 0.0) > 0.4:
        target = candidates[0]
        db.delete_memory(user_id, target["_id"])
        msg = f"I've permanently forgotten: **\"{target['content']}\"** (type: {target['type']})."
        notices.append(f"🗑️ Forgotten: {target['content']}")
    else:
        msg = f"I couldn't find a matching memory for \"{target_query}\" to forget."

    # Save to chat history
    db.save_message(user_id, "user", state["input_text"])
    db.save_message(user_id, "assistant", msg, memories_used=[])

    return {
        "final_response": msg,
        "notices": notices,
        "recalled_memories": [],
        "memories_used": [],
    }


def memory_extractor_node(state: AgentState) -> Dict[str, Any]:
    """FR1: Extract candidate memories from cleaned prompt."""
    text = state["clean_text"]
    try:
        found = brain.extract_memories(text)
    except Exception:
        found = []
    return {"extracted_memories": found}


def conflict_resolver_node(state: AgentState) -> Dict[str, Any]:
    """FR3: Conflict handling & updates (Key hard case).
    
    For each candidate memory:
    - Finds top 3 similar active memories of the same type via Vector Search.
    - LLM judges: 'replaces', 'duplicate', or 'unrelated'.
    - Updates history status or touches timestamp accordingly.
    """
    user_id = state["user_id"]
    candidates = state.get("extracted_memories", [])
    prompt = state["input_text"]
    notices = list(state.get("notices", []))

    for mem in candidates:
        try:
            vec = embed(mem["content"])
            expires_at = brain.expires_at(mem, db.now())
            similar_existing = db.find_similar_memories(user_id, vec, mem["type"], limit=3)
            
            resolved = False
            for old in similar_existing:
                # If similarity is significant, perform LLM conflict check
                if old.get("score", 0.0) > 0.55:
                    decision, reason = brain.judge_conflict(mem["content"], old["content"])
                    
                    if decision == "replaces":
                        # Save new active memory
                        new_id = db.save_memory(user_id, mem, vec, prompt, expires_at)
                        # Mark old memory as replaced
                        db.replace_memory(user_id, old["_id"], new_id)
                        notices.append(f"🔄 Updated {mem['type']}: \"{mem['content']}\" (replaces: \"{old['content']}\")")
                        resolved = True
                        break
                    elif decision == "duplicate":
                        # Do not insert; refresh timestamp
                        db.touch_memory(user_id, old["_id"])
                        notices.append(f"⚡ Duplicate detected: Refreshed timestamp for \"{old['content']}\"")
                        resolved = True
                        break

            if not resolved:
                # Unrelated or brand new memory
                db.save_memory(user_id, mem, vec, prompt, expires_at)
                notices.append(f"💾 Saved {mem['type']}: {mem['content']}")

        except Exception as e:
            notices.append(f"⚠️ Error processing memory \"{mem['content']}\": {e}")

    return {"notices": notices}


def semantic_recall_node(state: AgentState) -> Dict[str, Any]:
    """FR2: Semantic recall of top 5 relevant active memories using Vector Search."""
    user_id = state["user_id"]
    text = state["clean_text"]
    low = (text or "").lower().strip()

    is_smalltalk = bool(re.search(r"\b(hi|hello|hey|how are you|how r u|thanks|thank you)\b", low))
    is_mood_update = bool(re.search(r"\bi\s+(?:feel|am feeling|am)\s+\w+", low))
    planning_like = any(k in low for k in ["plan", "schedule", "routine", "today", "tomorrow", "week", "priorities"]) 

    try:
        query_vec = embed(text, input_type="query")
        recalled = db.vector_search_memories(user_id, query_vec, limit=5)
    except Exception:
        recalled = []

    # Guard against irrelevant carry-over memories on greetings/chitchat and direct mood updates.
    if recalled and (is_smalltalk or is_mood_update):
        if is_mood_update:
            recalled = [m for m in recalled if m.get("type") == "mood" and float(m.get("score", 0.0)) >= 0.45]
        else:
            recalled = [m for m in recalled if float(m.get("score", 0.0)) >= 0.75]

    # Degraded-mode fallback: if vector search is unavailable/empty, still provide context.
    if not recalled and planning_like:
        try:
            backup = db.list_memories(user_id)[:5]
            for m in backup:
                if "score" not in m:
                    m["score"] = 0.0
            recalled = backup
        except Exception:
            recalled = []

    return {"recalled_memories": recalled}


def response_generator_node(state: AgentState) -> Dict[str, Any]:
    """Generate contextual reply using recalled memories & save message."""
    user_id = state["user_id"]
    history = state.get("history", [])
    prompt = state["input_text"]
    recalled = state.get("recalled_memories", [])

    # Format memories_used for storage & UI
    memories_used = [
        {
            "memory_id": str(m["_id"]),
            "score": round(float(m.get("score", 0.0)), 3),
            "type": m.get("type"),
            "content": m.get("content"),
        }
        for m in recalled
    ]

    try:
        answer = brain.reply(history + [{"role": "user", "content": prompt}], recalled)
    except Exception as e:
        answer = f"I couldn't generate a response: {e}"

    # Save user message & assistant reply
    db.save_message(user_id, "user", prompt)
    db.save_message(user_id, "assistant", answer, memories_used=memories_used)

    return {
        "final_response": answer,
        "memories_used": memories_used,
    }


# --- Build StateGraph ---

def build_memory_agent():
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("privacy_guard_node", privacy_guard_node)
    workflow.add_node("forget_node", forget_node)
    workflow.add_node("memory_extractor_node", memory_extractor_node)
    workflow.add_node("conflict_resolver_node", conflict_resolver_node)
    workflow.add_node("semantic_recall_node", semantic_recall_node)
    workflow.add_node("response_generator_node", response_generator_node)

    # Define edges & conditional branches
    workflow.add_edge(START, "privacy_guard_node")
    workflow.add_conditional_edges(
        "privacy_guard_node",
        route_intent,
        {
            "forget_node": "forget_node",
            "memory_extractor_node": "memory_extractor_node",
        },
    )
    workflow.add_edge("forget_node", END)
    workflow.add_edge("memory_extractor_node", "conflict_resolver_node")
    workflow.add_edge("conflict_resolver_node", "semantic_recall_node")
    workflow.add_edge("semantic_recall_node", "response_generator_node")
    workflow.add_edge("response_generator_node", END)

    return workflow.compile()


memory_agent = build_memory_agent()


if __name__ == "__main__":
    print("[OK] LangGraph StateGraph compiled successfully!")
    print("\nAgent Graph Nodes:")
    for node in ["privacy_guard_node", "forget_node", "memory_extractor_node", "conflict_resolver_node", "semantic_recall_node", "response_generator_node"]:
        print(f"  • {node}")
