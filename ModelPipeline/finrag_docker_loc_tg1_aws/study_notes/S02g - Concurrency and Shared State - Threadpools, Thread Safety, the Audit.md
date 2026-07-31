# S02g — Concurrency and Shared State: Threadpools, Thread Safety, and the Audit

> **Why this note exists.** The FinSights backend rebuilds every RAG component on every
> request. The obvious fix is to build them once and share them. That fix is only correct
> if the shared objects are safe to share — and "safe to share" is a precise, checkable
> property, not a vibe.
>
> This note is the reasoning and the actual audit. It ends with a verified answer for this
> codebase and a method you can re-run on any other.
>
> Companion notes: S02h - Measurement as a Design Practice (Obsidian study note) for how the numbers were
> obtained, S02f - Serving and Production - Processes, Health, Cost (Obsidian study note) for how a request
> reaches a process in the first place.

---

## 1. The trap: you have concurrency even when you think you don't

The backend runs `uvicorn --workers 1`. One process. It is tempting to conclude that
requests are serialised and sharing state is therefore free.

That conclusion is **wrong**, and the reason is specific to how FastAPI dispatches.

```python
@app.post("/query")
def query_endpoint(request: QueryRequest):     # <- def, not async def
    result = answer_query(...)
```

FastAPI inspects each endpoint. The rule:

| Endpoint declared as | Runs where | Concurrency |
| :-- | :-- | :-- |
| `async def` | on the event loop, directly | cooperative — one at a time between `await` points |
| **`def`** (sync) | **handed off to a threadpool** | **genuinely parallel across threads** |

A sync endpoint would block the entire event loop if it ran there — one 50-second RAG query
would freeze every other connection, including health checks. So Starlette/AnyIO moves it
to a worker thread (`run_in_threadpool`), and the loop stays free.

Consequence:

> **A sync endpoint in a single-worker FastAPI process is executed by a pool of threads.
> Two requests really can be inside the same function, touching the same objects, at the
> same time.**

The default pool is small — AnyIO's default limiter is 40 threads — but 2 is enough to
corrupt shared mutable state. And the GIL does not save you: it makes individual bytecode
operations atomic, not *sequences* of them. `if self._x is None: self._x = load()` is a
read, a branch, and a write, and a thread switch can land between any of them.

### 1.1 Why this is easy to miss

Three reasons, all of which applied here:

1. `--workers 1` reads like "no concurrency."
2. The bug is a *race*, so it does not reproduce on demand. It shows up as a rare wrong
   answer, which gets attributed to the LLM.
3. Local testing is single-user. You will not see it until two people click at once — or
   until a health check overlaps a query.

---

## 2. What "safe to share" actually means

The property is simpler than it sounds:

> **An object is safe to share across threads if, after construction, its state is only
> ever read.**

That is it. Immutable-after-construction objects are trivially safe, because there is no
write for a race to interleave with. Anything that writes to itself during a call is
holding per-call state on a shared object, which means request A can observe or clobber
request B's value.

So the audit question becomes mechanical: **which attributes are assigned outside the
constructor?**

### 2.1 Three kinds of "mutation," only some of which are dangerous

| Pattern | Example | Dangerous? |
| :-- | :-- | :-- |
| Per-call scratch state | `self._current_query = q` | **Yes.** Two requests overwrite each other. |
| Lazy memoisation of an immutable value | `if self._df is None: self._df = load()` | **Benign race.** Both threads may load; both results are equal; one assignment wins. Wastes work and transient memory, does not corrupt. |
| Accumulating collection | `self._results.append(x)` | **Yes.** Cross-request leakage. |

That middle row matters, and it is why an audit tool must *report* rather than *judge*. A
memoisation cache and a per-query field look identical to a static checker and have
completely different consequences.

---

## 3. boto3: the specifics, because "is boto3 thread-safe" has three answers

Straight from the boto3 documentation, because this is exactly the kind of thing not to
recall from memory:

| Object | Thread-safe? | Guidance |
| :-- | :-- | :-- |
| **Client** | **Generally yes** | Safe to share across threads. **Not** across processes — the networking implementation can misorder responses. |
| **Resource** | **No** | Create one per thread. |
| **Session** | **No** | Create one per thread or process. |

