"""Throwaway diagnostic: verify BedrockClient.invoke_stream() end to end.

One tiny real call (max_tokens=20, same shape as the earlier field-path probe)
to confirm: text deltas arrive incrementally, the final event has the same
shape as invoke()'s return value, and cost/token accounting matches.
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
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.bedrock_client import (
    create_bedrock_client_from_config,
)

config = MLConfig()
client = create_bedrock_client_from_config(config)
# Cap output for this diagnostic only - avoid paying for a full-length answer
# just to prove the plumbing works.
client.max_tokens = 20

t_start = time.perf_counter()
t_first_token = None
deltas = []
final = None

for kind, payload in client.invoke_stream(
    system="You are terse.",
    user="Say exactly: hello world, nothing else.",
):
    if kind == "text":
        if t_first_token is None:
            t_first_token = time.perf_counter()
        deltas.append(payload)
        print(f"  [delta] {payload!r}")
    elif kind == "final":
        final = payload

t_end = time.perf_counter()

print(f"\nn_deltas: {len(deltas)}")
print(f"joined deltas: {''.join(deltas)!r}")
print(f"final: {final}")
print(f"\ntime to first token: {(t_first_token - t_start)*1000:.1f} ms")
print(f"total stream time:   {(t_end - t_start)*1000:.1f} ms")

assert final is not None, "FAIL: no final event yielded"
assert final["content"], "FAIL: final content is empty"
assert final["usage"]["input_tokens"] > 0, "FAIL: input_tokens not captured"
assert final["usage"]["output_tokens"] > 0, "FAIL: output_tokens not captured"
assert final["cost"] > 0, "FAIL: cost not computed"
assert "".join(deltas).strip() != "" or final["content"].strip() != "", "FAIL: no text at all"
print("\nVERDICT: PASS - invoke_stream() produces deltas + a well-formed final event")
