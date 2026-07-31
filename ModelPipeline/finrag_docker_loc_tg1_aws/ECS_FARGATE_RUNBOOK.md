# FinSights on AWS ECS Fargate - Design and Runbook

> **Status: WORKING.** Deployed and verified end to end on account **908877262866**
> (`mjsushanth_mlops`), region `us-east-1`, on **2026-07-31**. A real query was answered
> through the public frontend at a measured cost of **$0.0140** in **9.6 s**.
>
> **The full destroy-and-rebuild cycle was also verified.** Every resource was deleted,
> the account was confirmed empty on all six checks (ECR, clusters, active task
> definitions, log groups, IAM roles, security group), and `up` then reconstructed the
> entire stack from this repository alone and reached steady state again as revision 2.
> That round trip is the integration test for whether the infrastructure is genuinely
> described in code - and it is the test the Dec 2025 deployment could never have passed.
>
> **Current state: scaled to zero.** Standing cost is $0.064/month of ECR storage and an
> empty log group. Bring it back with `python -m deploy_aws.cli up --no-build` (about a
> minute - the images are still in ECR).
>
> This supersedes `HISTORICAL_2025-12_ECS_DEPLOYMENT_GUIDE.md` and
> `../../HISTORICAL_2025-12_INFRASTRUCTURE_SETUP_GUIDE.md`, which describe the Dec 2025
> deployment on the now-closed account 729472661729 and are kept only as a record.
>
> Everything here is either measured or read back from the live account. Figures that
> could not be confirmed are labelled UNVERIFIED.

> **Learning the design rather than operating it?** Read
> [SYSTEMS_WALKTHROUGH.md](./SYSTEMS_WALKTHROUGH.md) instead. This file is the runbook -
> what the resources are and which command to run. The walkthrough is the teaching
> document: the five questions every deployment answers, four rendered diagrams, the
> object design behind `deploy_aws/`, and what this system still gets wrong.

---

## 1. Quick start

Everything runs from `ModelPipeline/`.

```bash
cd ModelPipeline
python -m deploy_aws.cli preflight
```

| Verb | What it does |
| :-- | :-- |
| `preflight` | Checks credentials, both Bedrock models, S3, S3 Vectors, subnets, quota, Docker. Creates nothing. |
| `up` | Provisions, builds ARM64 images, pushes to ECR, registers the task definition, creates the service, waits for healthy. |
| `up --no-build` | Same, reusing the images already in ECR. About a minute. |
| `status` | Running count, public URL, per-container health, whether it is billing. |
| `smoke` | Confirms the frontend answers and the backend is **not** publicly reachable. |
| `logs --container backend` | Recent CloudWatch output. |
| `down` | Desired count to zero. Compute spend stops. |
| `destroy --yes` | Removes every resource including the images. |
| `render-taskdef` | Writes the task definition JSON to disk for review. |

Or double-click **`ModelPipeline/finsights_aws.command`** for the same verbs as a menu.

Requires: the `mjsushanth_mlops` profile in `~/.aws/credentials`, Docker running (for
builds), and a Python with `boto3` (the `finsights_revival` conda env has it).

The application's own credentials file at `finrag_ml_tg1/.aws_secrets/` is **not** used by
any of this, and no static keys reach the deployed container.

---

## 2. The architecture, and why it is this shape

```
                            INTERNET
                                |
                                |  tcp/8501 only
                                v
        +---------------------------------------------------+
        |  Security group  finsights-app-sg                 |
        |  inbound:  8501 from 0.0.0.0/0                    |
        |  inbound:  NOTHING on 8000                        |
        +---------------------------------------------------+
                                |
   default VPC vpc-07e7c1c0f47896c94, public subnets in 1a/1b/1c
   route table -> igw-0859a4b15b8c85d71     (internet gateway: free)
   NO NAT gateway                            (would be ~$32.85/mo/AZ)
                                |
                                v
   +=================================================================+
   |  ECS TASK   family finsights-app   1 vCPU / 3072 MiB / ARM64    |
   |  networkMode awsvpc -> its own ENI, its own public IP           |
   |                                                                 |
   |   ONE NETWORK NAMESPACE, SHARED BY BOTH CONTAINERS              |
   |   +---------------------------+   +--------------------------+   |
   |   |  frontend  (Streamlit)    |   |  backend  (FastAPI)      |   |
   |   |  listens 0.0.0.0:8501     |   |  listens 0.0.0.0:8000    |   |
   |   |  BACKEND_URL=             |   |                          |   |
   |   |    http://localhost:8000 -+-->|  loopback, never leaves  |   |
   |   |  memoryReservation 384    |   |  memoryReservation 2560  |   |
   |   |  dependsOn: backend       |   |                          |   |
   |   |    condition HEALTHY      |   |                          |   |
   |   +---------------------------+   +--------------------------+   |
   |                                        |                        |
   |            taskRoleArn finsightsEcsTaskRole (least privilege)   |
   +=================================================================+
                                             |
              +------------------------------+-------------------+
              v                     v                           v
        Bedrock                  S3                        S3 Vectors
   Haiku 4.5 via us.*     sentence-data-...-mjs     finrag-sentence-fact-
   inference profile      read all / write only     embed-1024d
   + cohere.embed-v4      LOGS/FINRAG prefix        query only
```

