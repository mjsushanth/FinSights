# S02h — Measurement as a Design Practice

> **The claim of this note.** Most of the good decisions in this deployment came from a
> measurement that took under five minutes to set up, and several of the bad ones came from
> reasoning confidently without one. The skill is not "knowing how to profile." It is
> **knowing which question a given tool can actually answer**, and designing the smallest
> experiment that discriminates between two hypotheses.
>
> Every example below is real, from this project, with the numbers it produced and — where
> it happened — the wrong conclusion it corrected.
>
> Companion: S02g - Concurrency and Shared State - Threadpools, Thread Safety, the Audit (Obsidian study note)

---

## 1. The core discipline: what can this tool *not* see?

This is the whole note in one idea. Every measurement tool has a scope, and the scope is
usually narrower than the question you are asking.

| Tool | Sees | **Cannot see** |
| :-- | :-- | :-- |
| `tracemalloc` | Python heap allocations | native memory — NumPy buffers, Arrow/Polars, C extensions |
| `docker stats` | container RSS, whole process | which *part* of the code holds it |
| `time.perf_counter` | wall clock of a block | whether the cost is CPU, IO, or lock contention |
| AST analysis | static structure | anything computed at runtime; `getattr`, `setattr`, `exec` |
| `grep` | text | scope, control flow, whether a match is in a comment or string |
| AWS `describe-*` | declared configuration | whether it *works* — permissions, reachability |
| Invoking an API | that it works right now | that it will work when routed to another region |

The failure mode is always the same: you use a tool, get a number, and answer a question the
number does not address. Section 3 is a case where that happened to me and reversed a
recommendation.

---

## 2. Method 1 — Sample an external observer while driving real work

**Question:** how much memory does the backend actually need, so the Fargate task can be
sized?

The documentation said 0.25 vCPU / 512 MiB. Trusting it would have produced a task that
OOM-killed on the first query. But you cannot measure peak memory from *inside* the process
cheaply and reliably, and you cannot measure it at all without real work to drive it.

So: an external sampler, a real query, and a marker file to coordinate them.

```bash
sample() {                                   # $1 = phase label
    while [ -f "$OUT/sampling" ]; do
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' \
            | sed "s/^/$1 /" >> "$OUT/stats_raw.log"
    done
}

run_query() {
    touch "$OUT/sampling";  sample "$1" &     # start sampling
    curl -s -X POST localhost:8000/query -d "$(jq -n --arg q "$2" '{question:$q}')" ...
    rm -f "$OUT/sampling";  wait              # stop sampling
}
```

Then reduce the log with awk, normalising MiB/GiB and keeping the max per phase:

```awk
{ if (mem ~ /GiB/) { gsub(/GiB/,"",mem); m=mem*1024 } else { gsub(/MiB/,"",mem); m=mem+0 }
  k=lbl" "name; if (m>max[k]) max[k]=m }
END { for (k in max) printf "%-28s peak=%8.1f MiB\n", k, max[k] }
```

**Result:**

| | Idle | Simple query | 10-company query |
| :-- | --: | --: | --: |
| Backend | 213 MiB | 1,139 MiB | **1,220 MiB** |
| Frontend | 146 MiB | 146 MiB | 146 MiB |

**What it decided:** 1 vCPU / 3072 MiB, split 2560 / 384.

**What it revealed beyond the number** — and this is the part worth copying:

1. **The frontend is flat.** 146 MiB idle and 146 MiB under load. That is not a lucky
   reading, it is *evidence* that the frontend is a pure HTTP client, which in turn justifies
   giving it only 384 MiB and justifies the whole "co-locate them, it's nearly free" argument.
2. **The backend loads lazily.** 213 → 1,220 MiB means ML components are constructed on
   demand, not at import. You cannot learn that by skimming the code, and it changes what
   caching can and cannot buy.
3. **Simple and heavy peaks are close** (1,139 vs 1,220). So most of the footprint is a fixed
   cost paid by any query, not proportional to result size. Different tuning problem entirely.

> **A good measurement answers a question you did not ask.** Three design facts fell out of
> one memory sample.

### 2.1 The honest limitation

