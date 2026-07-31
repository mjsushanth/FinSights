# S03 — Systems Walkthrough: Deploying a Stateful RAG Service to AWS

> **What this document is.** A walkthrough of one real deployment, written to teach the
> *shape* of the problem rather than the syntax of the tools. The example is FinSights —
> a FastAPI + Streamlit financial RAG system put onto AWS ECS Fargate on 2026-07-31 — but
> almost nothing here is specific to FinSights, and a good half of it is not specific to
> AWS either.
>
> **How to read it.** Part 1 sets up the five questions every deployment has to answer.
> Parts 2–6 answer them one at a time, each with the concrete decision we made and the
> reasoning behind it. Part 7 turns around and looks at the *deployment tool itself* as a
> piece of software design — that is where the object-design content lives. Parts 8–10 are
> cost, verification, and honest limitations.
>
> **Every number in here was measured or read back from a live account.** Where something
> is inferred rather than observed, it says so.
>
> Prerequisites, if you want them: S02a - Foundations - Processes, Namespaces, Containers (Obsidian study note)
> and S02b - Networking - Sockets, DNS, Bridges, Discovery (Obsidian study note). This document assumes them
> but re-states the load-bearing ideas as it goes.

### The four diagrams, and where they sit

Each one is embedded at the point in the argument where it does the most work, rather than
collected at the front. If you want to skim visually first, they are:

| Diagram | Appears in | Read it for |
| :-- | :-- | :-- |
| **D2 — Request path and the namespace boundary** | Part 4 | The single most important idea here: why `localhost` works between two containers, and why the backend has no door to the internet. Start here if you only look at one. |
| **D4 — What happens when you run `up`** | Part 6 | The 14-step sequence from empty account to serving task, with every idempotency decision marked and the one step that failed. |
| **D1 — The deploy control plane, end to end** | Part 7 | Nine modules, what each owns, and the specific December 2025 bug each exists to prevent. The broad overview. |
| **D3 — Module and class map** | Part 7.2 | The OOP layer: classes, key methods, and the direction dependencies are allowed to point. |

They are also standalone PNG and SVG files in this folder, and they regenerate from
`build_diagrams.py` in the repo — the geometry is computed, so editing content is a data
change rather than coordinate surgery.

---

## Part 0 — The thesis, in one sentence

> **Infrastructure that exists only in a cloud console is not infrastructure you own.**

Everything below is a consequence of taking that sentence seriously.

This project had already learned it the hard way. In December 2025 an earlier version of
FinSights ran publicly on ECS Fargate. It worked. It served real traffic. Someone
presented it at a Google office. Then the AWS account was closed, and the deployment
became unrecoverable — not because the code was lost, but because the *task definitions*
had been created by hand in the console. The GitHub workflow that "deployed" the system
could only read the live definition back, patch a new image URI into it, and re-register:

```bash
aws ecs describe-task-definition --task-definition finsights-backend-task \
  | jq 'del(.taskDefinitionArn, .revision, ...)' > task-def-clean.json
```

Read that carefully. It works *only while a previous revision already exists to be read*.
The repository held a patch script; AWS held the truth. When AWS forgot, nothing could
reconstruct it.

So the test of a deployment is not "does deploy work." It is:

> **Can you destroy the whole thing and rebuild it from the repository alone?**

We ran that test. It passed. Part 9 has the evidence.

---

## Part 1 — What kind of problem a deployment actually is

It is tempting to think of deployment as a transport problem: my code is here, it needs to
be there. That framing produces bad systems, because it hides the fact that a deployment
is really **five independent questions** that happen to be asked at the same time.

| # | Question | The name for it | Where it went wrong before |
| :-- | :-- | :-- | :-- |
| 1 | What is the unit that gets shipped, and what is inside it? | **Packaging** | Credentials baked into an image layer |
| 2 | Where does it run, and what does that placement cost? | **Placement** | 0.25 vCPU / 512 MiB — would have OOM-killed |
| 3 | How do the parts find each other? | **Wiring** | A Cloud Map hosted zone, billed monthly, for two processes on one machine |
| 4 | How does the code prove who it is to other services? | **Identity** | `BedrockFullAccess` + `S3FullAccess` behind a public endpoint |
| 5 | How does it start, stop, restart, and get replaced? | **Lifecycle** | The task definition existed nowhere in the repo |

These are genuinely independent. You can get packaging perfect and identity catastrophically
wrong. Most deployment confusion I have seen — including my own earlier reasoning on this
project — comes from answering two of them with one mechanism and not noticing.

Keep the table in mind. The next five parts are its five rows.

---

## Part 2 — Packaging: what is actually in the box?

### 2.1 The three channels, and why they are not interchangeable

Data reaches a container through exactly three channels, and they differ in *when* they
happen and *who can see them afterwards*:

| Channel | When | Persistence | Who can read it later |
| :-- | :-- | :-- | :-- |
| **Build time** — image layers | `docker build` | Permanent, published | Anyone who can pull the image |
| **Start time** — env vars, mounts | `exec` | Lives as long as the process | Anyone who can inspect the container |
| **Run time** — network fetch | During execution | Only in memory | Nobody, if you do it right |

Secrets must never use channel 1. This is not a style preference — an image layer is a
*published artifact*. A `.dockerignore` line is the only thing standing between a
credentials file and a public registry, and on this project that line had once been wrong:
a bare `aws_credentials.env` pattern matches only the context root, so the real file at
`finrag_ml_tg1/.aws_secrets/aws_credentials.env` was **verified baked into an image layer**
on 2026-07-30. The fix was `**/aws_credentials.env` — the `**/` is what recurses.

