"""MongoDB: messages and memories (database `memomate`).

Includes automatic fallback to local JSON database when campus Wi-Fi blocks port 27017.
"""
import json
import math
import os
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

load_dotenv()

LOCAL_DB_FILE = os.path.join(os.path.dirname(__file__), "memomate_local.json")
_db_instance = None
_db_mode = "atlas"  # "atlas" or "offline"


def now():
    return datetime.now(timezone.utc)


class _LocalCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        sort_key = key
        sort_dir = direction
        if isinstance(key, list) and key:
            sort_key = key[0][0]
            sort_dir = key[0][1] if len(key[0]) > 1 else 1

        def _get_sort_val(doc):
            val = doc.get(sort_key)
            if isinstance(val, datetime):
                return val.timestamp()
            return val or 0

        self._docs.sort(key=_get_sort_val, reverse=(sort_dir == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)

    def __getitem__(self, item):
        return self._docs[item]


class _InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _LocalCollection:
    def __init__(self, collection_name):
        self.name = collection_name

    def _read_all(self):
        if not os.path.exists(LOCAL_DB_FILE):
            return []
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get(self.name, [])
                for doc in items:
                    for k in ("created_at", "updated_at", "expires_at"):
                        if doc.get(k) and isinstance(doc[k], str):
                            try:
                                doc[k] = datetime.fromisoformat(doc[k])
                            except Exception:
                                pass
                return items
        except Exception:
            return []

    def _write_all(self, items):
        data = {}
        if os.path.exists(LOCAL_DB_FILE):
            try:
                with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        serializable = []
        for d in items:
            doc = dict(d)
            for k in ("created_at", "updated_at", "expires_at"):
                if isinstance(doc.get(k), datetime):
                    doc[k] = doc[k].isoformat()
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            serializable.append(doc)

        data[self.name] = serializable
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def create_index(self, *args, **kwargs):
        pass

    def create_search_index(self, *args, **kwargs):
        pass

    def insert_one(self, doc):
        items = self._read_all()
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = str(ObjectId())
        else:
            new_doc["_id"] = str(new_doc["_id"])
        items.append(new_doc)
        self._write_all(items)
        return _InsertResult(new_doc["_id"])

    def find(self, query, projection=None):
        items = self._read_all()
        matched = []
        current_time = now()
        for doc in items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for cond in v:
                        for cond_k, cond_v in cond.items():
                            if cond_k == "expires_at":
                                if cond_v is None and doc.get("expires_at") is None:
                                    or_match = True
                                elif isinstance(cond_v, dict) and "$gt" in cond_v:
                                    exp = doc.get("expires_at")
                                    if exp and isinstance(exp, datetime) and exp > current_time:
                                        or_match = True
                    if not or_match:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                res = dict(doc)
                if projection and "embedding" in projection and projection["embedding"] == 0:
                    res.pop("embedding", None)
                matched.append(res)
        return _LocalCursor(matched)

    def delete_one(self, query):
        items = self._read_all()
        user_id = query.get("user_id")
        mem_id = str(query.get("_id"))
        remaining = [
            d for d in items
            if not (d.get("user_id") == user_id and str(d.get("_id")) == mem_id)
        ]
        self._write_all(remaining)

    def update_one(self, query, update):
        items = self._read_all()
        user_id = query.get("user_id")
        mem_id = str(query.get("_id"))
        for d in items:
            if (user_id is None or d.get("user_id") == user_id) and str(d.get("_id")) == mem_id:
                if "$set" in update:
                    for k, v in update["$set"].items():
                        d[k] = v
                break
        self._write_all(items)


class _LocalMongoDB:
    def __init__(self):
        self.messages = _LocalCollection("messages")
        self.memories = _LocalCollection("memories")


def _db():
    global _db_instance, _db_mode
    if _db_instance is not None:
        return _db_instance

    uri = os.getenv("MONGODB_URI")
    if uri:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=2500, tz_aware=True)
            client.admin.command("ping")
            _db_mode = "atlas"
            _db_instance = client["memomate"]
            return _db_instance
        except Exception:
            pass

    # Automatic local offline database fallback
    _db_mode = "offline"
    _db_instance = _LocalMongoDB()
    return _db_instance


def connection_status():
    """Returns 'atlas' if connected to cloud cluster, or 'offline' if using local fallback."""
    _db()  # initialize if not done
    return _db_mode