Two footnotes that are easy to skip and worth keeping:

- On a client, the metadata attributes `meta`, `exceptions` and `waiter_names` are safe to
  **read**, but **mutating** them is not thread-safe.
- **Custom botocore event hooks can break thread safety.** If you register handlers on the
  event system, the guarantee no longer straightforwardly applies.

### 3.1 The sanctioned pattern, and what it implies

boto3's own documented example is precisely "make the client up front, share the client":

```python
def my_workflow():
    session = boto3.session.Session()
    s3_client = session.client("s3")            # created once, on one thread

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(do_s3_task, s3_client, task) for task in my_tasks]
        #                                      ^^^^^^^^^ shared across threads: fine
```

Note the asymmetry this creates, which is the actually useful takeaway:

> **Create clients on one thread; share the clients. Never share the Session for the
> purpose of creating more clients concurrently.**

So a cached-client factory is the right shape — *provided the cache is populated before the
threads start, or the population is locked.* My own `AwsSession` in `deploy_aws/` has
exactly this latent issue:

```python
def client(self, service: str) -> Any:
    if service not in self._clients:                        # read
        self._clients[service] = self.session.client(...)   # touches shared Session
    return self._clients[service]
```

Two threads asking for a *new* service simultaneously would both touch the shared Session,
which boto3 says is not thread-safe. In the deployment tool this is harmless — it is
single-threaded by construction, one command at a time. But it is a real constraint, and
writing it down is better than rediscovering it when someone parallelises the provisioning
steps.

**The general principle**: "X is thread-safe" is almost never a property of a library. It is
a property of *a specific object under a specific access pattern*. Clients yes, sessions no,
same library.

---

## 4. The audit: doing it mechanically instead of by eye

Grep cannot answer "which attributes are assigned outside `__init__`," because grep does not
know which function a line is inside, and it matches strings and comments. The AST does.

```python
def self_targets(node):
    """Attribute names assigned via `self.<name>` in this statement."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.attr for t in targets
            if isinstance(t, ast.Attribute)
            and isinstance(t.value, ast.Name) and t.value.id == "self"]
```

Then for each `ClassDef`, walk each `FunctionDef`, and bucket the `self.x = ...` assignments
by whether the enclosing function is `__init__` / `__post_init__` / `__new__` or something
else. Report, do not judge:

- **SAFE** — assigns to self only in the constructor.
- **SUSPECT** — assigns elsewhere; list each attribute with method and line number so a
  human can classify it against the table in §2.1.

Roughly 90 lines. The full script lives in
`ModelPipeline/finrag_ml_tg1/investigation_analysis/` alongside the analysis document.

### 4.1 The result for this codebase

```
=== entity_adapter.py ===      SAFE  EntityAdapter          (7 attrs, all in __init__)
=== pipeline.py ===            SAFE  MetricPipeline         (2 attrs)
=== query_embedder_v2.py ===   SAFE  QueryEmbedderV2        (2 attrs)
=== metadata_filters.py ===    SAFE  MetadataFilterBuilder  (1 attr)
=== variant_pipeline.py ===    SAFE  VariantPipeline        (5 attrs)
=== s3_retriever.py ===        SAFE  S3VectorsRetriever     (15 attrs)
=== sentence_expander.py ===   SAFE  SentenceExpander       (4 attrs)
=== bedrock_client.py ===      SAFE  BedrockClient          (7 attrs)
=== query_logger.py ===        SAFE  QueryLogger            (9 attrs)
=== prompt_loader.py ===       SAFE  PromptLoader           (5 attrs)
=== ml_config_loader.py ===    SUSPECT  MLConfig  (1 attr mutated outside __init__)
                                 self._aws_creds_source <- _load_aws_credentials():60,72,83

TOTAL: 17 safe, 1 suspect
```

**Every component the RAG pipeline shares is stateless after construction.** That is the
answer that unblocks caching.

### 4.2 The one SUSPECT was a false positive — and the reason is instructive

