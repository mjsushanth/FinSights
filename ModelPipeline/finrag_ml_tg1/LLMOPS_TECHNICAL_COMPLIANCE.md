# LLMOPS TECHNICAL COMPLIANCE


### **1. Executive Summary**
- Brief overview: RAG validation vs traditional ML validation
- Core argument: Why FinRAG exceeds requirements

### **2. RAG System Architecture (Docker/RAG Format - Requirement 8.1)**
- Platform core notebooks for reproducible, infra-management or embedding-retrieval spine data management.
- Perfectly parameterized with config-driven and service driven style. (MLConfig, YAML for 200+ parameters.)
- S3 Vectors as **production vector store**. 

### **3. Data Pipeline Integration (Requirement 8.2)**
- Perfectly integrated into AWS S3 with 6-users sharing a managed bucket. Prior Data Artifacts already have powerful cloud-managed, parameterized, executable ETL pipelines. 
- ML-pipelines simply pick up from there, rebuild extra facts if necessary, perform smart caching.
- Evidence: Notebooks 01-04

### **4. Validation Framework Overview (Requirement 8.4)**
- Three-tier validation: Infrastructure → Gold P1/P2 → Business Realism (P3 warehouses)
- Why retrieval metrics (Hit@k, MRR) replace traditional accuracy/F1

### **5. Infrastructure Validation (5-Phase S3 Vectors Tests)**
- Test suite 1-5 results, Multiple Isolation-Integration tests, Vector-Meta tests, Embedding staleness audits, Execution history checks - countless other validation-analytic queries.

### **6. Gold P1/P2: Deterministic Neighbor Tests**
- Anchor-based automatic gold set methodology, Filtered vs Open regime results
- Evidence: Notebook 05, screenshots.

### **7. Sensitivity Analysis (Requirement 5 - Hyperparameter/Feature Sensitivity)**
- Window size sensitivity (W=3 vs W=5)
- topK sensitivity (20 vs 30)
- Filter regime comparison (filtered vs open)
- Distance threshold calibration (0.50 baseline)

### **8. Bias Detection (Requirement 6)**
1. FinRAG implements bias detection across multiple architectural layers. More than traditional demographic slicing! 
2. We address retrieval-specific bias patterns. Bias mitigation strategy operates at three levels: **embedding space calibration, retrieval architecture design, and evaluation framework construction.** 
   - Distance threshold analysis across 10+ anchor tests revealed S3 Vectors maintains consistently high-quality retrievals—all top-30 results exhibit cosine distances >0.50~0.60, no low-confidence artifacts.
   - No poor-quality matches disproportionately affect underrepresented document types.

3. Avoiding Generative/Conditioning bias problems: Dual-supply-line architecture (structured KPI extraction + semantic RAG) prevents conditioning bias where generative models over-rely on narrative context while ignoring numerical grounding. 
4. Query variant generation via LLM rephrasings (2-4 semantic variants per query) reduces lexical-overlap bias—ensuring retrieval success doesn't depend on exact keyword matches that favor templated language.
5. **Filter regime analysis** quantifies this effect: open (global) retrieval achieves 60% Self@1 compared to 96.7% in filtered regimes. (cross-document boilerplate dominates nearest-neighbor space without metadata constraints.)
6. **The Gold P3 warehouse construction**: Slice-based bias detection through multi-dim json warehouses. 
   - V1/V2 factoid vs V3/V4/V5 multi-hop views.
   - V3 trend bundles (224 bundles spanning 2-8 fiscal years per company) expose temporal bias in risk/KPI language evolution; 
   - V4 cross-company bundles (316 bundles grouping 2-5 firms per topic/year) surface sector-specific lexical patterns that could disadvantage smaller companies with less standardized disclosure language. 
   - Heuristic NLP filtering and manual curation: identifying bias-prone content slices and creating bias-aware evaluation data. 
   - Section-size stratification in Gold P2 revealed that retrieval performance degrades predictably.
7. Quantitative slice analysis: We have metrics across **section length buckets** (<10, 10-19, 20-39, 40+ sentences), **fiscal year buckets** (2006-2010 vs 2016-2020), and filter regimes (**filtered 82% Hit@5 vs open 61% Hit@5**) documented in Notebook 05 anchor test results.
8. Triple retrieval-path concept too mitigates bias: core-hits from filtered (entity-constrained), global (no-filter fallback), and non-core neighbor expansions (±3 window context) ensure no single retrieval strategy dominates.


- Evidence: `Notebook 06, V3/V4 bundle construction, rag_modules_src`.. etc.


### **9. Non-Applicable Requirements & Justifications**
- Model training (using pre-trained Cohere Embed v4)
- CI/CD for model training (quarterly refresh ≠ code-triggered retraining)
- GCP Artifact Registry (S3 Vectors = production model registry)

---
