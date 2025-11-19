# S3 Vectors Query Cost — README

**QueryVectors** costs for Amazon S3 Vectors. Includes a minimal cost model, quick calculators, and concrete scenarios for both development and production RAG usage.

---

## What is billed

* **Storage**: ~$0.30 per 1,000,000 stored vectors per month (example: 203k vectors ≈ $0.06/month).
* **QueryVectors**: billed by **vector comparisons**, not by API calls.
* **PutVectors** (inserts) and data ingress are effectively free for planning purposes.
* **Hard limit**: `topK` must be between 1 and 30.

---

## Notation

* **N**: number of `QueryVectors` API calls.
* **K**: `topK` per call (1–30).
* **C**: vector comparisons per call (internal compute S3 Vectors charges for).
* **P**: price per 1,000,000 comparisons (assume $1.00 for planning).

**Cost (USD)** = (N × C / 1,000,000) × P

Rules of thumb for C:

* For K in [10, 30], a good planning range is **C ≈ 300–500** comparisons/call.
* A simple linear model that works well: **C ≈ 15 × K** (midpoint).

---

## Quick calculators

* **Cost per call (midpoint)**:
  If C ≈ 400 comps/call and P = $1.00 → cost/call ≈ 400 / 1,000,000 × $1 = **$0.0004**.

* **Cost per call as a function of K** (using C ≈ 15 × K):
  cost_per_call(K) ≈ (15 × K / 1,000,000) × P
  With P = $1: **cost_per_call(K) ≈ 0.000015 × K USD**
  Examples:

  * K=10 → $0.00015
  * K=20 → $0.00030
  * K=30 → $0.00045

---

## Dev scenario —  evaluation runs

Evaluated anchors with two queries per anchor (filtered + open).
Two runs:

* Run 1: 40 anchors → 80 calls
* Run 2: 60 anchors → 120 calls
* Total: **N = 200 calls**

Assume K in {20, 30}. Using C ≈ 400:

* Total comparisons: 200 × 400 = **80,000**
* Total cost: 80,000 / 1,000,000 × $1 = **$0.08**
* Range (C = 300–500): **$0.06–$0.10**

Result: a few hundred calls costs only a few cents. Perfectly fine for iterative testing.

---

## Production scenarios — 20 user queries in RAG

Assume K=30, C ≈ 450 comps/call.

**Mode 1: single retrieval per question**

* Calls: N = 20 × 1 = **20**
* Comparisons: 20 × 450 = **9,000**
* Cost: 9,000 / 1,000,000 × $1 = **$0.009**

**Mode 2: two-pass retrieval (reformulation or fallback)**

* Calls: N = 20 × 2 = **40**
* Comparisons: 40 × 450 = **18,000**
* Cost: **$0.018**

**Mode 3: multi-vector per question (3 sub-queries)**

* Calls: N = 20 × 3 = **60**
* Comparisons: 60 × 450 = **27,000**
* Cost: **$0.027**

Observation: the vector-comparison cost is negligible. In RAG systems, the dominant costs are typically embedding generation and LLM tokens, not ANN comparisons.

---

## Cheat sheets

### Cost per call vs. topK (P = $1, C ≈ 15 × K)

| topK K | comps C ≈ 15K | $ / call |
| -----: | ------------: | -------: |
|     10 |           150 |  0.00015 |
|     20 |           300 |  0.00030 |
|     30 |           450 |  0.00045 |

### Total cost quick formula (USD)

Cost ≈ N × 0.000015 × K

Examples:

* N=200, K=30 → 200 × 0.000015 × 30 = **$0.09**
* N=60,  K=30 → **$0.027**
* N=40,  K=20 → **$0.012**

---

## Practical guidance

* Keep `topK` ≤ 30 (service cap). If you need more candidates for reranking, prefer a second call over bumping K beyond 30.
* Pre-filter by metadata (e.g., `cik_int`, `section_name`) to shrink candidate sets and often reduce comparisons toward the 300 end of the range.
* Parallel or batched calls do not change cost; they only affect latency.
* Track `N` and `K` in logs so you can estimate comparisons and costs per endpoint easily.

---

## Minimal helper functions (optional)

```python
def estimate_comparisons(N, K, alpha=15):
    """Rough comparisons = N * (alpha * K)."""
    return int(N * alpha * K)

def estimate_cost_usd(N, K, price_per_million=1.0, alpha=15):
    comps = estimate_comparisons(N, K, alpha)
    return (comps / 1_000_000.0) * price_per_million
```

Examples:

* `estimate_cost_usd(200, 30)` → ~0.09
* `estimate_cost_usd(60, 30)`  → ~0.027

---

## Summary

* Storage: ~$0.30 per million vectors per month; your 203k vectors cost ≈ $0.06/month.
* QueryVectors: ~$1 per million comparisons; with K ≤ 30, think ~300–500 comps/call.
* Dev runs with a few hundred calls: a few cents total.
* 20-question RAG session (even with multi-sub-queries): still only a few cents.
* The real cost centers are typically embeddings and LLM tokens, not vector comparisons.

This framework gives you a stable, quick mental math model to budget and monitor QueryVectors usage in both development and production.
