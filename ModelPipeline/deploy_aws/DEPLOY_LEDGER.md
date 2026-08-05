# Deployment Ledger

Append-only. Newest entry at the bottom. This exists so a later session can resume
without re-deriving anything: it records what was done, what was measured, and what is
still open. Design rationale lives in
`../finrag_docker_loc_tg1_aws/ECS_FARGATE_RUNBOOK.md`, not here.

Claims are labelled **VERIFIED** (observed directly) or **UNVERIFIED** (inferred,
published, or assumed).

---

## 2026-07-31 - first working ECS Fargate deployment

**Starting state.** Account `908877262866` (`mjsushanth_mlops`) had a working data plane
(S3 bucket, S3 Vectors index, Bedrock) and a completely empty deployment plane: zero ECR
repositories, zero ECS clusters, zero load balancers, zero CloudWatch log groups, default
VPC only, and no ECS service-linked role.

### Reconnaissance (read-only)

- VPC `vpc-07e7c1c0f47896c94`, 6 subnets across us-east-1a-f, all `MapPublicIpOnLaunch`,
  main route table `rtb-0ce6cacf849032771` routes `0.0.0.0/0` to
  `igw-0859a4b15b8c85d71`. **No NAT gateway.** VERIFIED.
- Fargate on-demand vCPU quota: 30. VERIFIED.
- `us.anthropic.claude-haiku-4-5-20251001-v1:0` invoked successfully. VERIFIED.
- `cohere.embed-v4:0` invoked successfully. VERIFIED.
- CRIS profile routes to us-east-1, us-east-2, us-west-2 - read from
  `bedrock:GetInferenceProfile`, not assumed. VERIFIED.
- S3 Vectors index in the account is `finrag-sentence-fact-embed-1024d`. VERIFIED.

### Config traps found (not fixed - pre-existing, out of scope)

`ml_config.yaml` contains a **dead** `vector_search:` / `llm:` block around lines
380-400. It names `index_name: finrag-embeddings` (wrong - no such index) and
`model_id: anthropic.claude-3-5-sonnet-20240620-v1:0` (not accessible on this account).
Neither is read: the only consumer is `orchestrator_v1bkp.py:308`, commented out. The
live values are line 441 (`us.anthropic.claude-haiku-4-5-...`) and line 491
(`finrag-sentence-fact-embed-1024d`), both of which match the real account. VERIFIED by
grep. Left in place, but it will mislead the next reader.

### Measurements driving task sizing

Local ARM images, real queries, `docker stats` sampling. All VERIFIED.

| | Backend | Frontend |
| :-- | :-- | :-- |
| Idle | 213 MiB | 146 MiB |
| Simple query | 1,139 MiB | 146 MiB |
| 10-company query | 1,220 MiB | 146 MiB |

Latency: 10.5 s simple, 14.1 s heavy locally; 9.6 s deployed. Against 25-50 s in
`PIPELINE_LATENCY_ANALYSIS.md` - discrepancy NOT resolved, three samples is too few.

Chosen shape: **1 vCPU / 3072 MiB ARM64**, reservations 2560 / 384.

### Built

`ModelPipeline/deploy_aws/` - 8 modules plus `cli.py`. Every module has a
`__main__` self-test that runs without creating anything. Plus
`ModelPipeline/finsights_aws.command` as a double-click menu.

One surgical change outside the package: `deploy_aws/` added to
`ModelPipeline/.dockerignore`, so the served image carries no code capable of creating or
deleting AWS infrastructure.

### Deployment outcome - VERIFIED

- Task definition `finsights-app:1` registered **from the repo**, with no
  describe-then-patch step. This is the specific correction for what killed the Dec 2025
  deployment.
- Service reached steady state; both containers HEALTHY.
- Public URL was `http://13.223.242.82:8501` (ephemeral - changes on every task
  replacement).
- Real query answered: **cost $0.0140, 12,670 tokens, 9,631 ms**.
- Container log confirmed `using IAM role`, `S3_STREAMING mode`, and
  `POST /query 200 OK` from **`127.0.0.1`** - which is the direct proof that the
  two containers share one network namespace.
