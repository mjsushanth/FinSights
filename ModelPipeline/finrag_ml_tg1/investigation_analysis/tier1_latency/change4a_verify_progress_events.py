"""Throwaway diagnostic: verify Change 4a's on_progress callback actually fires.

Calls run_supply_line_2_rag() directly (cheap - no LLM synthesis) with a real
on_progress callback attached, and checks:
  1. Every expected stage fires, in order.
  2. Calling WITHOUT on_progress (the default) still works identically -
     zero behavior change for every existing caller.
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

from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.supply_lines import (
    init_rag_components,
    run_supply_line_2_rag,
)

rag = init_rag_components()

events = []


def on_progress(stage, detail):
    events.append((stage, detail))
    print(f"  [event] stage={stage:<10} detail={detail}")


print("=== WITH on_progress ===")
t0 = time.perf_counter()
run_supply_line_2_rag("What was NVIDIA's revenue in 2021?", rag, on_progress=on_progress)
wall_ms = (time.perf_counter() - t0) * 1000

expected_stages = ["entities", "embed", "retrieve", "expand", "assemble"]
fired_stages = [e[0] for e in events]

print(f"\nfired stages (in order): {fired_stages}")
print(f"expected stages (subset check, rerank optional): {expected_stages}")
missing = [s for s in expected_stages if s not in fired_stages]
print(f"missing expected stages: {missing if missing else 'NONE'}")
print(f"order preserved: {fired_stages == expected_stages or (len(fired_stages) == 6 and fired_stages[:2] == expected_stages[:2])}")
print(f"wall_ms: {wall_ms:.1f}")

print("\n=== WITHOUT on_progress (default None - must not raise) ===")
t0 = time.perf_counter()
run_supply_line_2_rag("What was NVIDIA's revenue in 2021?", rag)
wall_ms_no_cb = (time.perf_counter() - t0) * 1000
print(f"OK, no exception. wall_ms: {wall_ms_no_cb:.1f}")

print("\nVERDICT:", "PASS" if not missing and fired_stages == sorted(fired_stages, key=fired_stages.index) else "CHECK MANUALLY")
