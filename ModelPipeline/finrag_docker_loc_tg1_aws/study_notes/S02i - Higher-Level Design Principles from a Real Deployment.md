# S02i — Higher-Level Design Principles from a Real Deployment

> **What this note is.** The abstract layer. S03 - Systems Walkthrough - Deploying a RAG Service to AWS (Obsidian study note)
> walks through *what* was built; S02h - Measurement as a Design Practice (Obsidian study note) covers *how we
> know things*. This note extracts the transferable principles — each one stated as a rule,
> then grounded in the specific place in this project where it earned its keep.
>
> Fourteen principles. Every example is real. Several of them are places where I was wrong
> first, which is the only reason I trust them.

---

## Group 1 — Make bad states impossible, not unlikely

### P1. Prefer "unrepresentable" to "unlikely"

> If a class of bug can be eliminated by the *shape* of the code rather than by care, do that
> instead.

The December deployment had two YAML files that disagreed: `setup-infrastructure.yml` created
a cluster named `finsights-cluster`, while `deploy-ecs.yml` deployed into
`finsights-cluster-new`. The teardown block therefore deleted the wrong cluster, leaving the
real one running and billing.

No amount of care prevents that. A **single frozen dataclass** does:

```python
@dataclass(frozen=True)
class DeployConfig:
    cluster_name: str = "finsights-cluster"
```

Two modules cannot disagree about the name, because neither can change it and there is only
one. The bug is not *avoided*, it is **unrepresentable**.

The general test: when you fix a bug, ask whether you fixed *this instance* or *the class*.
Renaming one string fixes the instance. Collapsing two sources of truth into one fixes the
class.

### P2. Validate at the boundary where the error message is still useful

> Reject bad input at the point where you can still say what is wrong and what would be right.

Fargate accepts only specific cpu/memory pairs. `RegisterTaskDefinition` rejects an invalid
pair with a message that names neither the offending value nor the valid alternatives. So the
check moved into the config object:

```python
raise ValueError(
    f"task_memory={self.task_memory!r} is not valid for task_cpu={self.task_cpu!r}. "
    f"Valid: {sorted(allowed, key=int)}")
```

Same failure, caught seconds earlier, with the answer included. The principle is not "validate
input" — everyone knows that. It is that **the value of a validation is proportional to how
much better your error message is than the one you would otherwise get.**

---

## Group 2 — Convergence over creation

### P3. Write code that converges, not code that creates

> Stop asking "does this exist yet?" Start asking "does this match the description?"

The single highest-leverage idea in the whole project. The December IAM guard:

```bash
if aws iam get-role --role-name "$ROLE"; then echo "exists"     # checks ONE thing
else aws iam create-role ...; aws iam attach-role-policy ...     # does TWO things
fi
```

If `create-role` succeeded and `attach-role-policy` failed, the role exists with no policy,
and every future run prints "exists" and never repairs it. The failure surfaces later as
`AccessDenied` from inside a container, far from its cause.

The rule that kills the class:

> **Guard only the operation that is genuinely not idempotent. Let naturally idempotent
> operations run unconditionally, every time.**

| Operation | Idempotent? | Treatment |
| :-- | :-- | :-- |
| `CreateRole` | no | guard it |
| `AttachRolePolicy` | yes — describes an end state | never guard it |
| `PutRolePolicy` | yes — full replace | never guard it |
| `authorize_security_group_ingress` | no, but duplicate is benign | catch the duplicate error |

Running the idempotent calls every time is not waste — **it is the self-heal.** There is no
"create path" and "repair path"; there is only "converge." A crashed run becomes a run that
has not finished converging.

### P4. Make the destructive path as complete as the constructive one

> Every teardown step must tolerate the thing already being absent.

Otherwise a half-built stack cannot be cleaned up, and you accumulate orphaned billable
resources. `delete_all()` runs in reverse dependency order and swallows not-found on every
step. That is what makes P5 possible.