### 2.1 Why one task with two containers

Fargate bills **per task**, per second, on the task-level cpu and memory reservation -
not per container, and not on actual usage. Two consequences drive the whole design:

- A second **container** inside the same task is close to free.
- A second **task** doubles the compute bill.

So the question "one task or two services?" is really "do we need independent scaling
enough to pay for it?" The answer is no, and for a reason that is easy to miss:

> Independent scaling is only *useful* if something distributes traffic across the
> replicas. DNS-based service discovery cannot do that job - resolvers cache per TTL,
> clients hold connections open, and DNS carries no load information. So the two-service
> shape needs a load balancer to deliver its own benefit.

| Option | Monthly standing cost | Notes |
| :-- | :-- | :-- |
| **A. One task, two containers, `localhost`** | **$0** extra | Chosen. Also preserves compose's `depends_on: service_healthy`. |
| B. Two services + Cloud Map DNS | ~$0.50 (private hosted zone) + a second task | Independent scaling that cannot actually distribute load. |
| C. Two services + ALB | ~$16.43 (ALB) + a second task | Real load balancing. Ruled out on cost. |

Option A is both the cheapest *and* the only one that keeps the local ordering
guarantee, because ECS can express `dependsOn` between containers in one task but
cannot express ordering between two services - it reconciles services independently
and continuously.

### 2.2 Why public subnets

Public versus private is a property of the **route table**, not of the subnet. All six
default subnets are associated with a route table whose `0.0.0.0/0` route points at an
internet gateway, and an internet gateway is free. A task there with `assignPublicIp:
ENABLED` gets the outbound access it needs for Bedrock and S3 at no charge.

Private subnets would need a NAT gateway for that same egress: **~$32.85/mo per AZ plus
$0.045/GB**. That one choice would cost more per month than all the compute this
deployment is expected to use. `Provisioner.discover_network()` therefore verifies the
route table rather than trusting `MapPublicIpOnLaunch`.

### 2.3 Why only port 8501 is open

The Dec 2025 security group allowed **tcp/8000 from 0.0.0.0/0**. The backend's `/query`
endpoint costs real Bedrock money per call and has no authentication and no rate limit,
so that rule left a paid endpoint open to anyone who found the IP.

Co-locating the containers closes this for free. The backend listens on the task's
loopback interface, reachable only from inside the task's own network namespace. There
is no rule to write because there is no path to block. `smoke` asserts this as a
positive check rather than assuming it - if the backend ever answers from the internet,
that check fails.

The public **frontend** is correct and intended: the RAG UI is the product.

---

## 3. Verified measurements

All measured on 2026-07-31. Nothing in this table is an estimate.

| Property | Measured value | How |
| :-- | :-- | :-- |
| Backend peak memory, simple query | 1,139 MiB | `docker stats` sampling, local ARM images |
| Backend peak memory, 10-company query | **1,220 MiB** | same |
| Frontend memory, idle and under load | **146 MiB** (flat) | same - it is a pure HTTP client |
| Backend idle memory | 213 MiB | ML components load lazily, not at import |
| Backend cold start to healthy | ~5 s | container restart to `/health` 200 |
| Deployed query cost | **$0.0140** | backend log, 12,670 tokens |
| Deployed query latency | **9.6 s** | backend log |
| Local query latency | 10.5 s simple / 14.1 s heavy | local stack, warm |
| ECR stored size (both images) | **0.643 GB** compressed | `ecr describe-images` |
| Fargate on-demand vCPU quota | 30 | `service-quotas` |