def setup_indexes():
    """Safe to run every start."""
    try:
        _db().memories.create_index("expires_at", expireAfterSeconds=0)
        _db().messages.create_index([("user_id", 1), ("created_at", -1)])
        
        index_model = SearchIndexModel(
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": 1024,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "user_id"},
                    {"type": "filter", "path": "status"},
                    {"type": "filter", "path": "type"},
                ]
            },
            name="memory_vector_index",
            type="vectorSearch",
        )
        _db().memories.create_search_index(model=index_model)
    except Exception:
        pass


def save_message(user_id, role, content, memories_used=None):
    _db().messages.insert_one({
        "user_id": user_id,
        "role": role,
        "content": content,
        "memories_used": memories_used or [],
        "created_at": now(),
    })


def recent_messages(user_id, limit=20):
    """Last `limit` messages, oldest first."""
    docs = _db().messages.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return list(docs)[::-1]


def save_memory(user_id, mem, embedding, source, expires_at):
    return _db().memories.insert_one({
        "user_id": user_id,
        "type": mem["type"],
        "content": mem["content"],
        "embedding": embedding,
        "source": source,
        "status": "active",
        "replaced_by": None,
        "created_at": now(),
        "updated_at": now(),
        "expires_at": expires_at,
    }).inserted_id


def list_memories(user_id):
    """Active, not-yet-expired memories (without the big embedding array)."""
    query = {
        "user_id": user_id,
        "status": "active",
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now()}}],
    }
    return list(_db().memories.find(query, {"embedding": 0}).sort("created_at", -1))


def delete_memory(user_id, memory_id):
    _db().memories.delete_one({"_id": memory_id, "user_id": user_id})


def _cosine_similarity(vec1, vec2):
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _cosine_similarity_fallback(user_id, query_vector, limit=5):
    """In-memory cosine similarity fallback."""
    query = {
        "user_id": user_id,
        "status": "active",
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now()}}],
    }
    docs = list(_db().memories.find(query))
    scored = []
    for doc in docs:
        emb = doc.pop("embedding", None)
        if emb:
            doc["score"] = _cosine_similarity(query_vector, emb)
            scored.append(doc)
    scored.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return scored[:limit]


def vector_search_memories(user_id, query_vector, limit=5):
    """Retrieve top `limit` relevant active memories using MongoDB Atlas Vector Search.
    
    Falls back gracefully to in-memory cosine similarity if Atlas Search index is not yet ready or offline.
    """
    if _db_mode == "atlas":
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(50, limit * 10),
                    "limit": limit,
                    "filter": {
                        "user_id": {"$eq": user_id},
                        "status": {"$eq": "active"},
                    },
                }
            },
            {
                "$project": {
                    "embedding": 0,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        try:
            results = list(_db().memories.aggregate(pipeline))
            current = now()
            valid = [
                doc for doc in results
                if doc.get("expires_at") is None or doc["expires_at"] > current
            ]
            return valid
        except Exception:
            pass

    return _cosine_similarity_fallback(user_id, query_vector, limit)


def replace_memory(user_id, old_id, new_id):
    """Mark old memory as replaced by new memory (FR3)."""
    _db().memories.update_one(
        {"_id": old_id, "user_id": user_id},
        {"$set": {"status": "replaced", "replaced_by": new_id, "updated_at": now()}},
    )


def touch_memory(user_id, memory_id):
    """Refresh updated_at timestamp when duplicate is detected (FR3)."""
    _db().memories.update_one(
        {"_id": memory_id, "user_id": user_id},
        {"$set": {"updated_at": now()}},
    )


def find_similar_memories(user_id, query_vector, memory_type, limit=3):
    """Find top similar active memories of the same type for conflict checking (FR3)."""
    if _db_mode == "atlas":
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(30, limit * 10),
                    "limit": limit,
                    "filter": {
                        "user_id": {"$eq": user_id},
                        "status": {"$eq": "active"},
                        "type": {"$eq": memory_type},
                    },
                }
            },
            {
                "$project": {
                    "embedding": 0,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            results = list(_db().memories.aggregate(pipeline))
            current = now()
            return [
                doc for doc in results
                if doc.get("expires_at") is None or doc["expires_at"] > current
            ]
        except Exception:
            pass

    # Fallback in-memory
    query = {
        "user_id": user_id,
        "type": memory_type,
        "status": "active",
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now()}}],
    }
    docs = list(_db().memories.find(query))
    scored = []
    for doc in docs:
        emb = doc.pop("embedding", None)
        if emb:
            doc["score"] = _cosine_similarity(query_vector, emb)
            scored.append(doc)
    scored.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return scored[:limit]


def list_history(user_id):
    """List replaced memories for inspector history toggle (FR7)."""
    return list(_db().memories.find({"user_id": user_id, "status": "replaced"}, {"embedding": 0}).sort("updated_at", -1))

