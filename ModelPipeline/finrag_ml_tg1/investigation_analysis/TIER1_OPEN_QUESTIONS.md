# TIER 1 — OPEN QUESTIONS FOR JOEL

Unlike `TIER1_PROGRESS_LOG.md`, this file is **mutable**. Items get added when blocked and
struck through when resolved.

Rule for autonomous runs: **never end a turn with a question.** If something needs Joel's
judgment, write it here with enough context to answer cold, then move to the next queue
item. Idling is the one unacceptable outcome.

Each item: what is blocked, why it needs a human, what I did instead, and what I would do
under each possible answer — so the answer is a single word, not a conversation.

---

## OPEN

### Q1 — Is a slower first query acceptable in exchange for faster subsequent ones?
**Status:** OPEN, but proceeding under an assumption.
**Context:** Change 1 caches the RAG object graph at module level. The first query in a
fresh container still pays the full ~1,700 ms build; every later one pays zero. On ECS,
"first query after `up`" is exactly the demo query.
**Assumption I am proceeding under:** yes, acceptable — the alternative is warming at
container start, which moves the cost into ECS startup where nobody is watching a spinner.
**If you disagree:** say "warm at startup" and I will call `_get_components()` from a
FastAPI startup hook instead, trading ~1.7 s of container boot for a fast first query.

---

## RESOLVED

*(none yet)*