### P5. The reverse operation is the completeness test

> If you cannot destroy it and rebuild it from the repository, you do not have infrastructure
> as code. You have a console with a backup script.

Any weaker test can pass on a system that secretly depends on state nobody recorded. This is
precisely how December's deployment looked healthy right up until the account closed.

So: `destroy` → 6/6 resource checks empty → `up` → steady state again as revision 2.
Destroy-and-rebuild is not a disaster-recovery drill. **It is the unit test for whether your
description is complete.**

---

## Group 3 — Structure follows change

### P6. One file, one reason to change

> Partition by *what causes an edit*, not by what things are.

Eight modules, and the justification is a single column:

| Change | File you edit |
| :-- | :-- |
| a resource name or size | `config.py` |
| a permission | `policies.py` |
| the container shape | `taskdef.py` |
| how a resource is created | `provisioner.py` |

That is what "single responsibility" actually buys: **predictable blast radius.** You can
answer "what could this edit break?" before making it.

### P7. Push the risky logic into pure functions

> The things most likely to be wrong should be the things easiest to check.

The two most error-prone artifacts in an AWS deployment are the **IAM policy** and the **task
definition**. Both were made pure: config + account id in, dict out. No network, no state, no
ordering. Which means a security property becomes an offline assertion:

```python
for statement in doc["Statement"]:
    for action in statement["Action"]:
        assert not action.endswith(":*"), f"service wildcard in {statement['Sid']}"
        assert "Delete" not in action,    f"delete granted in {statement['Sid']}"
```

This is not an accident of the design — it is the reason for it. **Ask which part of a system
you are most afraid of, then move that part somewhere it can be tested without a network.**

### P8. Nothing constructs its own collaborators

> Dependencies arrive through the constructor. Always.

`Provisioner` is handed an `AwsSession`; `AwsSession` is handed a `DeployConfig`. The usual
justification is testability, and it is true but secondary. The primary payoff:

> **The dependency graph becomes readable.** You can determine everything a class touches by
> reading its constructor.

In the alternative — every module calling `boto3.client()` for itself — you must read every
method to know what a class reaches.

### P9. Know when to stop building the tool

> A tool whose false positives a human can triage in thirty seconds does not need to be
> perfect.

The AST statelessness audit reports "attributes assigned outside `__init__`." The question it
*means* is "assigned after construction completes." Those differ when a constructor delegates
to helpers — and one such false positive appeared (`MLConfig._aws_creds_source`, assigned in
a helper called from `__init__`).

Fixing it properly requires a call graph. I deliberately did not build that. **Over-engineering
the measurement tool is the same failure as over-engineering the system**, and it is more
seductive because it feels like rigour.

---

## Group 4 — Epistemics as an engineering discipline

### P10. Compare your effect against the system's own noise floor

> Before calling a difference meaningful, measure how much the system differs from *itself*.

The best piece of experimental design in this project. When comparing Cohere Embed v4 vectors
obtained via Bedrock against the same model via Cohere's native API, the mean cosine came out
`0.99984832` — just *below* a pre-registered `0.9999` identity threshold, landing in a
"drifting, needs decision" band.

The naive reading is "the transports disagree." The notebook instead asked a falsifiable
question: **is that difference larger than the difference between two calls to the same
endpoint?**

```
A) different transport (Bedrock stored vs Cohere direct)  mean 1.517e-04   max 2.743e-04
B) SAME endpoint, same model, repeat call                 mean 2.772e-04   max 2.772e-04
   worst cross-transport / worst same-endpoint = 0.99x
```

The cross-transport difference is **no larger than the model's own run-to-run variation.** The
"drift" was noise, not a transport effect.

Which also produced a genuinely surprising finding: repeat calls to one endpoint with
identical text gave **31/32 bit-identical vectors and 1/32 different** (max per-component
difference `2.891e-03`). The endpoint is not bit-deterministic — attributed to batch
composition and accumulation order in the serving stack.

