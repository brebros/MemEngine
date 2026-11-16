"""MemEngine — zero-dependency agent memory (SQLite + FTS5).

Banks of memories (fact | experience | observation | decision) in one SQLite
file. FTS5 recall with observation-first ranking, wikilink-style links +
backlinks, Jaccard duplicate guard, secret-filtering quality gate, dated
backups. Append-only: no silent overwrites.
"""
from memengine.db import SCHEMA, connect
from memengine.dedup import similar_exists
from memengine.quality import SECRET_PATTERNS, quality_gate

__version__ = "2.0.0"

__all__ = [
           "SCHEMA",
           "SECRET_PATTERNS",
           "__version__",
           "connect",
           "quality_gate",
           "similar_exists",
]
