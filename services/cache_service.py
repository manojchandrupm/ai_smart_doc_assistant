import json
import hashlib
from core.redis_client import get_redis

CACHE_TTL = 3600

def _make_cache_key(user_id: str, question: str) -> str:
    """
    Build a stable, collision-resistant cache key.
    We hash the question so special chars / long text don't cause issues.

    Format:  qa_cache:<user_id>:<sha256_of_lowercased_question>
    """
    q_hash = hashlib.sha256(question.lower().strip().encode()).hexdigest()
    return f"qa_cache:{user_id}:{q_hash}"


def get_cached_answer(user_id: str, question: str) -> dict | None:
    """
    Returns the cached payload dict  { "answer": str, "sources": list }
    or None if there is no cache hit.
    """
    r = get_redis()
    key = _make_cache_key(user_id, question)
    raw = r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def set_cached_answer(user_id: str, question: str, answer: str, sources: list) -> None:
    """
    Stores the answer + sources in Redis with a TTL.
    Only cache successful, non-error answers.
    """
    r = get_redis()
    key = _make_cache_key(user_id, question)
    payload = json.dumps({"answer": answer, "sources": sources})
    r.setex(key, CACHE_TTL, payload)


def invalidate_user_cache(user_id: str) -> int:
    """
    Delete ALL cached answers for a given user (e.g. when they delete a document).
    Returns the number of keys deleted.
    """
    r = get_redis()
    pattern = f"qa_cache:{user_id}:*"
    keys = r.keys(pattern)
    if keys:
        return r.delete(*keys)
    return 0
