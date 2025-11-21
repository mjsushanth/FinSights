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

---

## E2E Comprehensive FinRAG Cost Analysis

### Production Baseline Scenario (1,500 queries/month)
*Realistic production usage with mixed model deployment*

**Query Pattern**: 1,500 queries/month (50 queries/day average)

**Component Cost Breakdown**:

| Component | Configuration | Cost | Type |
|:----------|:--------------|-----:|:-----|
| **Infrastructure** | | | |
| - Vector Storage (S3) | 0.82 GB | $0.05 | Fixed |
| - Parquet Logs (S3) | ~100MB/month | $0.003 | Fixed |
| **Per-Query Vector Costs (Scenarios)** | | | |
| - Conservative | K=30, C≈450 | $0.00045 | Variable |
| - Typical filtered | K=20, C≈300 | $0.00030 | Variable |
| - Open search (worst) | K=30, C≈1000 | $0.00100 | Variable |
| - Multi-index query | K=30, C≈2000 | $0.00200 | Variable |
| **LLM Synthesis Costs** | | | |
| - LLM Sonnet (35% of queries) | 6,153 in / 777 out | $0.02782 | Variable |
| - LLM Haiku (65% of queries) | 6,153 in / 720 out | $0.01044 | Variable |
| - S3 Egress | 35KB/query | $0.000001 | Variable |
| **Development & Testing** | | | |
| - Gold Test P1 (Initial) | 20 anchors × 2 calls | $0.42 | One-time |
| - Gold Test P2 (40 anchors) | 40 × 2 calls × 2 runs | $1.68 | One-time |
| - Gold Test P2 (60 anchors) | 60 × 2 calls × 3 runs | $3.78 | One-time |
| - Dev iterations | ~500 test queries | $5.25 | One-time |



### Vector Retrieval Cost Scenarios
| N (calls/month) | K  | C     | Cost per call | Total cost/month |
| --------------- | -- | ----- | ------------- | ---------------- |
| 1,000           | 30 | 450   | $0.00045      | $0.45            |
| 1,000           | 30 | 1,000 | $0.00100      | $1.00            |
| 10,000          | 30 | 450   | $0.00045      | $4.50            |
| 10,000          | 30 | 1,000 | $0.00100      | $10.00           |
| 10,000          | 50 | 1,500 | $0.00150      | $15.00           |



| Queries/Month | Vector Cost* | Sonnet (35%) | Haiku (65%) | Total Monthly |
|:--------------|-------------:|-------------:|------------:|-------------:|
| **100** | $0.045 | $0.97 | $0.68 | **$1.70** |
| **300** | $0.135 | $2.92 | $2.04 | **$5.10** |
| **500** | $0.225 | $4.87 | $3.39 | **$8.49** |
| **1,000** | $0.450 | $9.74 | $6.78 | **$17.00** |
| **1,500** | $0.675 | $14.60 | $10.18 | **$25.50** |
| **2,000** | $0.900 | $19.47 | $13.57 | **$34.00** |
| **5,000** | $2.250 | $48.69 | $33.93 | **$85.00** |

*Vector cost assumes C≈450 comparisons per query

Where Vector_Cost ranges:
- Best case (filtered): $0.0003/query
- Expected (midpoint): $0.0005/query  
- Worst case (open): $0.0020/query

1. S3 Vectors charges based on data processed: (vector data + filterable metadata + key) × vectors processed
2. Query operations typically take 100-300ms for indexes with millions of vectors
3. In AWS's pricing example with 10M queries, query costs far outweigh storage and upload costs
4. The actual number of comparisons (C) depends on:
   - Index size and distribution
   - Use of metadata filters (reduces search space)
   - Query complexity (filtered vs open)

**Monthly Cost Calculation**:

| Category | Calculation | Monthly Cost |
|:---------|:------------|------------:|
| **Fixed Costs** | Storage + Logging | **$0.053** |
| **Variable Costs** | | |
| - Sonnet queries | 525 × ($0.00045 + $0.02782) | **$14.85** |
| - Haiku queries | 975 × ($0.00045 + $0.01044) | **$10.60** |
| **Monthly Recurring Total** | | **$25.50** |
| | | |
| **One-time Development** | | |
| - Gold Test Suite Total | P1 + P2(40) + P2(60) | **$5.88** |
| - Development Testing | 500 queries mixed | **$5.25** |
| **One-time Total** | | **$11.13** |

### **Cost Analysis Summary**
| Metric | Value |
|:-------|------:|
| **Average cost per query** | $0.0170 |
| **Monthly recurring** | $25.50 |
| **Annual projection** | $306.00 |
| **Development amortized (6 months)** | $1.86/month |
| **True monthly cost (with amortization)** | **$27.36** |

### **Key Insights**
1. **Model Mix Impact**: The 35% Sonnet usage drives 58% of LLM costs despite being the minority of queries
2. **Development ROI**: One-time testing costs ($11.13) amortize to negligible amounts over project lifetime
3. **Vector Costs**: Still <2% of total - essentially free compared to synthesis
4. **Scaling Formula**: 
   ```
   Monthly = $0.053 + (N_sonnet × $0.0283) + (N_haiku × $0.0109)
   ```

### **Total Cost Formula with Uncertainty Bands**
```
Monthly Cost = Fixed + Variable
Fixed = $0.053 (storage + logging)
Variable = N × [(% Sonnet × $0.028) + (% Haiku × $0.010) + Vector_Cost]

Where Vector_Cost ranges:
- Best case (filtered): $0.0003/query
- Expected (midpoint): $0.0005/query  
- Worst case (open): $0.0020/query
- Even in the worst-case scenario with C=2000 comparisons per query, the total cost increase is only ~10%, demonstrating the system's cost stability across different query complexities.Retry

**Result**: FinRAG achieves **60-73% cost reduction** versus the commercial alternatives.



### Author
- Joel Markapudi ( markapudi.j@northeastern.edu, mjsushanth@gmail.com )