That is a two-character bug with a credential-disclosure blast radius. It is worth
internalising the asymmetry: build-time mistakes are permanent and public; start-time
mistakes are local and fixable.

### 2.2 The decision that surprised me: one image, not two

There was an obvious-looking design available — a `finrag_docker_loc_tg1/` directory for
local Dockerfiles and a `finrag_docker_loc_tg1_aws/` directory for cloud Dockerfiles. That
directory actually existed, with its own `backend.Dockerfile`, `frontend.Dockerfile` and
`docker-compose.yml`.

Inspecting them settled it. The `_aws` compose file still pointed its
`build.dockerfile` at `finrag_docker_loc_tg1/` — so it had never built the files sitting
beside it — and its inline `curl` health check would fail against the current runtime
images, which ship no `apt` layer and therefore no curl. They were December-era copies
that nothing referenced.

But the shallow finding ("they're dead") matters less than the deep one: **nothing about
the image needs to differ.** Everything that separates local from cloud is a start-time
input.

|  | Local | ECS |
| :-- | :-- | :-- |
| Credentials | static keys via compose `env_file` | task role, over the container credential endpoint |
| `BACKEND_URL` | `http://backend:8000` (compose DNS) | `http://localhost:8000` (shared namespace) |
| Health probe | honoured from the image `HEALTHCHECK` | restated in the task definition; image one ignored |

All three are injected. So:

> **If the image differs between local and cloud, the thing you tested is not the thing
> you deployed** — which is the entire property containers exist to provide. An
> environment-specific image is a contradiction in terms.

### 2.3 Multi-stage builds, and what "slim" buys you

The backend image is 889 MB locally, 378 MB compressed in ECR. It is built in two stages:
a builder stage that installs `uv` and resolves dependencies into `/opt/venv`, and a
runtime stage that copies only that venv. Neither pip, nor uv, nor any build toolchain
survives into the final image.

The second-order effect is the interesting one. Because the runtime stage has no `apt`
layer at all, **there is no curl** — so the health check had to become a Python probe:

```dockerfile
HEALTHCHECK CMD ["python", "-c", "import urllib.request,sys; \
  sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"]
```

That is a good example of how one decision propagates. "Make the image smaller" turned into
"rewrite the health check," which later turned into "restate the health check in the task
definition," which is what made container ordering work on Fargate at all.

---

## Part 3 — Placement: where it runs, and the arithmetic of that

### 3.1 Fargate bills per *task*, and that one fact drives the architecture

> Fargate charges per **task**, per second, on the **task-level** cpu and memory
> reservation. Not per container. Not on actual usage.

Two consequences fall straight out:

- A second **container** inside the same task is nearly free.
- A second **task** doubles the compute bill.

Verified rates, us-east-1, read from the AWS Pricing API on 2026-07-31 (the usage types
carry a region prefix — `USE1-Fargate-ARM-vCPU-Hours:perCPU` — which is why an unprefixed
query returns nothing at all):

| Rate | x86_64 | ARM64 (Graviton) | ARM saving |
| :-- | --: | --: | --: |
| per vCPU-hour | $0.040480 | **$0.032380** | 20.01% |
| per GB-hour | $0.0044450 | **$0.0035600** | 19.91% |

There is also a **floor**: the smallest Fargate task is 0.25 vCPU / 0.5 GB. You cannot buy
less. So task *count* is the cost variable, and consolidation is the lever.

### 3.2 Sizing from measurement, not from the documentation

The existing documentation specified 0.25 vCPU / 512 MiB. Measured reality, sampling
`docker stats` against real queries on the local ARM images:

| | Idle | Simple query | 10-company query |
| :-- | --: | --: | --: |
| Backend | 213 MiB | 1,139 MiB | **1,220 MiB** |
| Frontend | 146 MiB | 146 MiB | 146 MiB |

The documented shape would have been OOM-killed on the first query. Chosen instead:
**1 vCPU / 3072 MiB**, split 2560 / 384 as soft reservations — roughly 2× headroom over
observed peak without stepping up a cpu tier.

Two things worth extracting from that table beyond the number:

1. **The frontend never moves.** 146 MiB idle, 146 MiB under load. That is not luck; it is
   what "pure HTTP client" means when it is true. It also justifies giving it only 384 MiB.
2. **The backend loads lazily.** 213 MiB at rest versus 1,220 MiB under query means the ML
   components are constructed on demand, not at import. That is a design fact you could not
   have learned from reading the code quickly, and it changes what caching would buy you
   (see Part 10).

### 3.3 Why ARM64, and the reason that mattered most

The 20% saving is real — $7.85/month at 24/7 for this shape. But it was the *third* reason.

The first: **the build host is an Apple Silicon Mac, so ARM64 is the native build.** x86
would have meant QEMU emulation on every build — several times slower, with a class of
failures that appear only under emulation. The second: **the risk was already retired.**
The local images were aarch64 and had already served two real queries before anything was
deployed, so the entire dependency set was known to work on ARM. Adopting it cost nothing.

The general lesson is about *sequencing evidence*. ARM was a safe choice not because ARM is
safe, but because we happened to have already proven it for free. Had the local machine
been x86, the honest answer would have been "deploy x86, revisit later."

### 3.4 Public subnets, and the $32.85 that never got spent