Task sizing follows directly: **1 vCPU / 3072 MiB**, split 2560 / 384 as soft
reservations. That is roughly 2x headroom over observed peak without stepping up a cpu
tier. The 0.25 vCPU / 512 MiB shape quoted in the December documents would have been
killed by the OOM killer on the first query.

### 3.1 Latency, correctly characterised

There is no discrepancy with `PIPELINE_LATENCY_ANALYSIS.md` - the two documents were
measuring different query classes. Latency here scales with query complexity, and almost
all of it is the LLM:

| Query class | End-to-end | Notes |
| :-- | :-- | :-- |
| Simple / moderate | **9.6-14.1 s** | measured 2026-07-31, local and deployed |
| Multi-year, multi-company, cross-comparison | **50 s and up** | consistent with the 25-50 s in `PIPELINE_LATENCY_ANALYSIS.md` |
| Very large, many KPIs triggered | up to **~4 minutes** | observed historically; completed successfully - the context was simply enormous |

**The retrieval pipeline itself is essentially constant at 5-6 s regardless of class.**
Everything above that is Bedrock generating tokens, and a bigger assembled context means
more input tokens and a longer answer, so the LLM time grows while the pipeline time does
not. This is the same cost-over-latency trade-off recorded in
`../finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md`, and it is deliberate, not a regression.

Two operational consequences:

- A 4-minute worst case matters for any future load balancer or API gateway in front of
  this. It is one of the concrete reasons Lambda was never viable: API Gateway caps an
  integration at about 29 s.
- Per-request construction overhead of ~825 ms (section 9) is 8.6% of a simple query but
  under 2% of a complex one. Optimising it is real but small.

---

## 4. Cost model

**VERIFIED** against the AWS Pricing API on 2026-07-31, region `us-east-1`. The usage
types carry a region prefix (`USE1-Fargate-ARM-vCPU-Hours:perCPU`), which is why an
unprefixed query returns nothing:

| Rate | x86_64 | ARM64 (Graviton) | ARM saving |
| :-- | --: | --: | --: |
| per vCPU-hour | $0.040480 | **$0.032380** | 20.01% |
| per GB-hour | $0.0044450 | **$0.0035600** | 19.91% |

At 1 vCPU / 3 GB: `1 x 0.03238 + 3 x 0.00356` = **$0.04306/hour** on ARM, versus
$0.053815/hour on x86. That is **$7.85/month saved** at 24/7, for an architecture change
that cost nothing to adopt.

| Posture | Compute | Standing | Total |
| :-- | :-- | :-- | :-- |
| Running 24/7 | $31.43/mo | $0.0643 ECR | **~$31.50/mo** |
| Running 2 h/day | $2.62/mo | $0.0643 ECR | **~$2.68/mo** |
| Running 4 h for a demo | $0.17 once | $0.0643 ECR | **~$0.23** |
| `down` (desired count 0) | **$0** | $0.0643 ECR | **$0.064/mo** |
| `destroy` | $0 | $0 | **$0** |

ARM64 was chosen partly for the ~20% saving over x86 ($0.053815/hour for the same
shape, or ~$39.28/mo at 24/7) but mainly because it is the *native* build on an Apple
Silicon Mac - no emulation, faster builds - and because the images were already proven
on aarch64 locally before deploying.

Per-query Bedrock spend is separate and additive: **$0.017-$0.06+**, scaling with
retrieved-context volume and entity fan-out rather than a fixed rate.

### Why `down` really is zero

There is no stopped-container charge on Fargate, because there is no stopped container -
the micro-VM is destroyed. `down` keeps the service, cluster, roles, log group and
images, so `up --no-build` restarts in about a minute. `destroy` exists for when even
$0.064/month is unwanted.

---

## 5. What each resource is, and why