- **The largest pre-deployment risk is closed:** Polars reaches S3 through the Rust
  `object_store` crate, which resolves credentials independently of botocore, so it was
  unknown whether it would find a bare ECS task role. `S3StreamingLoader` read its
  tables successfully with no static credentials present. VERIFIED.
- `down` reached desired=0 running=0. VERIFIED.
- ECR standing cost measured at **0.643 GB -> $0.0643/month**. VERIFIED.

### Bug found and fixed during deployment

`CreateCluster` failed on the first `up`:

```
InvalidParameterException: Unable to assume the service linked role.
```

The account had never used ECS, so `AWSServiceRoleForECS` did not exist. The console
creates it silently on first visit, which is why this is rarely seen. Fixed by
`Provisioner.ensure_service_linked_role()`, called before `ensure_cluster()`. This is the
concrete reason `setup-infrastructure.yml`'s "works on a completely fresh AWS account"
claim was false.

### Left alone deliberately

- `serving/backend/config.py:140` warns "AWS credentials not detected in environment" at
  startup. It checks for `AWS_ACCESS_KEY_ID`, correctly absent under a task role. Wrong
  but harmless; fixing it is not deployment work.
- `api_service.py:144-157` `/health` returns healthy unconditionally with
  `aws_configured=None`. It cannot fail, so it is not a usable deploy gate. `smoke`
  therefore does not rely on it.

### Open, in priority order

1. **Per-request rebuild** - `synthesis_pipeline/orchestrator.py:142-160` rebuilds
   MLConfig x3, `init_rag_components()`, `PromptLoader()`, `QueryLogger()` on every
   request. The measurements above make the caching order decidable. Kept separate from
   the deployment change on purpose.
2. **Latency discrepancy** - needs a real measurement pass.
3. **Fargate ARM pricing** - UNVERIFIED by API. The AWS Pricing API returned no Fargate
   usage types under service code `AmazonECS`. Published rates used
   ($0.03238/vCPU-hr, $0.00356/GB-hr). Confirm against Cost Explorer after a full day.
4. **Real readiness probe** - would make `dependsOn: HEALTHY` mean something.
5. **CI wiring** - deliberately not done. The user asked for a working local pipeline
   first. `deploy_aws.cli` is callable from CI when wanted; nothing needs reimplementing.

### Resume instructions

```bash
cd ModelPipeline
export AWS_PROFILE=mjsushanth_mlops
python -m deploy_aws.cli status      # where things stand
python -m deploy_aws.cli up          # bring it back (rebuilds images)
python -m deploy_aws.cli up --no-build   # if the ECR images are still there
```

Nothing in this work has been committed to git.
*(Superseded — see the 2026-08-05 entry: `deploy_aws/` is tracked in git as of the Aug 1 work.)*

---

## 2026-08-05 - cost verification against Cost Explorer

No infrastructure was created, started, or modified. Read-only billing analysis only.

### Open item 3 - RESOLVED: Fargate ARM pricing is now VERIFIED

The 2026-07-31 entry recorded Fargate ARM rates as **UNVERIFIED**, used published figures, and
asked to "confirm against Cost Explorer after a full day." Done. Derived by dividing
`UnblendedCost` by `UsageQuantity` per usage type over 2026-07-01 → 2026-08-06:

| Usage type | Published (assumed 07-31) | Measured from bill | Verdict |
| :-- | --: | --: | :-- |
| `USE1-Fargate-ARM-vCPU-Hours:perCPU` | $0.03238 / vCPU-hr | **$0.032380** | exact match |
| `USE1-Fargate-ARM-GB-Hours` | $0.00356 / GB-hr | **$0.003560** | exact match |
| `USE1-PublicIPv4:InUseAddress` | not recorded | **$0.005000 / hr** | new |

The published rates were right. **VERIFIED.** Note the Pricing API gap that caused the original
UNVERIFIED label is real and unchanged — service code `AmazonECS` still returns no Fargate usage
types. Cost Explorer, not the Pricing API, is the way to confirm these.

### Cost of the deployed shape - VERIFIED

For `finsights-app:6` (1 vCPU / 3072 MiB ARM64) at `desiredCount=1`, 24/7:

    1 vCPU x $0.03238  +  3 GB x $0.00356  +  $0.005 IPv4  =  $0.04806/hr
    -> $1.1534/day  ->  $34.60 per 30 days