> Public versus private is a property of the **route table**, not of the subnet.

All six subnets in the default VPC are associated with a route table whose `0.0.0.0/0`
route points at an internet gateway. An internet gateway is **free**. A task placed there
with `assignPublicIp: ENABLED` gets the outbound access it needs to reach Bedrock and S3 at
no charge.

Private subnets would need a NAT gateway for that same egress: **~$32.85/month per
availability zone, plus $0.045/GB**. That single choice would have cost more per month than
all the compute this deployment is expected to use.

Because the distinction is the route table, the code verifies the route table:

```python
has_igw = any(route.get("GatewayId", "").startswith("igw-")
              for route in table.get("Routes", []))
```

`MapPublicIpOnLaunch` is *not* proof, and a subnet with no explicit association inherits
the VPC's main table — so a subnet explicitly bound to a private table must not be accepted
just because the main table happens to be public. That distinction was a real bug in my
first draft of this function, and it is the kind of thing that works in every account you
test and fails in the one that matters.

---

## Part 4 — Wiring: how two processes find each other

This is the part with the most interesting answer, and the diagram below is the one to sit
with.

![D2-request-path.png](diagrams/D2-request-path.png)

### 4.1 Three options, and the trap in the middle one

| Option | Mechanism | Standing cost |
| :-- | :-- | --: |
| **A. One task, two containers** | shared network namespace → `localhost` | **$0** |
| B. Two services + Cloud Map | private DNS, `backend.finsights.local` | ~$0.50/mo hosted zone + a second task |
| C. Two services + ALB | load balancer with target groups | ~$16.43/mo + a second task |

Option B looks like the sophisticated middle ground. It is a trap, and the reason is worth
understanding properly:

> **DNS-based service discovery solves *churn*, not *distribution*.** It gives you a stable
> name for a moving target. It does **not** balance load — resolvers cache per TTL, clients
> hold connections open, and a DNS answer carries no information about which backend is
> busy.

So option B's headline benefit — independent scaling — cannot actually be *delivered* by
option B. To use N backend replicas you need something that distributes across them, which
means option C, which means $16.43/month. B is a monthly bill for a capability that only
becomes useful once you also pay for C.

Option A won on cost. But it also won on **capability**, which is the part I did not expect:

> ECS cannot express startup ordering between two **services** — it reconciles them
> independently and continuously, forever. It *can* express ordering between two
> **containers inside one task**, via `dependsOn: {condition: HEALTHY}`.

The local `docker-compose.yml` says `depends_on: {backend: {condition: service_healthy}}`.
Co-locating is the only one of the three options that preserves that semantic. The cheapest
option was also the only faithful one.

### 4.2 `localhost` does not mean what you probably think

This is the load-bearing idea in the whole document.

> **`localhost` means "this network namespace," not "this machine."**

A network namespace is a kernel-enforced perception boundary: an independent set of
interfaces, routing tables, and port space. Two containers in one ECS task share **one**
network namespace. Therefore they share one loopback interface. Therefore
`http://localhost:8000` from the frontend reaches the backend — and reaches *nothing else
in the account*, because there is no route from outside into a namespace's loopback.

The proof, from the deployed container's own log:

```
INFO: 127.0.0.1:34932 - "POST /query HTTP/1.1" 200 OK
```

That source address is not a detail. It is the entire cost argument, observed. No load
balancer, no service discovery, no hosted zone, no DNS — and the request still arrived.

### 4.3 The security property that falls out for free

The December security group allowed **tcp/8000 from 0.0.0.0/0**. The backend's `/query`
endpoint spends real Bedrock money per call and has no authentication and no rate limit. So
that rule left a paid endpoint open to anyone who found the IP, at roughly $0.017–$0.06 a
call.

Co-location closes it at zero cost. The backend listens on the task's loopback interface;
there is no rule to write because there is no path to block. The security group has exactly
one ingress rule, for the Streamlit port.

Note the asymmetry, because I got this wrong once and had to be corrected: the public
**frontend** is correct and intended — the RAG UI *is* the product. The narrower problem was
that the paid API was *separately* reachable. Those are different claims, and conflating
them turns a precise security observation into vague alarm.

The verification step asserts the property positively rather than assuming it:

```
[PASS] frontend health      HTTP 200
[PASS] backend not public   no route from the internet, as designed
```

If that second check ever passes as reachable, the hole is back.

---

## Part 5 — Identity: how code proves who it is

### 5.1 The chain, and why "use an IAM role" is not a code change

boto3 resolves credentials by walking an ordered chain:

```
1. explicit constructor arguments
2. environment variables            (AWS_ACCESS_KEY_ID, ...)
3. shared credentials file          (~/.aws/credentials)
4. shared config file               (~/.aws/config)
5. ECS container credentials  ->  HTTP GET to 169.254.170.2
                                   at $AWS_CONTAINER_CREDENTIALS_RELATIVE_URI
6. EC2 instance metadata      ->  HTTP GET to 169.254.169.254
```

Steps 5 and 6 are link-local addresses — non-routable, answered by the infrastructure
itself. Which means:

> Switching from static keys to an IAM role is a **deployment** change, not a code change.
> The application does not know the difference. It calls `boto3.client(...)` either way.

FinSights already had the detection:

```python
if os.getenv('AWS_EXECUTION_ENV') or os.getenv('AWS_LAMBDA_FUNCTION_NAME') \
   or os.getenv('ECS_CONTAINER_METADATA_URI'):
    self._aws_creds_source = "IAM_ROLE"
    return   # boto3 will automatically use the attached IAM role
```

