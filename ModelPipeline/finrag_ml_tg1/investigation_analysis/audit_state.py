"""Statelessness audit: which classes mutate self OUTSIDE __init__?

Why this question decides the caching design
--------------------------------------------
Caching a component means one instance is shared across requests. FastAPI runs
sync endpoint functions in a threadpool, so two requests really can be inside
the same object at the same time - even with uvicorn --workers 1.

An object is safe to share iff, after construction, its attributes are only
ever READ. Any attribute assigned in a method other than __init__ is per-call
state living on a shared object, which under concurrency means request A can
observe or clobber request B's value.

Grep cannot answer this reliably (it cannot tell which function an assignment
is in, and it trips over strings and comments). The AST can.

Reports, per class:
  SAFE      - assigns to self only in __init__
  SUSPECT   - assigns to self elsewhere; each offending attribute is listed
              with the method and line, so it can be judged individually
              (a memoisation cache is different from a per-query field)

Usage: python audit_state.py <file.py> [file.py ...]
"""
import ast
import sys
from pathlib import Path
from typing import Dict, List, Tuple

INIT_LIKE = {"__init__", "__post_init__", "__new__"}


def self_targets(node: ast.AST) -> List[str]:
    """Attribute names assigned via `self.<name>` in this statement."""
    found = []
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        targets = [node.target]
    for t in targets:
        if (isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"):
            found.append(t.attr)
        # self.a, self.b = ...
        elif isinstance(t, (ast.Tuple, ast.List)):
            for elt in t.elts:
                if (isinstance(elt, ast.Attribute)
                        and isinstance(elt.value, ast.Name)
                        and elt.value.id == "self"):
                    found.append(elt.attr)
    return found


def audit_class(cls: ast.ClassDef) -> Tuple[List[str], Dict[str, List[Tuple[str, int]]]]:
    init_attrs: List[str] = []
    mutations: Dict[str, List[Tuple[str, int]]] = {}
    for item in cls.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        in_init = item.name in INIT_LIKE
        for node in ast.walk(item):
            for attr in self_targets(node):
                if in_init:
                    init_attrs.append(attr)
                else:
                    mutations.setdefault(attr, []).append((item.name, node.lineno))
    return init_attrs, mutations


def main(paths: List[str]) -> None:
    total_safe = total_suspect = 0
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"?? missing: {p}")
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:
            print(f"?? unparseable: {p} ({exc})")
            continue
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if not classes:
            continue
        print(f"\n=== {path.name} ===")
        for cls in classes:
            init_attrs, mutations = audit_class(cls)
            if not mutations:
                total_safe += 1
                print(f"  SAFE     {cls.name:<28} "
                      f"({len(set(init_attrs))} attrs, all set in __init__)")
            else:
                total_suspect += 1
                print(f"  SUSPECT  {cls.name:<28} "
                      f"({len(mutations)} attr(s) mutated outside __init__)")
                for attr, sites in sorted(mutations.items()):
                    where = ", ".join(f"{m}():{ln}" for m, ln in sites[:4])
                    extra = "" if len(sites) <= 4 else f" +{len(sites)-4} more"
                    print(f"             self.{attr:<22} <- {where}{extra}")
    print(f"\nTOTAL: {total_safe} safe, {total_suspect} suspect")


if __name__ == "__main__":
    main(sys.argv[1:])