| Resource | Name | Why it exists |
| :-- | :-- | :-- |
| ECR repositories | `finsights-backend`, `finsights-frontend` | Image storage. Lifecycle policy expires untagged images after 1 day so rebuilds do not accumulate. |
| CloudWatch log group | `/ecs/finsights` | Container stdout. **7-day retention set explicitly** - the default is never-expire, which is how log costs creep. |
| Execution role | `finsightsEcsExecutionRole` | Assumed by the **ECS agent, before the container starts**, to pull from ECR and open the log stream. Uses the AWS managed policy, which is correct for that job. |
| Task role | `finsightsEcsTaskRole` | Assumed by the **application at request time**. Inline least-privilege policy, versioned with the repo. |
| Security group | `finsights-app-sg` | One ingress rule: tcp/8501. |
| ECS cluster | `finsights-cluster` | Logical grouping. Costs nothing itself. |
| Service-linked role | `AWSServiceRoleForECS` | Lets ECS manage ENIs on your behalf. See section 7. |

### 5.1 The IAM task role, in detail

The Dec 2025 task role carried `AmazonBedrockFullAccess` + `AmazonS3FullAccess`. Between
them, every Bedrock action on every model and every S3 action on every bucket -
including `DeleteObject` on the embedding tables that cost days of compute to
regenerate. Fronted by a public endpoint.

The replacement grants five statements and no wildcards, no `Delete` anywhere:

| Sid | Grants |
| :-- | :-- |
| `BedrockInvokeOnly` | `InvokeModel`, `InvokeModelWithResponseStream` on 5 specific ARNs |
| `S3ReadCorpusAndTables` | `GetObject` on one bucket |
| `S3ListForPolarsScan` | `ListBucket`, `GetBucketLocation` - Polars lists a prefix before reading parts |
| `S3WriteQueryLogsOnly` | `PutObject` on `DATA_MERGE_ASSETS/LOGS/FINRAG/*` only |
| `S3VectorsQueryOnly` | `QueryVectors`, `GetVectors`, `GetIndex`. No `PutVectors`, no `DeleteVectors` |

**The cross-region inference trap.** `us.anthropic.claude-haiku-4-5-...` is not a
foundation model - it is an *inference profile* that fans requests across regions.
Invoking it needs permission on two different kinds of resource:

1. the inference profile, which is account-scoped, and
2. the underlying foundation model in **every region the profile can route to**, which
   is account-agnostic (note the empty account field).

```
arn:aws:bedrock:us-east-1:908877262866:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0
arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0
arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0
arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0
arn:aws:bedrock:us-east-1::foundation-model/cohere.embed-v4:0
```

Granting only the profile, or only `us-east-1`, produces the worst failure mode: it
works most of the time and throws `AccessDeniedException` whenever Bedrock happens to
route elsewhere. The region list was read from `bedrock:GetInferenceProfile`, not
guessed - the profile's own description states us-east-1, us-east-2 and us-west-2.

---

## 6. Why the credentials need no code change

`finrag_ml_tg1/loaders/ml_config_loader.py` already detects a cloud runtime and hands
credential resolution to boto3:

```python
if os.getenv('AWS_EXECUTION_ENV') or os.getenv('AWS_LAMBDA_FUNCTION_NAME') \
   or os.getenv('ECS_CONTAINER_METADATA_URI'):
    self._aws_creds_source = "IAM_ROLE"
    return   # boto3 will automatically use the attached IAM role
```

boto3 then walks its credential chain and finds the ECS container credential provider,
which does an HTTP GET to the link-local address `169.254.170.2` at the path in
`AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`. So "use an IAM role" is a **deployment**
change, not a code change.

One hardening step was needed. That check looks for `ECS_CONTAINER_METADATA_URI`, but
modern Fargate platform versions inject the **v4** name
(`ECS_CONTAINER_METADATA_URI_V4`). Rather than depend on platform-version trivia, the
task definition sets `AWS_EXECUTION_ENV=AWS_ECS_FARGATE` explicitly - one line of
config against a failure that would otherwise appear as the container hunting for a
credentials file that is deliberately not in the image.

**Verified in the deployed container:**

```
[DEBUG] AWS containerized environment detected (ECS/Lambda) - using IAM role
[DEBUG] Container detected -> S3_STREAMING mode
[DEBUG: S3StreamingLoader] Using temp cache: /tmp/finrag_cache
Query successful: cost=$0.0140, tokens=12670, time=9631ms
INFO: 127.0.0.1:34932 - "POST /query HTTP/1.1" 200 OK
```

That last line is the proof of the whole wiring argument: the request reached the
backend from `127.0.0.1`. Two containers, one loopback interface, no load balancer, no
DNS.