One hardening step was needed, and it is a nice example of a fragile check. That code looks
for `ECS_CONTAINER_METADATA_URI`, but modern Fargate platform versions inject the **v4**
name, `ECS_CONTAINER_METADATA_URI_V4`. Rather than depend on platform-version trivia, the
task definition sets `AWS_EXECUTION_ENV=AWS_ECS_FARGATE` explicitly. One line of config
against a failure that would otherwise surface as the container hunting for a credentials
file that is deliberately not in the image.

**Verified in the deployed container:**

```
[DEBUG] AWS containerized environment detected (ECS/Lambda) - using IAM role
[DEBUG] Container detected -> S3_STREAMING mode
[DEBUG: S3StreamingLoader] Using temp cache: /tmp/finrag_cache
```

### 5.2 The risk I could not reason my way out of

Here is a case where measurement was the only option.

Polars does not use boto3. It reads S3 through the Rust `object_store` crate, which does its
**own** credential resolution. So "boto3 finds the task role" did **not** imply "Polars finds
the task role," and the failure mode would have been vicious: it would work at startup and
fail on the *first query*, because the tables are read lazily.

I flagged it UNVERIFIED and deployed anyway, because the only way to answer it was to try.
It worked — `S3StreamingLoader` read its tables under a bare task role with no static
credentials present.

The transferable habit: **when two subsystems resolve the same thing by different
mechanisms, you have two problems, not one.** Enumerate them, label the unknown one, and
design the test that distinguishes them.

### 5.3 Least privilege, and the cross-region inference trap

The old task role carried `AmazonBedrockFullAccess` + `AmazonS3FullAccess`. Between them:
every Bedrock action on every model, and every S3 action on every bucket in the account —
including `DeleteObject` on the embedding tables that cost days of compute to regenerate.

The replacement has five statements, no wildcard actions, and no `Delete` anywhere:

| Sid | Grants |
| :-- | :-- |
| `BedrockInvokeOnly` | 2 invoke actions on 5 specific ARNs |
| `S3ReadCorpusAndTables` | `GetObject` on one bucket |
| `S3ListForPolarsScan` | `ListBucket`, `GetBucketLocation` — Polars lists a prefix before reading parts |
| `S3WriteQueryLogsOnly` | `PutObject` under `DATA_MERGE_ASSETS/LOGS/FINRAG/*` only |
| `S3VectorsQueryOnly` | `QueryVectors`, `GetVectors`, `GetIndex` — no `PutVectors` |

Now the trap. `us.anthropic.claude-haiku-4-5-20251001-v1:0` is **not a foundation model**.
The `us.` prefix makes it a *cross-region inference profile* that fans requests out across
regions. Invoking it requires permission on two different kinds of resource:

```
arn:aws:bedrock:us-east-1:908877262866:inference-profile/us.anthropic.claude-haiku-4-5-...
arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-...
arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-...
arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-...
```

Note the **empty account field** on the foundation-model ARNs — those are account-agnostic.
And note there are three regions. Grant only the profile, or only `us-east-1`, and you get
the worst possible failure: it works most of the time and throws `AccessDeniedException`
whenever Bedrock happens to route elsewhere. An intermittent permissions bug is far more
expensive to diagnose than a total one.