> **Any measurement without a noise floor is uninterpretable.** "0.9998 similarity" means
> nothing until you know what identical inputs produce.

### P11. Pre-register the decision rule

> Write down the thresholds and what each one implies *before* you see the numbers.

That same notebook fixed its rubric in advance: `>= 0.9999` = same vector space; `0.99–0.9999`
= drifting, needs decision; `< 0.99` = different space. Then it ran.

This is what stops the result from being negotiated after the fact. It is also why the
"drifting" verdict was trustworthy enough to *act* on — the analysis in P10 was a
pre-committed follow-up, not a search for a reason to proceed.

### P12. Prefer deterministic sampling to seeded randomness

> "Reproducible" should not depend on an RNG implementation.

Instead of `df.sample(n=32, seed=42)`, that study sorted `sentenceID` lexicographically and
took evenly-spaced indices with `stride = n // SAMPLE_SIZE`. Because the ID encodes
`{cik}_{form}_{year}_section_{n}_{i}`, striding auto-spreads across companies, years and
sections — yielding 20 companies and 10 report years from 32 picks.

The stated rationale: byte-for-byte reproducible on any machine and any library version, where
a seeded shuffle depends on the RNG. **Determinism by construction beats determinism by
configuration.**

### P13. Label provenance on every number

Three labels, used consistently:

| Label | Means |
| :-- | :-- |
| **VERIFIED** | observed directly, command recorded |
| **UNVERIFIED** | inferred, published, or reasoned — not observed here |
| **NOT FOUND** | looked, found no evidence — distinct from "false" |

The payoff is compounding. Every correction I have made in this project was possible *because*
the original claim carried its provenance:

- Fargate ARM pricing was labelled UNVERIFIED because my Pricing API query returned nothing.
  The query was wrong (usage types carry a `USE1-` prefix). **"My tool returned nothing" and
  "the data does not exist" are different conclusions.**
- The per-request caching cost was reported as 825 ms from constructor timing. Measuring the
  *other* half — discarded table loads, 873 ms — took the total to ~1,698 ms (~17.7% of a
  9.6 s query) and **reversed my recommendation** from "not necessary" to "worth doing."
- An audit tool that printed "1 FAIL" instead of "1 SUSPECT, here is the line" would have been
  confidently wrong.

The corollary is uncomfortable and important: **an unlabelled number is a liability**, because
a later reader cannot tell whether to re-check it.

### P14. Negative and null results are results

> The experiment that says "do not ship this" has done its job.

The reranking study made 30 real LLM calls across 10 gold questions and three configurations,
and found top-8 reranking was **better on quality *and* cheaper**:

| config | avg ROUGE-L | avg context chars | avg input tokens | total cost |
| :-- | --: | --: | --: | --: |
| no rerank | 0.101 | 35,905 | 13,108 | $0.1970 |
| rerank top-16 | 0.105 | 25,015 | 10,689 | $0.1631 |
| **rerank top-8** | **0.112** | **14,314** | **8,140** | **$0.1319** |

61% median context reduction, 32% cost reduction, and the best ROUGE-L. **And it was not
shipped.** On a 10-question sample with ROUGE-L differences of 0.011, that is well inside the
noise a 10-question suite can resolve — exactly the P10 discipline applied to a result that
was *flattering*.

Applying a noise floor only to results you dislike is not rigour, it is motivated reasoning.
The harder skill is **declining to act on a good-looking result that your sample cannot
support.**

---

## Group 5 — Forces that shape architecture

### P15. A tight cost constraint removes options you did not need

One constraint — "never adopt anything costing ~$17/month" — decided seven things:

| Decision | Hurt quality? |
| :-- | :-- |
| One task, two containers (no ALB) | **No** — it is the only option preserving `depends_on` ordering |
| Public subnets (no NAT, −$32.85/mo) | No — the workload needs egress, not inbound privacy |
| `localhost` over Cloud Map | No — removed a DNS failure mode entirely |
| ARM64 | No — also the native build on Apple Silicon |
| 7-day log retention | Mildly — old incidents unavailable |
| Scale to zero by default | Yes — cold start on every demo |
| No load balancer | Yes — public IP changes on task replacement |

Five of seven were free or better. The version with an ALB, NAT gateway and two services
would cost ~$80/month, be strictly more complex, and be *less* faithful to local development.

But note the discipline that goes with it: **optimise the dominant term.** Per-query Bedrock
spend is $0.017–$0.06; infrastructure is pennies. Agonising over a $0.50/month hosted zone
while each query costs $0.04 would be the wrong target. Cloud Map was skipped because it
bought nothing, *not* because it was expensive.

### P16. The concurrency model is a consequence of the work, not a free choice

`answer_query` is blocking and IO-heavy. Declaring the endpoint `async def` would block the
event loop and be strictly worse; declaring it `def` sends it to a threadpool, which is
correct — and which is precisely why the shared-state audit in
S02g - Concurrency and Shared State - Threadpools, Thread Safety, the Audit (Obsidian study note) was necessary.

You do not choose your concurrency model from taste. **The shape of the work chooses it, and
then you accept the consequences.**

### P17. Weigh care by the asymmetry of the failure

> Silent wrongness deserves more paranoia than a crash.

A shared mutable field produces *a wrong answer to a correct query* — intermittently, under
load, with no error and no traceback. In a financial RAG system that is close to the worst
available outcome, and it is strictly worse than a 500.

That asymmetry is what justified auditing rather than assuming. Conversely, the public IP
changing on task replacement is *visibly* broken, so it needs no defence — just documentation.

**Match the effort to the failure mode, not to the probability.**

### P18. Trust the artifact over the description

| Documented | Measured |
| :-- | :-- |
| Stage 2 parquet "500 MB – 2.3 GB" | **64,781,290 bytes** (~62 MiB), 614,787 rows |
| Task 0.25 vCPU / 512 MiB | needs **1,220 MiB** peak |
| ECR "~$1/month" | 0.643 GB → **$0.0643/month** |
| "Service Discovery: Free" | Route 53 private hosted zone bills monthly |

Every one of these was a one-line command against a claim that had sat in a document for
months. **Documentation drifts; artifacts do not.** When they disagree, the artifact wins —
and the document should be *corrected*, not quietly worked around.

### P19. Exercise the capability, do not enumerate it

`list-foundation-models` says a model exists. It does not say this account may invoke it. So
preflight **invokes** both models with a 2-token request.

Same shape elsewhere: `MapPublicIpOnLaunch` looks like "public" but reachability is a property
of the *route table*, so the code checks for a real IGW route. And the region list for a
cross-region inference profile came from `get-inference-profile`, not from an assumption —
it returned **three** regions, and a policy naming two would have failed intermittently.

> **Describing is not permitting. Listing is not invoking. Configuring is not reaching.**

---

## The two-line summary

If I had to compress all nineteen:

1. **Make the bad state unrepresentable; converge rather than create; and prove it by
   destroying and rebuilding.**
2. **Measure both halves, against the system's own noise floor, and label every number with
   how you know it.**

---

## Related notes

- S03 - Systems Walkthrough - Deploying a RAG Service to AWS (Obsidian study note) — the deployment itself
- S02g - Concurrency and Shared State - Threadpools, Thread Safety, the Audit (Obsidian study note) — the audit
- S02h - Measurement as a Design Practice (Obsidian study note) — the tools and their blind spots
- S02 INDEX - Curriculum and Answer Map (Obsidian study note) — the underlying curriculum

*Grounded in work verified 2026-07-31. Embedding, reranking and cost figures are from the
project's own notebooks; see the empirical methods document in
`ModelPipeline/finrag_ml_tg1/investigation_analysis/` for exact citations.*
