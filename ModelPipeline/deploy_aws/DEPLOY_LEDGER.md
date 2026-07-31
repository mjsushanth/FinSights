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