The region list was **read from the API**, not guessed:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier "us.anthropic.claude-haiku-4-5-20251001-v1:0"
# "Routes requests to Anthropic Claude Haiku 4.5 in us-east-1, us-east-2 and us-west-2."
```

### 5.4 Two roles, because there are two assumers

This confused me for a while, so it is worth stating plainly:

| Role | Assumed by | When | Purpose |
| :-- | :-- | :-- | :-- |
| **Execution role** | the ECS agent | *before* the container exists | pull the image from ECR, open the log stream |
| **Task role** | your application process | at request time | call Bedrock, S3, S3 Vectors |

They are not interchangeable and they are not alternatives. The execution role is the
correct place to use an AWS managed policy — `AmazonECSTaskExecutionRolePolicy` grants
exactly the agent's job and nothing more. The task role is the one that must be narrow,
because it is the one a compromised request handler would be holding.

There is also a third, easily-missed role — see Part 6.4.

---

## Part 6 — Lifecycle: start, stop, replace, rebuild

![D4-up-sequence.png](diagrams/D4-up-sequence.png)

### 6.1 The four ECS objects, disambiguated

| Object | What it is | Analogy |
| :-- | :-- | :-- |
| **Task definition** | an immutable, versioned *specification* | a class |
| **Task** | one running instance of that spec | an object |
| **Service** | a controller that keeps N tasks running | a supervisor / ReplicaSet |
| **Cluster** | a namespace for accounting and grouping | a folder |

The word "namespace" is now doing at least three unrelated jobs in this stack, and keeping
them apart matters:

| "Namespace" | What it enforces |
| :-- | :-- |
| Linux namespace | a real, kernel-enforced perception boundary |
| ECS cluster | nothing — an accounting label |
| Cloud Map namespace | a DNS suffix |

Only the first one enforces anything.

### 6.2 Why the scheduling unit is bigger than the container

Fargate schedules *tasks*, not containers, and that is not an arbitrary choice — it is a
lineage. Google's Borg had **allocs**: co-scheduled bundles of processes that share
resources. Kubernetes inherited that as the **pod**. ECS calls it a **task**.

The reason is empirical: production processes come in bundles. A server plus its log
shipper. A server plus its metrics sidecar. A frontend plus its backend. Making the
scheduling unit exactly one container would mean the scheduler could split things that must
be co-located. So every serious orchestrator has an abstraction one level above the
container — and that abstraction is precisely what makes the `localhost` wiring in Part 4
possible.

### 6.3 Fargate is a container API over a VM, and it leaks

Fargate gives you the container *programming model* on top of **Firecracker micro-VM**
isolation. That mismatch explains a cluster of otherwise-arbitrary restrictions:

- no bind mounts, no named volumes, no privileged mode
- slower cold starts than a container on a warm host
- **the image's `HEALTHCHECK` instruction is ignored entirely**

That last one is worth dwelling on, because its symptom is confusing. A container whose only
probe lives in the Dockerfile reports `healthStatus: UNKNOWN` **forever** on Fargate. And
`dependsOn: {condition: HEALTHY}` against an UNKNOWN container is never satisfied — so the
dependent container never starts, and you get a task that is "running" and does nothing.

Hence both probes are restated in the task definition. (A transient `UNKNOWN` right after
launch is normal — it just means the `startPeriod` has not elapsed. A *permanent* one is the
signature of this bug.)

### 6.4 The failure that no document warns you about

The first `up` failed here:

```
InvalidParameterException: Unable to assume the service linked role.
Please verify that the ECS service linked role exists.
```

A **service-linked role** is a role in your account that an AWS service assumes to act on
your behalf — here, so ECS can manage elastic network interfaces. It is not the execution
role and not the task role; it belongs to the *service*, not to the workload.

The console creates it silently the first time anyone opens the ECS page. Which is exactly
why this error is almost never seen: anyone testing a deployment script has usually clicked
through the console once already, so the role exists before their script runs. Doing
everything through the API on a genuinely untouched account is what exposes it.

This is the concrete, specific reason the old `setup-infrastructure.yml` claim to work on
"a completely fresh AWS account" was false. It never created this role, so its very first
ECS call would have failed the same way.

```python
try:
    client.create_service_linked_role(AWSServiceName="ecs.amazonaws.com")
    time.sleep(10)                      # not immediately assumable
except (client.exceptions.InvalidInputException,        # <- existing role reports
        client.exceptions.EntityAlreadyExistsException):  #    InvalidInput, not
    pass                                                 #    AlreadyExists
```

Note the API inconsistency in that except clause. An *existing* service-linked role is
reported as `InvalidInput`, not `EntityAlreadyExists`. Cloud APIs are full of this, and it
is why "guard" logic has to be written against observed behaviour rather than expected
behaviour.

### 6.5 Three postures, and why `down` is genuinely free

> There is **no stopped-container charge** on Fargate, because there is no stopped
> container. The micro-VM is destroyed.

| Posture | Compute | Standing | Recovery |
| :-- | --: | --: | :-- |
| Running | $0.04306/hr | — | — |
| `down` (desired count 0) | **$0** | $0.064/mo (ECR) | `up --no-build`, ~1 min |
| `destroy` | $0 | **$0** | `up`, ~7 min (rebuilds images) |

The $0.064 is measured, not estimated: 0.643 GB of compressed layers in ECR at $0.10/GB-month.

Having both verbs matters. `down` is what you use daily. `destroy` exists because "almost
zero" is not zero, and because — as Part 9 argues — being *able* to destroy is the only
real proof the rebuild path works.

---

## Part 7 — The control plane as software

Everything so far was about the deployed system. This part is about the *tool that deploys
it*, which turned out to be the more interesting piece of design.

![D1-control-plane.png](diagrams/D1-control-plane.png)

### 7.1 Why this is a Python package and not a YAML workflow

The December deployment lived in two GitHub Actions YAML files. They could not be executed,
inspected, or dry-run locally; their failure output was a web page; and their idempotency
was expressed in shell conditionals that could not be unit tested.

Every bug later found in them — the cluster-name mismatch, the non-atomic IAM guard, the
describe-then-patch task definition — **would have been visible if the logic had been
runnable on a laptop.**

So the logic is a Python package, and CI *calls* it rather than reimplementing it. That is
the whole relationship: the button in GitHub runs `python -m deploy_aws.cli up`, the same
command you run locally. There is exactly one implementation of the deployment.

### 7.2 The five kinds of module

![D3-module-map.png](diagrams/D3-module-map.png)

Eight modules, but only **five kinds**, and the kind determines everything about how you
test it:

| Kind | Module | Does I/O? | How you test it |
| :-- | :-- | :-- | :-- |
| **Data** | `config.py` | no | construct it and assert |
| **Pure transform** | `policies.py`, `taskdef.py` | no | call it, assert on the returned dict |
| **Access** | `aws_session.py` | yes, but only to authenticate | one integration test |
| **Effect** | `provisioner.py`, `images.py`, `service.py` | yes, extensively | integration only |
| **Wiring** | `cli.py` | no logic of its own | end to end |

The valuable part is that **the two most error-prone artifacts — the IAM policy and the task
definition — are in the "pure transform" row.** They take a config and an account id and
return a dict. No network, no state, no ordering. That means the hardest things to get right
are also the easiest things to check, which is not a coincidence; it is the point of putting
them there.

Each module's `__main__` block exercises it without creating anything:

```python
for statement in doc["Statement"]:
    for action in statement["Action"]:
        assert not action.endswith(":*"), f"service wildcard in {statement['Sid']}"
        assert "Delete" not in action,    f"delete granted in {statement['Sid']}"
