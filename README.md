# MemEngine

**Zero-dependency long-term memory for AI agents.** Hindsight-inspired concepts (retain / recall / observe, memory banks, memory types), rebuilt on pure Python stdlib — one file, one SQLite database, no Docker, no PostgreSQL, no LLM service.

Built for [Hermes Agent](https://github.com/nousresearch) setups, works with any agent that can run a CLI.

## Why

Agent memory systems like [Hindsight](https://github.com/vectorize-io/hindsight) are great but heavy: Docker, PostgreSQL, embedding models, an LLM service for extraction. If your agent runs on a small VPS and *the agent itself* is smart enough to extract its own facts, you don't need all that.

MemEngine keeps only what matters:

- **Append-only storage** — no silent overwrites; wrong entry? `delete` by explicit ID and re-add
- **Anti-duplicate writes** — token-overlap guard blocks near-identical entries
- **Observation-first recall** — distilled lessons (observations) always rank above raw experiences
- **Wikilinks + backlinks** — memories reference each other; ask "what points at this?"
- **Health check** — `stats` tells you when the agent stores experiences but never learns from them

## Install

```bash
git clone https://github.com/YOU/memengine.git
sudo ln -sf "$(pwd)/memengine/mem.py" /usr/local/bin/mem
```

Requirements: Python 3.11+ with SQLite FTS5 (ships with most builds). Nothing else.

Optional: `export MEMENGINE_DB=/path/to/mem.db` to relocate the database (default `/root/memengine/mem.db`).

## Memory types

| Type | Meaning | Written via |
|---|---|---|
| `fact` | stable data — addresses, URLs, config values | `add` |
| `experience` | something that happened (a failure, a fix, a surprise) | `add` |
| `decision` | an agreed plan or rule | `add` |
| `observation` | a distilled pattern learned from many experiences | `observe` only |

The intended learning flow:

```
experience ──(pattern repeats)──▶ observation ──(informs)──▶ decision
```

## Usage

```bash
# store
mem add myproject experience "Install script replaced all skills; had to restore from backup" --tags lesson,install
mem add myproject fact "RPC endpoint is https://rpc.example.live chainId 99901" --tags rpc

# recall — observations rank first automatically
mem recall myproject "install backup" --limit 5

# consolidate: distill repeated experiences into a lesson, auto-link to sources
mem observe myproject "Any install MUST be backed up first and verified after" --refs 6,7 --tags pattern

# link & inspect the network
mem link myproject 8 5
mem backlinks myproject 5        # what references memory #5?
mem graph myproject              # JSON nodes+edges dump (on demand)

# inspect
mem banks                        # list banks
mem stats myproject              # counts by type + learning health
mem list myproject --type decision

# hygiene
mem delete myproject 12          # explicit only; cleans links too
mem backup                       # dated snapshot in backups/<timestamp>/, keeps last 30
```

All output is JSON — trivially parseable from any agent or script.

## Design rules

1. **One source of truth** — a single SQLite file. No mirrors, no sync, nothing to overwrite.
2. **Append-only** — the CLI has no `update`. History is history.
3. **Quality over quantity** — the duplicate guard (≥82% token overlap) forces a decision on every near-duplicate. `--force` exists but should be rare.
4. **Observations are the goal** — `stats` reports `observation_ratio`; if experiences pile up with zero observations, the agent is storing but not learning.
5. **Backups are manual and dated** — never auto-clobbered, keep last 30.

## The agent skill

MemEngine is designed to be paired with an agent-side skill that defines *when* to store what (quality bar, the experience→observation→decision flow, when to recall before deciding). See `skill/SKILL.md` in this repo for a ready-to-adopt example — drop it into your agent's skills directory.

## What it deliberately does NOT have

- ❌ Docker / PostgreSQL / pgvector — SQLite + FTS5 covers single-agent scale
- ❌ Embedding models / LLM extraction — the calling agent does extraction; recall is full-text (BM25)
- ❌ Vault/markdown mirroring — two storage locations means one will drift
- ❌ Auto-crons — backups are a command, run when you decide

## License

MIT
