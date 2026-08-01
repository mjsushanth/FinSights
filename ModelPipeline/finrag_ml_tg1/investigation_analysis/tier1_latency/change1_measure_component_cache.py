"""Throwaway diagnostic: verify the Tier 1 Change 1 component cache actually works.

Calls the new private getters in orchestrator.py (_get_rag_components,
_get_prompt_loader, _get_llm_client, _get_query_logger) directly, twice, in one
process - mirroring exactly what answer_query()'s init block now does. This is
zero-cost (no Bedrock calls at all - these getters only construct objects, they
don't invoke anything), so it is run outside the query-count cost ledger.

Acceptance criteria (TIER1_LATENCY_DESIGN.md section 1.5):
  1. Second+ calls drop by ~1400-1700ms vs the first, in one process.
  2. First call is unchanged (cold build still happens, once).
"""
from pathlib import Path
import sys
import time

for p in [Path.cwd()] + list(Path.cwd().parents):
    if p.name == "ModelPipeline":
        model_root = p
        break
if str(model_root) not in sys.path:
    sys.path.insert(0, str(model_root))

from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline import orchestrator as orch


def build_all(config, model_key=None):
    orch._get_rag_components()
    orch._get_prompt_loader()
    orch._get_llm_client(config, model_key)
    orch._get_query_logger()


config = MLConfig()

for pass_no in (1, 2, 3):
    t0 = time.perf_counter()
    build_all(config)
    ms = (time.perf_counter() - t0) * 1000
    print(f"PASS {pass_no}: {ms:8.1f} ms   "
          f"(_RAG_COMPONENTS is {'cached' if orch._RAG_COMPONENTS is not None else 'None'})")

print("\nExpectation: PASS 1 pays the full build. PASS 2 and 3 should be near-zero"
      " (dict/attribute lookups only) since every getter now short-circuits on"
      " the module-level cache.")