```

A security property, asserted as a test, runnable offline, in four lines.

### 7.3 Dependency injection, stated without the jargon

> **Nothing constructs its own collaborators.**

`Provisioner` is *handed* an `AwsSession`. `AwsSession` is *handed* a `DeployConfig`.
Neither reaches out and builds what it needs.

```python
class Provisioner:
    def __init__(self, aws: AwsSession, log: Optional[logging.Logger] = None) -> None:
        self._aws = aws
        self._config = aws.config          # <- borrowed, never rebuilt
        self._policies = IamPolicies(aws.config)
```

Two payoffs, and only the second one is usually mentioned:

1. A test can pass a fake session.
2. **The dependency graph becomes readable.** You can determine what `Provisioner` touches
   by reading its constructor. In the alternative design — where each module calls
   `boto3.client()` for itself — you would have to read every method to find out.

The config being a **frozen** dataclass compounds this. Two modules cannot disagree about a
resource name, because neither can change it. That single property makes the December
`finsights-cluster` vs `finsights-cluster-new` bug *unrepresentable* rather than merely
unlikely — and "unrepresentable" is always the better engineering target.

### 7.4 The cached-client pattern

```python
@property
def session(self) -> boto3.Session:
    if self._session is None:
        self._session = boto3.Session(...)     # built once, on first use
    return self._session

def client(self, service: str) -> Any:
    if service not in self._clients:
        self._clients[service] = self.session.client(service, config=self._boto_config)
    return self._clients[service]
```

Three separate ideas are doing work here:

- **Lazy**: nothing happens at import. A module can be imported to read its docstring
  without authenticating to anything.
- **Cached**: `client("ecs")` returns the same object every time. Client construction parses
  a service model from disk — it is not free, and doing it per call is a real cost.
- **Centralised retry config**: one `BotoConfig` with 8 standard-mode attempts covers every
  client. `CreateService` and `RegisterTaskDefinition` are both throttled APIs, and IAM is
  eventually consistent, so a freshly created role is briefly unassumable. Configuring that
  in one place instead of at fourteen call sites is the entire reason to have this class.

The general shape — *a resource that is expensive to create, immutable once created, and
needed by many collaborators, wrapped in an object that owns its lifetime* — is one of the
highest-leverage patterns in systems code. Database connection pools are the same shape.

### 7.5 Subprocess as a typed method

`docker` has no Python API worth using here, so it gets driven as a subprocess — but wrapped
so that callers never see that:

```python
def _run(self, command: List[str], step: str) -> None:
    result = subprocess.run(command, cwd=str(self._context),
                            capture_output=True, text=True)
    if result.returncode != 0:
        # docker writes progress to stderr, so the TAIL of stderr is the error
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-25:])
        raise RuntimeError(f"{step} failed (exit {result.returncode}):\n{tail}")
```

The design content is in the details:

- **A list, not a string.** No shell, so no quoting bugs and no injection surface.
- **A `step` label.** The exception says *which* build failed, not just that one did.
- **The tail, not everything.** Docker emits thousands of progress lines; the last 25 are
  where the error is.
- **Failure becomes an exception**, so callers use `try`/`except` rather than checking
  return codes — the subprocess boundary stops leaking upward.

And the credential handling in `docker_login` is worth copying verbatim as a habit:

```python
subprocess.run([...,"--password-stdin", registry], input=password, ...)
```

Passing a secret on **stdin** rather than as an argv element keeps it out of the process
table, where any other user on the machine could read it with `ps`.

### 7.6 Idempotency: the rule, and the bug it comes from

This is the single most transferable idea in the project.

The December workflow guarded IAM creation like this:

```bash
if aws iam get-role --role-name "$ROLE" 2>/dev/null; then
  echo "exists"                      # <- checks ONE thing
else
  aws iam create-role ...            # <- but does TWO things
  aws iam attach-role-policy ...