The sampler runs `docker stats --no-stream` in a loop, which takes 1–2 s per iteration. On a
14 s query that is ~8 samples. **A spike between samples is invisible.** The reported peak is
a lower bound. Fine for sizing with 2× headroom; not fine if I were tuning to the megabyte,
where I would need `cgroup` `memory.peak` read directly.

---

## 3. Method 2 — Two passes, to separate one-time cost from per-call cost

**Question:** how expensive is the per-request component rebuild?

The trick is to run the same construction **twice in one process** and print both:

```python
for pass_no in (1, 2):
    print(f"===== PASS {pass_no} =====")
    timed("MLConfig()", MLConfig)
    timed("init_rag_components()", init_rag_components)
    ...
```

| Constructor | Pass 1 | Pass 2 | Reading |
| :-- | --: | --: | :-- |
| `MLConfig()` | 66.8 ms | 65.2 ms | genuinely per-call |
| `init_rag_components()` | 1076.7 ms | **592.2 ms** | ~485 ms was one-time module import |
| `PromptLoader()` | 91.5 ms | 92.4 ms | per-call |
| `create_bedrock_client_from_config()` | 4.0 ms | 3.8 ms | negligible |
| `QueryLogger()` | 72.5 ms | 71.4 ms | per-call |

Pass 1 alone would have overstated the recurring cost by 60%. **The steady-state number is
pass 2**, and the difference between the passes is itself a datum: it tells you how much of a
cold start is import machinery.

### 3.1 Where this measurement misled me, and how

I also captured `tracemalloc` peaks alongside the timings:

```
init_rag_components()   592.2 ms   peak_alloc=  0.7 MiB
```

Under 1 MiB. So I concluded the constructors were cheap in memory, correctly — and then made
an error one step later. I had earlier written that a large resident table was being loaded
per request as *construction* cost. The tracemalloc number contradicts that: construction
allocates almost nothing on the Python heap.

But **`tracemalloc` cannot see native allocations.** The ~900 MiB that `docker stats` saw is
Arrow/Polars buffers, invisible to `tracemalloc` by design. So the two tools together say:

> Construction is cheap. The memory is in the *query work*. Therefore caching constructors
> saves time but **will not reduce the task's memory footprint at all.**

Neither tool alone supports that conclusion. `tracemalloc` alone would say "nothing uses
memory." `docker stats` alone would say "something uses 900 MiB" without saying what.

> **Two tools with different blind spots, pointed at the same event, tell you something
> neither can tell you alone.** That is the most useful measurement pattern I know.

---

## 4. Method 3 — Cold instance vs warm instance, to find discarded work

**Question:** the audit found the DataLoader memoises tables into instance attributes. Since
a fresh loader is built per request, how much work does that throw away?

The experiment is almost trivially small, and that is the point — construct a **new** instance
for the cold reading, reuse **the same** instance for the warm one:

```python
loader = create_data_loader(config)      # fresh instance = cold memo
t0 = time.perf_counter(); df = fn();  cold = ...
t0 = time.perf_counter();      fn();  warm = ...   # same instance = memo hit
```

| Table | Cold | Warm | Rows |
| :-- | --: | --: | --: |
| Stage 2 meta | 189.1 ms | 0.00 ms | 614,787 |
| KPI fact | 4.4 ms | 0.00 ms | 9,260 |
| **dim: companies** | **477.5 ms** | 0.00 ms | **25** |
| dim: sections | 201.7 ms | 0.00 ms | 21 |
| **Total** | **872.7 ms** | **0.01 ms** | |

Two findings, both of which changed something:

**(a) It reversed a recommendation.** Constructor time was 825 ms; this is another 873 ms.
Total avoidable per-request work is **~1,698 ms ≈ 17.7%** of a 9.6 s query — not the 8.6% I
had reported. I had told the user caching was "not necessary" based on measuring *one* of the
two costs. Measuring the second one inverted the advice.

**(b) A 25-row table is slower than a 614,787-row table.** 477 ms versus 189 ms. Whatever
`dim: companies` costs, it is not data volume — it is per-call overhead: round trip, file
open, parquet footer parse.

> **Latency tracks round trips, not bytes.** This table is a clean natural experiment for it,
> and it is the heuristic I would keep if I could keep only one.