Actual Fargate consumed to date: **1.0633 vCPU-hours** (~1.1 h of a 1-vCPU task) across the
Jul 31 and Aug 1-2 sessions. The service is currently at `desiredCount=0`, running 0, and has
been since Aug 2 - so it is contributing **nothing**. VERIFIED by `describe-services`.

### Account-wide idle floor - VERIFIED

2026-08-03 was a natural zero-activity day (no Bedrock, no Fargate), which isolates the
always-on cost cleanly:

| Line item | $/day | $/30 days |
| :-- | --: | --: |
| S3 Vectors storage (2.501 GB @ $0.06/GB-mo) | 0.004841 | 0.1452 |
| S3 Standard storage | 0.003307 | 0.0992 |
| ECR image storage | 0.001646 | 0.0494 |
| **Total** | **0.009794** | **0.2938** |

Swept for silent recurring resources and found **none**: no NAT gateway, load balancer, Elastic
IP, EBS volume or snapshot, Route 53 hosted zone, Secrets Manager secret, KMS customer key, or
Glue database. VERIFIED by direct API calls.

**ECR figure from 07-31 revisited.** That entry recorded 0.643 GB → $0.0643/month. Cost
Explorer now isolates ECR at **$0.001646/day = $0.0494/month**, implying ~0.49 GB stored at
$0.10/GB-month. `describe-images` reports only 0.345 GB across the two `latest` tags
(197,961,464 B + 146,761,936 B), so roughly 0.15 GB is untagged layers that `describe-images`
does not show. Direction of travel is down (0.643 → 0.49 GB), consistent with some layer
reclamation since 07-31. The remaining tagged-vs-billed gap is **UNVERIFIED** but is inherent to
how ECR reports: bill by stored layers, API by tagged manifests. ECR is 17% of the idle floor
and $0.05/month absolute, so not chased further.

### Spend to date

Jun 1 - Aug 5 total **$4.59**, of which Bedrock inference is 81% (Cohere Embed 4 $2.2279,
Haiku 4.5 $1.2715, Rerank 3.5 $0.24). All infrastructure combined - ECS, ECR, VPC - is
**$0.0590**, i.e. 1.3%. The deployment is not what costs money; the model calls are.

### Corrected elsewhere in this pass

`finrag_ml_tg1/S3Vect_QueryCost.md` carried "PutVectors and data ingress are effectively free" -
**false**, PUT is $0.20/GB and cost $0.500237. Fixed, with a dated "Verified pricing" section and
a correction log. Also settled the long-open per-vector footprint contradiction in
`investigation_analysis/EMPIRICAL_METHODS_AND_FINDINGS.md` at **2.501 GB** logical for 614,647
vectors. Committed as `889e898`.

### Built: `deploy_aws/cost_forensics.py`

The analysis above was first done with throwaway shell one-liners. It is now a ninth module in
this package so the next session does not re-derive it: `CostForensics` over `AwsSession`,
Decimal end to end, usage-type results cached so no service is queried twice.

- `by_service()` / `by_usage_type()` - grouped totals, credits and refunds filtered out.
- `unit_rates()` - cost / usage quantity. This is what closed open item 3, and is the general
  way to price anything the Pricing API will not quote.
- `idle_floor(day)` - pass a zero-activity day to get the true recurring floor, measured.
- `log_report(start, end)` - the whole breakdown.

Follows the package convention: a `__main__` self-test that creates nothing **and makes no API
calls** - it checks always-on classification and Decimal aggregation against synthetic data.
Cost Explorer bills ~$0.01/request, so live querying is opt-in behind `--live`:

```bash
python -m deploy_aws.cost_forensics                                     # offline, free
python -m deploy_aws.cost_forensics --live --start 2026-08-03 --end 2026-08-04
```

Both paths VERIFIED 2026-08-05. The live run independently reproduced the $0.2938/month floor.

### Still open (unchanged from 07-31)

Items 1 (per-request rebuild), 2 (latency discrepancy), 4 (real readiness probe), and 5 (CI
wiring) are untouched by this pass.