`MLConfig._aws_creds_source` is assigned in `_load_aws_credentials()`, not in `__init__`. But:

```
ml_config_loader.py:36:        self._load_aws_credentials()     # <- called FROM __init__
ml_config_loader.py:44:    def _load_aws_credentials(self):
```

The mutation happens *during construction*, via a helper. So `MLConfig` is safe.

The tool asked "assigned outside `__init__`?" when the real question is **"assigned after
construction completes?"** Those differ whenever a constructor delegates to helpers, which
is most well-factored code.

> **A static check answers the question you encoded, not the question you meant.** Its output
> is a list of things to look at, not a verdict. A tool that emitted "1 FAIL" here would have
> been confidently wrong.

Making it answer the real question requires a call graph — every method transitively
reachable from `__init__` counts as construction. That is a meaningful jump in complexity
for a check whose false positives a human can classify in thirty seconds, so I deliberately
did not build it. **Knowing where to stop is part of the design.**

### 4.3 Two blind spots I checked separately

A per-class AST audit cannot see:

**(a) In-place mutation of a contained object.** `self.cache[k] = v` and
`self.items.append(x)` mutate shared state without ever assigning to `self.<attr>`, so the
audit is blind to them.

```bash
grep -nE "self\.[a-zA-Z_]+\^ (Obsidian study note)+\] *=|self\.[a-zA-Z_]+\.(append|extend|update|add|pop|clear)\(" ...
# no matches across all eight component files
```

**(b) Module-level mutable globals.** A `_CACHE = {}` at module scope is shared by every
instance and every thread, and a class-scoped audit will never look there.

```bash
grep -nE "^_?[a-z][a-zA-Z_]* *[:=] *(\{\}|\[\])|^global |    global " ...
# no matches
```

Both clean. The point is not that they were clean — it is that **each blind spot needed its
own check.** "The audit passed" means nothing until you enumerate what the audit cannot see.

---

## 5. The genuinely shared mutable thing, and why it is the *point*

One class did come back SUSPECT for real:

```
=== data_loader_strategy.py ===
  SAFE     DataLoaderStrategy
  SUSPECT  LocalCacheLoader    (4 attrs mutated outside __init__)
  SUSPECT  S3StreamingLoader   (4 attrs mutated outside __init__)
             self._stage2_df      <- load_stage2_meta():176, 193
             self._kpi_fact_df    <- load_kpi_fact_data():241, 259
             self._dim_companies  <- load_dimension_companies():203
             self._dim_sections   <- load_dimension_sections():215
```

This is lazy memoisation — row 2 of the table in §2.1, the benign-race kind. And it reframes
the entire caching question.

Today `init_rag_components()` builds a **fresh DataLoader per request**, so this memo is
populated and then thrown away every single time. Measured inside the running container:

| Table | Cold (per request today) | Warm (memo hit) | Rows |
| :-- | --: | --: | --: |
| Stage 2 meta | 189.1 ms | 0.00 ms | 614,787 |
| KPI fact | 4.4 ms | 0.00 ms | 9,260 |
| dim: companies | 477.5 ms | 0.00 ms | 25 |
| dim: sections | 201.7 ms | 0.00 ms | 21 |
| **Total** | **872.7 ms** | **0.01 ms** | |

Two things jump out.

**First, caching components does more than skip constructors.** Constructor time is ~825 ms;
table loading is another ~873 ms. Together **~1,698 ms per request** — about **17.7%** of a
9.6 s query, not the 8.6% that constructor timing alone suggested. I had judged this "not
worth doing" from the constructor numbers. That judgement was wrong, and it was wrong
because I had measured one of the two costs.

**Second, look at `dim: companies`: 477 ms for 25 rows.** Cost here has nothing to do with
data volume. It is per-call overhead — round trip, file open, parquet metadata parse. The
25-row table is *slower* than the 614,787-row table.

> **Latency tracks the number of round trips, not the number of bytes.** This is the single
> most reliably useful heuristic in data-access performance, and this table is a clean
> natural experiment for it.

### 5.1 What sharing the memo requires

Once the DataLoader is shared, its lazy init runs under concurrency:

