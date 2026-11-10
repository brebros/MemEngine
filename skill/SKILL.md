---
name: memengine
description: Use when saving or recalling long-term context in MemEngine.
---

# MemEngine — agent long-term memory

Our own build (Hindsight-inspired, zero deps). CLI `mem`, DB `/root/memengine/mem.db`, JSON output.

## Types — use the right one
- `fact` — stable data (contract addresses, RPC URLs, config values)
- `experience` — something that happened to us (a failure, a surprise, a fix)
- `decision` — an agreed plan with the operator (sell plans, pauses, rules)
- `observation` — NEVER via add; only via `observe` (see flow below)

## Flow: experience → observation → decision
1. Something happens worth remembering → `add <bank> experience "..." --tags a,b`
2. Same pattern shows up 3+ times → distill it → `observe <bank> "pattern statement" --refs <ids of source experiences>`
3. A plan comes out of it → `add <bank> decision "..." --tags plan` + `link` to the observation

## When to recall
- BEFORE any decision that touches a bank we have (check past decisions first)
- When operator references past work ("cron charon kenapa mati?")
- Observations sort FIRST in results — they are distilled lessons, weight them highest

## Quality bar (operator rule: no junk inside)
- Only store: decisions, lessons, stable facts, verified numbers. Never: small talk, transient states, session progress
- Anti-duplicate fires on add (>=82% token overlap). Never `--force` past it unless genuinely a distinct case
- One memory = one idea, self-contained (readable 6 months later without context)
- Banks: `operator` (cross-project), one bank per project (charon, qr-bintang, clients)

## Commands
- `mem add <bank> <type> "content" --tags a,b [--force]`
- `mem observe <bank> "synthesis" --refs id1,id2 --tags pattern` (auto-links to sources)
- `mem recall <bank> "query" [--type T] [--days N] [--limit N]` — observations rank first
- `mem link <bank> <from_id> <to_id>` / `mem backlinks <bank> <id>`
- `mem graph [bank]` (JSON, on-demand) · `mem list <bank>` · `mem stats [bank]` (health: observation_ratio) · `mem banks`
- `mem delete <bank> <id>` (explicit only, cleans links) · `mem backup` (dated folder, never overwrites)

## Rules
- Append-only: never rewrite history, delete + re-add if wrong
- At session end: distill new experiences into observations (keep stats healthy)
- After big installs/changes: `mem backup`
- Health check: `stats` says NOT consolidating if experiences exist with zero observations → distill then