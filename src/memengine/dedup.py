"""Duplicate guard: token-overlap (Jaccard) against same-bank memories."""


def similar_exists(con, bank: str, content: str,
                   threshold: float = 0.82) -> tuple[int | None, float]:
    """Return (similar_id, score) for the closest same-bank memory, or (None, 0.0)."""
    words = {w for w in content.lower().split() if len(w) > 3}
    if not words:
        return None, 0.0
    best, best_score = None, 0.0
    for mid, mcontent in con.execute(
            "SELECT id, content FROM memories WHERE bank=? ORDER BY id DESC LIMIT 500", (bank,)):
        mwords = {w for w in mcontent.lower().split() if len(w) > 3}
        if not mwords:
            continue
        score = len(words & mwords) / len(words | mwords)
        if score > best_score:
            best, best_score = mid, score
    if best is not None and best_score >= threshold:
        return best, best_score
    return best, best_score