```python
if self._stage2_df is None:        # thread A reads None; thread B reads None
    self._stage2_df = load(...)    # both load; one assignment wins
return self._stage2_df
```

Correctness is fine — Polars DataFrames are immutable, both threads load equal data, and the
loser's copy is garbage collected. But two concurrent cold loads mean **two copies of a
62 MB table in flight**, on a task sized at 3072 MiB with a measured 1,220 MiB peak. That is
survivable, and it is still worth a lock, because the cost of the lock is zero in the warm
path:

```python
if self._stage2_df is None:                 # fast path, no lock
    with self._lock:
        if self._stage2_df is None:         # re-check under the lock
            self._stage2_df = load(...)
return self._stage2_df
```

That is **double-checked locking**. The outer check makes the common case lock-free; the
inner check makes the initialisation happen exactly once. (In Python it is safe; in languages
with weaker memory models it famously is not, without explicit barriers.)

---

## 6. The design conclusion

| Question | Answer | How known |
| :-- | :-- | :-- |
| Do concurrent requests actually happen? | Yes — sync endpoint → threadpool | FastAPI dispatch rules |
| Are the 10 RAG components safe to share? | **Yes** — stateless after construction | AST audit, 17/17 clean |
| Are the boto3 clients they hold safe to share? | **Yes** — clients are thread-safe | boto3 docs |
| Is anything genuinely shared and mutable? | Yes — the DataLoader's lazy table memo | AST audit |
| Is that dangerous? | No, benign race; wants a lock to avoid double loads | reasoning + immutability of Polars frames |
| Is caching worth doing? | **Yes — ~1,698 ms/request, ~17.7%** | measured, both halves |

The sequence to internalise: **audit before you cache, and measure both halves of the cost
before you judge.** The audit turned "I think this is probably fine" into a verified property.
The measurement turned "not worth doing" into "worth doing," and it did so by finding a cost
I had not thought to look for.

---

## 7. Higher-level questions this opens

These do not have tidy answers, which is why they are worth holding onto.

**7.1 Where should a cache live?** Three options, and the trade is about *blast radius*:

| Placement | Lifetime | Cost of getting it wrong |
| :-- | :-- | :-- |
| Inside each component (as now) | per instance | contained — one component |
| A module-level singleton in the orchestrator | per process | one process's requests |
| An external store (Redis, etc.) | cross-process | every consumer, plus a new failure mode |

For one task with one process, the middle option is right, and the third would be pure
overhead. Adding Redis here would be adding a dependency, a network hop, and a new outage
mode to solve a problem that does not exist yet.

**7.2 When does per-request construction become the correct answer?** It is not always
wrong. If components held per-tenant credentials, or per-user authorisation scope, then
sharing them across requests would be a security bug and rebuilding would be the *point*.
The reason sharing is safe here is that **every request has identical authority** — one task
role, no per-user data. Change that assumption and this whole note inverts.

**7.3 Should the endpoint be `async def` instead?** It would remove the threadpool, and with
it this entire class of concern. But `answer_query` is blocking and CPU/IO-heavy; making the
endpoint async without making the internals async would block the event loop and be strictly
worse. Sync-in-threadpool is the correct choice for a blocking workload. **The concurrency
model is a consequence of the work, not a free choice.**

**7.4 What is the actual failure mode of getting this wrong?** Worth naming, because it
governs how much care is proportionate: a shared mutable field produces *a wrong answer to a
correct query*, intermittently, under load, with no error and no traceback. In a financial
RAG system that is close to the worst available failure. That asymmetry — silent wrongness
versus a crash — is what justifies auditing rather than assuming.

---

## Related notes

- S02h - Measurement as a Design Practice (Obsidian study note) — the tools and their blind spots
- S02i - Higher-Level Design Principles from a Real Deployment (Obsidian study note) — the abstract layer
- S02f - Serving and Production - Processes, Health, Cost (Obsidian study note) — sockets, workers, health
- S03 - Systems Walkthrough - Deploying a RAG Service to AWS (Obsidian study note) — the deployment this sits in

*All audit output and measurements: verified 2026-07-31 in the running backend container.*