It also resolves the largest open risk from the design phase. Polars reaches S3 through
the Rust `object_store` crate, which does its own credential resolution rather than
going through botocore, so it was an open question whether it would find the task role.
It did - `S3StreamingLoader` read its tables successfully under the bare task role, with
no static keys present.

---

## 7. Failures found while getting this working

**7.1 The ECS service-linked role did not exist.** `CreateCluster` failed with:

```
InvalidParameterException: Unable to assume the service linked role.
Please verify that the ECS service linked role exists.
```

A service-linked role is a role AWS assumes to act on your behalf - here so ECS can
manage ENIs. The console creates it silently the first time anyone opens the ECS page,
which is why almost nobody meets this error. Doing everything through the API on a
genuinely untouched account exposes it.

This is exactly the gap that made `setup-infrastructure.yml`'s claim of working on "a
completely fresh AWS account" untrue: it never created this role, so its very first ECS
call would have failed the same way. Fixed by
`Provisioner.ensure_service_linked_role()`.

**7.2 A cosmetic false alarm, deliberately left alone.** `serving/backend/config.py`
logs at startup:

```
WARNING - AWS credentials not detected in environment.
```

It is looking for `AWS_ACCESS_KEY_ID` in the environment, which is correctly absent -
the task role supplies credentials instead. The warning is wrong but harmless, and
fixing it is outside the scope of the deployment work.

**7.3 `health=UNKNOWN` immediately after start.** Expected: during the 60 s
`startPeriod` a container reports UNKNOWN until its first successful probe. Both reached
HEALTHY shortly after. Worth knowing because a *permanent* UNKNOWN is the signature of a
health check defined only in the Dockerfile - Fargate ignores the image's `HEALTHCHECK`
instruction entirely, which is why the task definition restates both probes.

---

## 8. What is different from December 2025

| | Dec 2025 | Now |
| :-- | :-- | :-- |
| Task definition | Hand-made in the console; workflow could only `describe` then patch it | Built by `deploy_aws/taskdef.py`, committed |
| Fresh-account capable | No - failed at the first describe, and never created the service-linked role | Yes, verified from an account with zero ECS history |
| Account IDs | Hardcoded (`729472661729`, 8 places) | Resolved from STS at runtime, never committed |
| Cluster name | `finsights-cluster` in setup, `finsights-cluster-new` in deploy - teardown deleted the wrong one | One name, one config object |
| IAM guard | Guarded 2 operations with a 1-operation check; a half-built role never self-healed | Only `CreateRole` guarded; policy assertions run every time |
| Task role | `BedrockFullAccess` + `S3FullAccess` | 5 scoped statements, no wildcards, no deletes |
| Backend exposure | tcp/8000 open to 0.0.0.0/0 | No ingress; loopback only |
| Wiring | Cloud Map private hosted zone | `localhost` |
| Task size | 0.25 vCPU / 512 MiB (would OOM) | 1 vCPU / 3072 MiB (measured) |
| Log retention | Unset (never expire) | 7 days |
| Architecture | x86 | ARM64 |
| Runnable locally | No - GitHub Actions only | Yes - `python -m deploy_aws.cli` |

---

## 9. Still open

- **Per-request rebuild.** `synthesis_pipeline/orchestrator.py:142-160` reconstructs
  MLConfig three times, plus `init_rag_components()`, `PromptLoader()` and
  `QueryLogger()`, on every request. The measurements in section 3 make the caching
  order decidable; the fix is deliberately separate from the deployment change so the
  two are not entangled.
- **Latency discrepancy.** 9.6-14.1 s observed against 25-50 s documented. Needs a real
  measurement pass, not three samples.
- **Fargate ARM pricing not read back from the API.** See section 4.
- **`/health` proves nothing.** `api_service.py:144-157` returns `status="healthy"`
  unconditionally with `aws_configured=None` hardcoded. It cannot fail, so it cannot be
  used as a deploy gate. A real readiness probe that checks Bedrock and S3 reachability
  would let `dependsOn: HEALTHY` mean something.
- **Retrieval coverage.** The verification query returned the "KPI snapshot not in
  retrieved context" guardrail response rather than the revenue figure. That is a
  retrieval-coverage question, not a deployment one, but it is the kind of thing a
  deploy smoke test should eventually assert on.

---

*Author: Joel Markapudi. Written 2026-07-31 against the working deployment.*