fi
```

Find the bug before reading on.

The guard tests whether the **role** exists, but the body performs **two** operations. If
`create-role` succeeded and `attach-role-policy` then failed — a throttle, a cancelled
workflow run, a transient error — the role now exists with **no policy attached**. Every
subsequent run takes the "exists" branch, prints a reassuring message, and never repairs
it. The failure surfaces much later as `AccessDenied` from inside a running container, a
very long way from its cause.

The rule that prevents the entire class:

> **Guard only the operation that is genuinely not idempotent. Let naturally idempotent
> operations run unconditionally on every invocation.**

| Operation | Idempotent? | Treatment |
| :-- | :-- | :-- |
| `CreateRole` | no (`EntityAlreadyExists`) | **guard it** |
| `AttachRolePolicy` | yes — describes an end state | **never guard it** |
| `PutRolePolicy` | yes — full replace | **never guard it** |
| `PutRetentionPolicy` | yes | **never guard it** |
| `authorize_security_group_ingress` | no, but duplicate is benign | catch `InvalidPermission.Duplicate` |
| `CreateCluster` | yes — returns the existing one | just call it |

Running the idempotent ones every time is not wasteful. **It is the self-heal.** A role left
half-built by a crashed run is repaired on the next invocation, automatically, with no
special recovery path — because there is no "create" path and "repair" path, there is only
"converge."

The mental shift: stop writing code that *creates* infrastructure. Write code that
*converges* infrastructure toward a description. Then a failed run is just a run that has
not finished converging yet.

The inverse applies to teardown: every `delete_*` tolerates absence, so a partially-built
stack can still be torn down completely.

### 7.7 Choosing an inline policy over a managed one

A small decision with a good reason:

```python
client.put_role_policy(RoleName=..., PolicyName=..., PolicyDocument=...)
```

`PutRolePolicy` is a **full replace**. So editing `policies.py` and re-running converges the
live policy to the file — no versioning, no detach step, no drift. A managed policy would
need version management and could be attached to other principals by accident. The inline
policy is versioned by *git*, which is where you actually want the history.

---

## Part 8 — Cost as an architectural force

Most architecture writing treats cost as an afterthought. On a personal project it is a
**primary design input**, and it produces better systems, not worse ones.

The constraint here was explicit: never adopt anything costing ~$17/month. Watch what that
single constraint decided:

| Decision | Cost-driven? | Did it hurt quality? |
| :-- | :-- | :-- |
| One task, two containers | yes — avoided ALB | **No** — it is the only option preserving `depends_on` |
| Public subnets, no NAT | yes — avoided $32.85/mo | No — the workload needs egress, not inbound privacy |
| `localhost` over Cloud Map | yes — avoided $0.50/mo | No — removed a DNS failure mode entirely |
| ARM64 | partly — 20% | No — also the native build |
| 7-day log retention | yes | Mildly — 8-day-old incidents are unavailable |
| Scale to zero by default | yes | Yes — a cold start on every demo |
| No load balancer | yes | Yes — the public IP changes on every task replacement |

Five of seven cost decisions were **free or better**. Two involved real trade-offs, and both
are honest ones a reader can evaluate.

The general claim: **a tight cost constraint is a forcing function that removes options you
did not need.** The version of this system with an ALB, a NAT gateway, and two services
would cost ~$80/month, be strictly more complex, and — because of the `depends_on` point —
be *less* faithful to the local development setup.

Note also which costs are *not* on that list. Bedrock spend of $0.017–$0.06 per query
dwarfs the infrastructure at any real usage level. Optimising a $0.50/month hosted zone
while each query costs $0.04 would be the wrong target — the reason to skip Cloud Map was
that it bought nothing, not that it was expensive.

---

## Part 9 — How you know it works

### 9.1 A health check that cannot fail proves nothing

```python
@app.get("/health")
async def health():
    return {"status": "healthy", "aws_configured": None}   # hardcoded