### 4.1 Limitation, stated because it matters

These were measured in a container that had been running for hours and had already served
queries, so the `/tmp/finrag_cache` disk cache was **warm**. A genuinely cold container pays
S3 download time on top. So 873 ms is the *warm-disk* figure and the true first-request cost
is higher — unmeasured.

---

## 5. Method 4 — Static analysis for questions runtime cannot answer

Some properties are about *all possible executions*, so no amount of running the program
proves them. "No component mutates itself after construction" is one: testing shows it did
not happen in the paths you exercised.

That is what the AST audit in S02g - Concurrency and Shared State - Threadpools, Thread Safety, the Audit (Obsidian study note)
is for, and the discipline that made it useful was making it **report rather than judge**:

```
SAFE     EntityAdapter       (7 attrs, all set in __init__)
SUSPECT  MLConfig            (1 attr mutated outside __init__)
           self._aws_creds_source <- _load_aws_credentials():60,72,83
```

The single SUSPECT was a false positive: `_load_aws_credentials()` is called *from*
`__init__`. The tool answered "assigned outside `__init__`" when the question was "assigned
after construction completes."

> **A static check answers the question you encoded, not the question you meant.** Design its
> output as a worklist for a human, not a verdict. A tool that printed "1 FAIL" would have
> been confidently wrong, and the confidence is the damaging part.

And: enumerate the blind spots explicitly and check each one separately. That audit could not
see in-place container mutation (`self.cache[k] = v`) or module-level globals, so both got
their own grep. "It passed" is meaningless until you have written down what it could not see.

---

## 6. Method 5 — Ask the cloud instead of assuming

A whole class of question is answerable by API call, and guessing instead is inexcusable
because the call takes seconds.

**Cross-region inference routing.** A least-privilege IAM policy for a `us.*` Bedrock model
needs the foundation-model ARN in every region the profile can route to. I could have assumed
"us-east-1 and us-west-2." Instead:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier "us.anthropic.claude-haiku-4-5-20251001-v1:0"
# "Routes requests to Anthropic Claude Haiku 4.5 in us-east-1, us-east-2 and us-west-2."
```

Three regions. A policy naming two would have worked *most of the time* and thrown
`AccessDeniedException` intermittently — the most expensive kind of bug to diagnose.

**Model access.** `list-foundation-models` tells you a model *exists*. It does not tell you
this account may invoke it. So preflight **invokes** both models with a 2-token request:

```python
runtime.invoke_model(modelId=model_id, body=json.dumps(
    {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 2,
     "messages": [{"role": "user", "content": "hi"}]}))
```

> **A capability check should exercise the capability.** Listing is not invoking; describing
> is not permitting.

**Route tables, not subnet flags.** `MapPublicIpOnLaunch` looks like it means "public." It
does not — reachability is a property of the route table. So the code checks for a real
internet-gateway route rather than the flag.

**Prices.** See §8 — this one I got wrong first.

---

## 7. Method 6 — Measure the artifact, not the description of the artifact

Cheap, and repeatedly worth it:

| Claim in documentation | Measured reality |
| :-- | :-- |
| Stage 2 parquet "500 MB – 2.3 GB" | **64,781,290 bytes** (~62 MiB), 614,787 rows |
| Task shape 0.25 vCPU / 512 MiB | needs **1,220 MiB** peak |
| ECR storage "~$1/month" | 0.643 GB → **$0.0643/month** |
| "Service Discovery: Free" | Route 53 private hosted zone bills monthly |

```bash
aws ecr describe-images --repository-name finsights-backend \
  --query 'sum(imageDetails[].imageSizeInBytes)' --output text
