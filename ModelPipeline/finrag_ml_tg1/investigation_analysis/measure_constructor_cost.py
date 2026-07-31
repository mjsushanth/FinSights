"""Throwaway diagnostic: time each constructor answer_query() rebuilds per request.

Run inside the backend container. Two passes, to reveal anything already cached
at module level (pass 2 much faster) versus genuinely rebuilt every time.
"""
import time
import tracemalloc

from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.orchestrator import (
    init_rag_components,
)
from finrag_ml_tg1.rag_modules_src.prompts.prompt_loader import PromptLoader
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.query_logger import QueryLogger
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.bedrock_client import (
    create_bedrock_client_from_config,
)


def timed(label, fn):
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        obj = fn()
        err = ""
    except Exception as exc:  # diagnostic only
        obj = None
        err = f"  ERROR: {type(exc).__name__}: {str(exc)[:90]}"
    ms = (time.perf_counter() - t0) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"{label:<34} {ms:9.1f} ms   peak_alloc={peak/1048576:8.1f} MiB{err}")
    return obj


for pass_no in (1, 2):
    print(f"\n===== PASS {pass_no} =====")
    total = time.perf_counter()
    cfg = timed("MLConfig()", MLConfig)
    timed("init_rag_components()", init_rag_components)
    timed("PromptLoader()", PromptLoader)
    if cfg is not None:
        timed("create_bedrock_client_from_config()",
              lambda: create_bedrock_client_from_config(cfg, None))
    timed("QueryLogger()", QueryLogger)
    print(f"{'TOTAL construction':<34} {(time.perf_counter()-total)*1000:9.1f} ms")
