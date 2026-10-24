"""Verification test for the MemoMate LangGraph Agent."""
from unittest.mock import patch

import agent
import db


def test_agent_graph_compilation():
    assert agent.memory_agent is not None
    print("[OK] LangGraph StateGraph compiled and instantiated")


def test_privacy_guard_node():
    state = {
        "user_id": "test_user",
        "history": [],
        "input_text": "My phone number is 9876543210 and my email is test@example.com.",
        "notices": [],
    }
    res = agent.privacy_guard_node(state)
    assert "[SENSITIVE DATA REDACTED]" in res["clean_text"]
    assert "[EMAIL REDACTED]" in res["clean_text"]
    assert any("Privacy Guard" in n for n in res["notices"])
    print("[OK] test_privacy_guard_node: Redacted phone & email successfully")


def test_intent_routing():
    forget_state = {"input_text": "Please forget my DBMS exam"}
    chat_state = {"input_text": "I had pasta for dinner"}
    assert agent.route_intent(forget_state) == "forget_node"
    assert agent.route_intent(chat_state) == "memory_extractor_node"
    print("[OK] test_intent_routing: Correctly routed forget vs memory pipeline")


def test_end_to_end_agent_flow():
    user = "langgraph_demo_user"
    # Clean previous demo memories
    for m in db.list_memories(user):
        db.delete_memory(user, m["_id"])

    with patch.object(agent.brain, "extract_memories", return_value=[{"type": "preference", "content": "Studies best late at night"}]), \
         patch.object(agent.brain, "reply", side_effect=[
             "Great, keep your deep work block at night.",
             "Here is your schedule with a late-night focus block.",
         ]):
        # Turn 1: Save preference
        turn1 = agent.memory_agent.invoke({
            "user_id": user,
            "history": [],
            "input_text": "I study best late at night.",
            "notices": [],
        })
        assert turn1["final_response"]
        mems1 = db.list_memories(user)
        assert len(mems1) >= 1
        print(f"[OK] Turn 1 completed: Memory saved -> {[m['content'] for m in mems1]}")

        # Turn 2: Recall & Planning
        turn2 = agent.memory_agent.invoke({
            "user_id": user,
            "history": [{"role": "user", "content": "I study best late at night."}, {"role": "assistant", "content": turn1["final_response"]}],
            "input_text": "Plan my schedule for tomorrow.",
            "notices": [],
        })
        assert len(turn2["recalled_memories"]) >= 1
        print(f"[OK] Turn 2 completed: Recalled memories -> {[m['content'] for m in turn2['recalled_memories']]}")

    # Turn 3: Forget command
    turn3 = agent.memory_agent.invoke({
        "user_id": user,
        "history": [],
        "input_text": "Forget that I study late at night.",
        "notices": [],
    })
    mems3 = db.list_memories(user)
    assert len(mems3) == 0
    print("[OK] Turn 3 completed: Forget node successfully removed target memory")


if __name__ == "__main__":
    test_agent_graph_compilation()
    test_privacy_guard_node()
    test_intent_routing()
    test_end_to_end_agent_flow()
    print("\n>>> ALL LANGGRAPH AGENT TESTS PASSED! <<<")