```

Every one of these was a one-line command against a claim that had been sitting in a document
for months. **Documentation drifts; artifacts do not.** When they disagree, the artifact wins,
and the document should be corrected rather than quietly worked around.

---

## 8. Three times my own measurement was the thing that was broken

The uncomfortable section, and the most useful one.

**8.1 A grep pattern that could never match.** While waiting for a deployed query to appear
in CloudWatch, I ran a monitor loop:

```bash
until ... | grep -qiE "credential|IAM_ROLE|S3_STREAMING|denied|Traceback"; do sleep 5; done
```

The log says `using IAM role` — space, lowercase. `IAM_ROLE` with an underscore never matched.
I waited five minutes on a condition that could not become true, while the query had already
succeeded.

> **A verification tool that is silently broken is worse than no verification tool**, because
> it manufactures false confidence. It produced "no evidence of success," which I was one step
> from reading as "failure."

Habit: **test that your check can go green.** Run it against a case you know passes.

**8.2 An exit code from the wrong command.** I reported a deployment as "exit code 0." It was
not; the deploy had failed on the ECS service-linked role. The 0 came from the `tail` at the
end of my shell pipeline. Fix: write the real status into the log explicitly —

```bash
python -m deploy_aws.cli up > up.log 2>&1
echo "REAL_EXIT_CODE=$?" >> up.log
```

**8.3 A Pricing API query that returned nothing.** I queried Fargate rates, got zero results,
and labelled the figures UNVERIFIED. The query was wrong: usage types carry a region prefix
(`USE1-Fargate-ARM-vCPU-Hours:perCPU`). Once fixed, the numbers came back exactly:

| | x86_64 | ARM64 |
| :-- | --: | --: |
| vCPU-hour | $0.040480 | $0.032380 |
| GB-hour | $0.0044450 | $0.0035600 |

> **"My tool returned nothing" and "the data does not exist" are different conclusions.**
> Conflating them produces a confident gap, which is its own kind of wrong answer.

Also worth noting from that same episode: `set -- $spec` inside a `for` loop silently did
nothing, because **zsh does not word-split unquoted variables** the way bash does. The
symptom was files named `D1-control-plane 1480 1230.png`. Shell dialect is part of your
measurement apparatus.

---

## 9. The pattern behind all of it

Every measurement above has the same three-part shape:

1. **Two competing hypotheses**, stated before measuring. "Construction is expensive" vs "the
   query work is expensive." "Polars will find the task role" vs "it will not."
2. **The smallest experiment that discriminates** between them. Two passes. Cold instance vs
   warm instance. One real query.
3. **An explicit statement of what the experiment cannot rule out**, so the conclusion is
   scoped honestly.

Step 3 is the one that gets skipped, and skipping it is how a real measurement becomes an
overclaim.

### 9.1 Label provenance, always

Carry this into documents and commit messages:

| Label | Means |
| :-- | :-- |
| **VERIFIED** | I observed this directly, with the command recorded |
| **UNVERIFIED** | plausible, inferred, or from documentation — not observed here |
| **NOT FOUND** | I looked and there was no evidence; distinct from "false" |

The cost of an unlabelled number is that a later reader — often you — cannot tell whether to
re-check it. Three of the corrections in this note were possible *only* because the original
claim carried its provenance.

---

## 10. A checklist worth reusing

- [ ] What two hypotheses am I distinguishing? (If only one, I am confirming, not measuring.)
- [ ] What is the smallest experiment that separates them?
- [ ] What can this tool structurally **not** see? Does a second tool cover that gap?
- [ ] Is this cold or warm? Have I run it twice to find out?
- [ ] Is the sampling interval short enough for the event I care about?
- [ ] Can my check go green? Have I proved it against a known-passing case?
- [ ] Am I reading the exit code of the thing I ran, or of the last thing in the pipe?
- [ ] Am I measuring the artifact, or a document describing the artifact?
- [ ] Did I ask the API instead of assuming? Did I *exercise* the capability, not just list it?
- [ ] Is every number in my write-up labelled VERIFIED / UNVERIFIED / NOT FOUND?
- [ ] What did this measurement reveal that I was not looking for?

---

## Related notes

- S02g - Concurrency and Shared State - Threadpools, Thread Safety, the Audit (Obsidian study note)
- S02i - Higher-Level Design Principles from a Real Deployment (Obsidian study note)
- S03 - Systems Walkthrough - Deploying a RAG Service to AWS (Obsidian study note)

*All figures verified 2026-07-31 unless marked otherwise. Scripts preserved in
`ModelPipeline/finrag_ml_tg1/investigation_analysis/`.*
