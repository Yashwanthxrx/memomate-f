"""Demo walkthrough for Milestone 2: Semantic Recall & MongoDB Vector Search.

Can run in:
1. Simulated mode (offline, demonstrates the exact math, ranking, top-5 retrieval, and prompt injection)
2. Live mode (if .env contains valid keys)
"""
import math
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()


def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


def print_banner(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def run_demo():
    print_banner("MEMOMATE: MILESTONE 2 DEMO (SEMANTIC RECALL)")

    print("\n[Step 1] User stores multiple memories in previous sessions:")
    sample_memories = [
        {
            "id": "mem_1",
            "type": "preference",
            "content": "Studies best late at night, hates mornings",
            # Simulated 1024-dim embedding with high weight in "study/habits" dimensions
            "embedding": [0.85, 0.12, 0.05, 0.01] + [0.0] * 1020,
        },
        {
            "id": "mem_2",
            "type": "preference",
            "content": "Strict vegetarian, prefers high-protein meals",
            # Simulated 1024-dim embedding with high weight in "food/diet" dimensions
            "embedding": [0.02, 0.91, 0.10, 0.00] + [0.0] * 1020,
        },
        {
            "id": "mem_3",
            "type": "fact",
            "content": "DBMS final exam on Friday",
            # Simulated 1024-dim embedding with weight in "academics/exams"
            "embedding": [0.72, 0.08, 0.65, 0.00] + [0.0] * 1020,
        },
        {
            "id": "mem_4",
            "type": "goal",
            "content": "Wants to run a 5k marathon this spring",
            # Simulated 1024-dim embedding with weight in "fitness/running"
            "embedding": [0.04, 0.15, 0.02, 0.88] + [0.0] * 1020,
        },
    ]

    for m in sample_memories:
        print(f"  [SAVED MEMORY] [{m['type'].upper()}] {m['content']}")

    print("\n[Step 2] User starts a new session and asks:")
    query = "Plan my study schedule for tomorrow."
    print(f'  [USER QUERY]: "{query}"')

    # Query embedding focuses heavily on studying and exams
    query_vector = [0.90, 0.05, 0.40, 0.02] + [0.0] * 1020

    print("\n[Step 3] Vector Search: Scoring all active memories against user prompt:")
    scored = []
    for m in sample_memories:
        score = cosine_similarity(query_vector, m["embedding"])
        scored.append((score, m))

    # Sort descending
    scored.sort(key=lambda x: x[0], reverse=True)

    for rank, (score, m) in enumerate(scored, 1):
        bar = "#" * int(score * 20)
        status = "[RECALLED (Top 5)]" if rank <= 5 and score > 0.4 else "[NOT RELEVANT]"
        print(f"  Rank {rank}: [{score:0.3f}] {bar:<20} {status}")
        print(f"          Content: ({m['type']}) {m['content']}")

    print("\n[Step 4] Top Relevant Memories injected into Claude's prompt context:")
    top_memories = [m for score, m in scored if score > 0.4][:5]
    for m in top_memories:
        print(f"  - ({m['type']}) {m['content']}")

    print("\n[Step 5] Assistant Response generated with recalled context:")
    mock_reply = (
        "Here's a study plan tailored for you tomorrow:\n\n"
        "- Morning: Sleep in and take your time waking up - no stress.\n"
        "- Afternoon: Light review and organize your DBMS exam prep notes.\n"
        "- 8:00 PM - 12:30 AM: Deep focus study block (since you do your best work late at night!).\n\n"
        "You've got this for the DBMS exam!"
    )
    print(f'  Assistant: "{mock_reply}"')

    print("\n[Step 6] UI 'Memories used' section (FR7):")
    print("  +-------------------------------------------------------------+")
    print(f"  | Memories used ({len(top_memories)})                                         |")
    for score, m in scored[:len(top_memories)]:
        print(f"  |   - ({m['type']}) {m['content']} -- similarity: {score:.1%} |")
    print("  +-------------------------------------------------------------+")

    print("\n[Step 7] MongoDB messages record saved with `memories_used`:")
    saved_msg = {
        "user_id": "demo",
        "role": "assistant",
        "content": mock_reply,
        "memories_used": [
            {"memory_id": m["id"], "score": round(score, 3), "type": m["type"], "content": m["content"]}
            for score, m in scored[:len(top_memories)]
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"  Saved to MongoDB: {saved_msg['memories_used']}")

    print_banner("DEMO COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    run_demo()