```

This returns `healthy` unconditionally. It cannot fail. Therefore it **cannot confirm
anything**, and using it as a deploy gate is theatre.

The distinction to internalise:

| Probe | Question | May check dependencies? |
| :-- | :-- | :-- |
| **Liveness** | is the process wedged? | **No** — a dependency blip becomes a restart storm |
| **Readiness** | can it serve traffic *now*? | **Yes** — that is the point |
| **Startup** | has it finished booting? | usually not |

Conflating liveness and readiness is how a brief S3 hiccup turns into an outage: every
replica fails its liveness probe simultaneously, gets killed, and the restarts hit S3 harder.

### 9.2 So the real test is a real query

```
Query successful: cost=$0.0140, tokens=12670, time=9631ms
INFO: 127.0.0.1:34932 - "POST /query HTTP/1.1" 200 OK
```

That one line exercises the task role, Bedrock, S3, S3 Vectors, and the `localhost` wiring
simultaneously. Nothing short of it would have caught a Polars credential failure, because
that failure occurs on the *first query*, not at startup.

A small confession about process, because it is instructive. While waiting for this, I set
up a monitor loop grepping the logs for `IAM_ROLE`. The log actually says `IAM role` — with
a space, lowercase. I waited five minutes on a pattern that could never match, while the
query had already succeeded. **A verification tool that is silently broken is worse than no
verification tool**, because it manufactures false confidence. Check that your check works.

### 9.3 Destroy and rebuild is the only completeness test

Any test short of this can pass on a system that is secretly dependent on state nobody
recorded. So:

```
destroy  ->  6/6 resource checks empty  ->  up  ->  steady state again as revision 2
```

| Check after destroy | Result |
| :-- | :-- |
| ECR repositories | empty |
| ECS clusters | empty |
| Active task definitions | empty |
| Log groups | empty |
| IAM roles | empty |
| Security group | empty |

Then `up` reconstructed everything from the repository alone.

> **Pets versus cattle.** If you cannot destroy and rebuild it, you do not have
> infrastructure as code — you have a console with a backup script. Destroy-and-rebuild is
> not a disaster-recovery drill; it is the *unit test* for whether your description is
> complete.

### 9.4 Verified versus asserted

A discipline worth carrying into everything: label claims by how you know them.

| Claim | Status | How |
| :-- | :-- | :-- |
| Both Bedrock models usable | VERIFIED | invoked them |
| Polars resolves the task role | VERIFIED | real query read real tables |
| Task memory sizing | VERIFIED | sampled during real queries |
| ARM 20% cheaper | VERIFIED | Pricing API |
| ECR standing cost | VERIFIED | `describe-images`, measured bytes |
| Latency by query class | PARTLY | 3 samples for the simple class; complex classes from prior experience |

The first version of this document listed ARM pricing as UNVERIFIED because my Pricing API
query returned nothing. The query was wrong — Fargate usage types carry a region prefix.
The lesson is not "I was wrong about the price," it is that **"my tool returned nothing" and
"the data does not exist" are different conclusions**, and conflating them produces a
confident gap.

---

## Part 10 — What this still gets wrong

An honest system description ends here rather than at the success.

**1. `/health` is not a readiness probe.** It cannot fail, so `dependsOn: HEALTHY` is a
weaker guarantee than it appears. A probe that actually checks Bedrock and S3 reachability
would make container ordering mean something.

**2. The per-request rebuild is real but small.** Every request reconstructs its components.
Measured inside the running container:

| Constructor | Steady-state time |
| :-- | --: |
| `init_rag_components()` | 592 ms |
| `PromptLoader()` | 92 ms |
| `QueryLogger()` | 71 ms |
| `MLConfig()` | 65 ms |
| `create_bedrock_client_from_config()` | 4 ms |
| **Total** | **~825 ms** |

Against a 9.6 s simple query that is 8.6%; against a 50 s complex query, 1.6%. And
`tracemalloc` showed each constructor allocating **under 1 MiB** of Python memory — so the
~900 MiB per-query jump is native Polars/Arrow buffers doing real work, and **caching the
constructors would not reduce the task size at all.**

This corrects something I had earlier implied. I had suggested a large table was being
loaded per request as construction cost. The measurement says construction is cheap and the
memory is in context assembly. Worth fixing for design cleanliness; not a performance
necessity. The actual work is not the cache — it is auditing whether those four components
hold per-request state, because sharing a stateful object across the FastAPI threadpool
would corrupt answers under concurrency.

**3. Latency is characterised, not modelled.** 9.6–14.1 s simple, 50 s+ for multi-year
cross-comparisons, up to ~4 minutes for very large KPI-heavy queries. The retrieval pipeline
is roughly constant at 5–6 s; **everything above that is the LLM generating tokens**. That
4-minute worst case is also, incidentally, the clearest reason Lambda was never viable —
API Gateway caps an integration at about 29 s.

**4. The public IP changes on every task replacement.** Real cost of having no load
balancer. Acceptable while the deployment is demo-driven; not acceptable if anyone ever
bookmarks it.

**5. `ml_config.yaml` contains dead configuration** — a `vector_search:`/`llm:` block naming
a nonexistent index and an inaccessible model. Nothing reads it (the only consumer is
commented out in a `_v1bkp` file), but it will mislead the next reader. Left in place as
out-of-scope, flagged here deliberately.

---

## Appendix A — every verified number

| Quantity | Value |
| :-- | :-- |
| Account / region | 908877262866 / us-east-1 |
| Task shape | 1 vCPU / 3072 MiB, ARM64 |
| Container reservations | backend 2560 MiB, frontend 384 MiB |
| Backend memory: idle / simple / heavy | 213 / 1,139 / **1,220** MiB |
| Frontend memory (any load) | 146 MiB |
| Backend cold start to healthy | ~5 s |
| Deployed query | $0.0140, 12,670 tokens, 9,631 ms |
| Fargate ARM | $0.032380/vCPU-hr, $0.0035600/GB-hr |
| Fargate x86 | $0.040480/vCPU-hr, $0.0044450/GB-hr |
| This shape, hourly | $0.04306 ARM vs $0.053815 x86 |
| ECR stored (both images) | 0.643 GB → $0.0643/month |
| Per-request construction | ~825 ms |
| Fargate vCPU quota | 30 |
| Subnets / AZs / NAT gateways | 3 / 3 / **0** |

---

## Appendix B — the transferable checklist

Things from this project that apply to the next one, cloud-agnostic:

- [ ] Can I destroy everything and rebuild from the repo alone? If not, I am not done.
- [ ] Is every resource name in exactly one place, immutable?
- [ ] Have I guarded only the non-idempotent calls, and left the rest unconditional?
- [ ] Does every teardown step tolerate the resource already being absent?
- [ ] Are secrets reaching the process at *start* time or *run* time, never *build* time?
- [ ] Is the identity of the running code a deployment property, not a code property?
- [ ] Are the two hardest-to-get-right artifacts pure functions I can test offline?
- [ ] Does my smoke test exercise a path that could actually fail?
- [ ] Have I checked that my check works?
- [ ] Is every number in my documentation measured, or labelled as not measured?
- [ ] For anything expensive-and-immutable: does one object own its lifetime?
- [ ] Have I written down what the system still gets wrong?

---

## Related notes

- S02 INDEX - Curriculum and Answer Map (Obsidian study note) — the curriculum this sits on top of
- S02a - Foundations - Processes, Namespaces, Containers (Obsidian study note) — namespaces, cgroups, images
- S02b - Networking - Sockets, DNS, Bridges, Discovery (Obsidian study note) — why DNS is not a load balancer
- S02c - AWS Substrate - EC2, VPC, Subnets, NAT, ECR (Obsidian study note) — route tables, NAT, ECR
- S02d - ECS Anatomy - Tasks, Services, Fargate (Obsidian study note) — the four objects, Borg lineage
- S02e - Credentials and Config - Injection, IMDS, Loaders (Obsidian study note) — the credential chain
- S02f - Serving and Production - Processes, Health, Cost (Obsidian study note) — liveness vs readiness, cost

**Source of truth for everything here:** `ModelPipeline/deploy_aws/` and
`ModelPipeline/finrag_docker_loc_tg1_aws/ECS_FARGATE_RUNBOOK.md` in the FinSights repo.
Diagrams regenerate from `finrag_docker_loc_tg1_aws/diagrams/build_diagrams.py`.

*Written 2026-07-31 against the working deployment.*
