"""Self-check and verification test for Milestone 2: Semantic Recall & Vector Search."""
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import db


def test_cosine_similarity():
    # Identical vectors -> 1.0
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert math.isclose(db._cosine_similarity(v1, v2), 1.0, rel_tol=1e-5), "Identical vectors should have similarity 1.0"

    # Orthogonal vectors -> 0.0
    v3 = [0.0, 1.0, 0.0]
    assert math.isclose(db._cosine_similarity(v1, v3), 0.0, abs_tol=1e-5), "Orthogonal vectors should have similarity 0.0"

    # Opposite vectors -> -1.0
    v4 = [-1.0, 0.0, 0.0]
    assert math.isclose(db._cosine_similarity(v1, v4), -1.0, rel_tol=1e-5), "Opposite vectors should have similarity -1.0"

    print("[OK] test_cosine_similarity passed")


def test_vector_search_fallback_and_ranking():
    now_utc = datetime.now(timezone.utc)
    mock_memories = [
        {
            "_id": "mem_study_night",
            "user_id": "alice",
            "type": "preference",
            "content": "Studies best late at night",
            "embedding": [0.9, 0.1, 0.0],
            "status": "active",
            "expires_at": None,
        },
        {
            "_id": "mem_vegetarian",
            "user_id": "alice",
            "type": "preference",
            "content": "Prefers vegetarian food",
            "embedding": [0.1, 0.9, 0.0],
            "status": "active",
            "expires_at": None,
        },
        {
            "_id": "mem_exam",
            "user_id": "alice",
            "type": "fact",
            "content": "DBMS exam coming up",
            "embedding": [0.8, 0.3, 0.1],
            "status": "active",
            "expires_at": now_utc + timedelta(days=2),
        },
        {
            "_id": "mem_expired",
            "user_id": "alice",
            "type": "mood",
            "content": "Felt stressed yesterday",
            "embedding": [0.85, 0.2, 0.0],
            "status": "active",
            "expires_at": now_utc - timedelta(days=1),  # Expired!
        },
    ]

    mock_collection = MagicMock()
    # Mock find to return non-expired active docs
    def mock_find(query):
        # Return docs that match user and not expired
        res = [
            dict(m) for m in mock_memories 
            if m.get("expires_at") is None or m["expires_at"] > now_utc
        ]
        return res

    mock_collection.find.side_effect = mock_find

    with patch.object(db, "_db") as mock_db_fn:
        mock_db = MagicMock()
        mock_db.memories = mock_collection
        mock_db_fn.return_value = mock_db

        # Query vector close to study / exam: [1.0, 0.0, 0.0]
        query_vec = [1.0, 0.0, 0.0]
        results = db._cosine_similarity_fallback("alice", query_vec, limit=2)

        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        assert results[0]["_id"] == "mem_study_night", "Top memory should be study preference"
        assert results[0]["score"] > results[1]["score"], "Results must be sorted descending by score"
        assert all(r["_id"] != "mem_expired" for r in results), "Expired memories must not appear"

        print(f"[OK] test_vector_search_fallback passed (Top: {results[0]['content']} with score {results[0]['score']:.3f})")


def test_vector_search_memories_atlas_pipeline():
    # Test that vector_search_memories calls aggregate with the correct Atlas Vector Search pipeline
    mock_collection = MagicMock()
    mock_collection.aggregate.return_value = [
        {"_id": "1", "content": "Studies at night", "type": "preference", "score": 0.94, "expires_at": None}
    ]

    with patch.object(db, "_db") as mock_db_fn:
        mock_db = MagicMock()
        mock_db.memories = mock_collection
        mock_db_fn.return_value = mock_db

        query_vec = [0.1] * 1024
        results = db.vector_search_memories("alice", query_vec, limit=5)

        assert len(results) == 1
        assert results[0]["score"] == 0.94
        
        # Verify aggregate call args
        args, kwargs = mock_collection.aggregate.call_args
        pipeline = args[0]
        assert "$vectorSearch" in pipeline[0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["index"] == "memory_vector_index"
        assert vs["path"] == "embedding"
        assert vs["limit"] == 5
        assert vs["filter"]["user_id"]["$eq"] == "alice"
        assert vs["filter"]["status"]["$eq"] == "active"
        assert pipeline[1]["$project"]["score"] == {"$meta": "vectorSearchScore"}

        print("[OK] test_vector_search_memories_atlas_pipeline passed")


if __name__ == "__main__":
    test_cosine_similarity()
    test_vector_search_fallback_and_ranking()
    test_vector_search_memories_atlas_pipeline()
    print("\n>>> ALL MILESTONE 2 TESTS PASSED! <<<")
