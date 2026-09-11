"""Runner: native compiler prefixes vs independent dependency reference.

For each in-scope fixture the native program from compile_native is
executed at every prefix (located ONLY via compiler metadata
assembly_end, never its expected values), plus the initial empty program
and the full program. Full coordinates and parent read state (previous
prefix) are compared against shamir_native_dependency_reference, which
never imports the compiler or the float solver. Oblique
compare_native_sequences fixtures are skipped explicitly. Units are raw
26.6 integers. No visual gallery.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import freetype as ft

import shamir_native_dependency_reference as ref
from compare_native_sequences import fixtures as sequence_fixtures
from compare_native_translation import fixture_bytes, run_ft_raw
from shamir_constraints import relation
from shamir_native_translation import compile_native
from shamir_point_schedule import schedule

MS = "https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions"
PPEMS = [14, 16, 18, 20, 125, 1000]
X = [1.0, 0.0]
Y = [0.0, 1.0]
EXPECTED_FIXTURES = 9
EXPECTED_PPEMS = 6
EXPECTED_FULL = 54
EXPECTED_EMPTY = 54
EXPECTED_PREFIX = 528


def _rel(kind, point, normal, sources=(), value=None, rnd=None, i=None):
    kw = dict(sources=list(sources), value=value, id=i)
    if rnd is not None:
        kw["round"] = rnd
    return relation(kind, point, normal, **kw)


def chain_fixtures():
    out = []
    px = [[0, 0], [300, 0], [100, 0], [100, 50], [160, 50], [130, 50]]
    cx = {
        0: [_rel("PAbs", 0, X, value=0, rnd=True, i=1),
            _rel("Abs", 0, Y, value=0.0, rnd=False, i=2)],
        1: [_rel("PAbs", 1, X, value=300, rnd=True, i=3),
            _rel("Abs", 1, Y, value=0.0, rnd=False, i=4)],
        2: [_rel("Ratio", 2, X, sources=[0, 1], value=100.0 / 300.0, rnd=False, i=5),
            _rel("Abs", 2, Y, value=0.0, rnd=False, i=6)],
        3: [_rel("Dist", 3, X, sources=[2], value=0.0, rnd=False, i=7),
            _rel("Abs", 3, Y, value=50.0, rnd=False, i=8)],
        4: [_rel("PDist", 4, X, sources=[3], value=60, rnd=True, i=9),
            _rel("Abs", 4, Y, value=50.0, rnd=False, i=10)],
        5: [_rel("Ratio", 5, X, sources=[2, 4], value=0.5, rnd=False, i=11),
            _rel("Abs", 5, Y, value=50.0, rnd=False, i=12)],
    }
    out.append(("thirds-chain-x", px, cx))
    nx = [[0, 0], [-300, 0], [-100, 0], [-100, -50], [-160, -50], [-130, -50]]
    cn = {
        0: [_rel("PAbs", 0, X, value=0, rnd=True, i=1),
            _rel("Abs", 0, Y, value=0.0, rnd=False, i=2)],
        1: [_rel("PAbs", 1, X, value=-300, rnd=True, i=3),
            _rel("Abs", 1, Y, value=0.0, rnd=False, i=4)],
        2: [_rel("Ratio", 2, X, sources=[0, 1], value=float(-100.0 / -300.0),
                 rnd=False, i=5),
            _rel("Abs", 2, Y, value=0.0, rnd=False, i=6)],
        3: [_rel("Dist", 3, X, sources=[2], value=0.0, rnd=False, i=7),
            _rel("Abs", 3, Y, value=-50.0, rnd=False, i=8)],
        4: [_rel("PDist", 4, X, sources=[3], value=-60, rnd=True, i=9),
            _rel("Abs", 4, Y, value=-50.0, rnd=False, i=10)],
        5: [_rel("Ratio", 5, X, sources=[2, 4], value=0.5, rnd=False, i=11),
            _rel("Abs", 5, Y, value=-50.0, rnd=False, i=12)],
    }
    out.append(("thirds-chain-x-neg", nx, cn))
    py = [[0, 0], [0, 300], [0, 100], [50, 100], [50, 160], [50, 130]]
    cy = {
        0: [_rel("Abs", 0, X, value=0.0, rnd=False, i=1),
            _rel("PAbs", 0, Y, value=0, rnd=True, i=2)],
        1: [_rel("Abs", 1, X, value=0.0, rnd=False, i=3),
            _rel("PAbs", 1, Y, value=300, rnd=True, i=4)],
        2: [_rel("Abs", 2, X, value=0.0, rnd=False, i=5),
            _rel("Ratio", 2, Y, sources=[0, 1], value=100.0 / 300.0,
                 rnd=False, i=6)],
        3: [_rel("Abs", 3, X, value=50.0, rnd=False, i=7),
            _rel("Dist", 3, Y, sources=[2], value=0.0, rnd=False, i=8)],
        4: [_rel("Abs", 4, X, value=50.0, rnd=False, i=9),
            _rel("PDist", 4, Y, sources=[3], value=60, rnd=True, i=10)],
        5: [_rel("Abs", 5, X, value=50.0, rnd=False, i=11),
            _rel("Ratio", 5, Y, sources=[2, 4], value=0.5, rnd=False, i=12)],
    }
    out.append(("thirds-chain-y", py, cy))
    rx = [[300, 0], [0, 0], [200, 0], [210, 50], [270, 50], [285, 50]]
    cr = {
        0: [_rel("PAbs", 0, X, value=300, rnd=True, i=1),
            _rel("Abs", 0, Y, value=0.0, rnd=False, i=2)],
        1: [_rel("PAbs", 1, X, value=0, rnd=True, i=3),
            _rel("Abs", 1, Y, value=0.0, rnd=False, i=4)],
        2: [_rel("Ratio", 2, X, sources=[0, 1],
                 value=float((200 - 300) / (0 - 300)), rnd=False, i=5),
            _rel("Abs", 2, Y, value=0.0, rnd=False, i=6)],
        3: [_rel("Dist", 3, X, sources=[2], value=10.0, rnd=True, i=7),
            _rel("Abs", 3, Y, value=50.0, rnd=False, i=8)],
        4: [_rel("PDist", 4, X, sources=[3], value=60, rnd=True, i=9),
            _rel("Abs", 4, Y, value=50.0, rnd=False, i=10)],
        5: [_rel("Ratio", 5, X, sources=[2, 4],
                 value=float((285 - 200) / (270 - 200)), rnd=False, i=11),
            _rel("Abs", 5, Y, value=50.0, rnd=False, i=12)],
    }
    out.append(("thirds-chain-reversed", rx, cr))
    return out


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _is_positive_cardinal(normal):
    return list(normal) in ([1.0, 0.0], [0.0, 1.0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    out = Path(a.output)
    if out.exists() and any(out.iterdir() if out.is_dir() else [out]):
        sys.exit("refusing to overwrite non-empty output: %s" % out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        ft_ver = list(ft.version())
    except Exception:
        ft_ver = "unknown"

    here = Path(__file__).resolve().parent
    code_hashes = {n: _sha((here / n).read_bytes()) for n in
                   ["experiment_native_dependencies.py",
                    "shamir_native_dependency_reference.py",
                    "test_native_dependency_reference.py", "shamir_native_translation.py",
                    "compare_native_translation.py", "compare_native_sequences.py",
                    "shamir_point_schedule.py", "shamir_constraints.py",
                    "shamir_prototype.py"]}
    errors = []
    cases = []
    skipped = []
    n_full = n_empty = n_prefix = 0

    workload = []
    for key, pts, chosen in sequence_fixtures():
        pts = [list(map(float, p)) for p in pts]
        oblique = any(not _is_positive_cardinal(c["normal"])
                      for group in chosen.values() for c in group)
        if oblique:
            skipped.append(dict(fixture=key, reason="oblique/noncardinal normal: "
                                "reference domain is positive cardinal X/Y"))
            continue
        workload.append((key, pts, {k: list(v) for k, v in chosen.items()}))
    for key, pts, chosen in chain_fixtures():
        workload.append((key, [list(map(float, p)) for p in pts], chosen))

    for key, pts, chosen in workload:
        ihash = _sha(json.dumps(pts).encode())
        case = dict(fixture=key, input_hash=ihash, supported=True)
        try:
            import numpy as np
            graph = schedule(np.asarray(pts, float), chosen, [], [])
            nasm, nmeta = compile_native(graph, pts)
        except Exception as e:
            errors.append(dict(fixture=key, stage="compile-native",
                               input_hash=ihash,
                               error="%s: %s" % (type(e).__name__, e)))
            case["supported"] = False
            cases.append(case)
            continue
        ops = list(nmeta.get("operations", []))
        ncvt = list(nmeta.get("cvt", []))
        case["native_cvt"] = ncvt
        (out / (key + ".native.asm")).write_text("\n".join(nasm))
        (out / (key + ".graph.json")).write_text(
            json.dumps(graph, indent=1, default=str))
        (out / (key + ".native.meta.json")).write_text(
            json.dumps(nmeta, indent=1, default=str))
        nbytes = fixture_bytes(pts, nasm, ncvt or [0])
        (out / (key + ".native.ttf")).write_bytes(nbytes)
        case["hashes"] = {
            "native_asm": _sha("\n".join(nasm).encode()),
            "graph": _sha(json.dumps(graph, sort_keys=True, default=str).encode()),
            "native_meta": _sha(json.dumps(nmeta, sort_keys=True, default=str).encode()),
            "native_ttf": _sha(nbytes),
        }
        rows = []
        for ppem in PPEMS:
            row = dict(ppem=ppem)
            try:
                pred = ref.run(graph, pts, ppem)
            except ref.ReferenceError as e:
                row["error"] = "reference: %s" % e
                errors.append(dict(fixture=key, stage="reference", ppem=ppem,
                                   input_hash=ihash, error=row["error"]))
                rows.append(row)
                continue
            # initial empty program: loaded no-op boundary
            try:
                eraw, _, _ = run_ft_raw(pts, [], ppem, ncvt or [0])
                n_empty += 1
                row["empty_matches_initial"] = (
                    [list(map(int, p)) for p in eraw.tolist()] == pred["initial"])
                if not row["empty_matches_initial"]:
                    errors.append(dict(
                        fixture=key, stage="empty", ppem=ppem, input_hash=ihash,
                        expected=pred["initial"],
                        actual=[list(map(int, p)) for p in eraw.tolist()]))
            except Exception as e:
                row["error"] = "empty: %s: %s" % (type(e).__name__, e)
                errors.append(dict(fixture=key, stage="empty", ppem=ppem,
                                   input_hash=ihash, error=row["error"]))
                rows.append(row)
                continue
            # every op prefix vs predicted step + parent read at previous prefix
            prev = [list(map(int, p)) for p in eraw.tolist()]
            row["reference"] = pred
            row["native_prefixes"] = []
            if len(ops) != len(pred["steps"]):
                errors.append(dict(fixture=key, stage="operation-count", ppem=ppem))
                rows.append(row)
                continue
            ok = True
            for k, op in enumerate(ops):
                end = op["assembly_end"]  # locating only; never expected values
                step = pred["steps"][k]
                stage = "prefix-%d-point-%d-%s" % (
                    k, step["point"], step["kind"])
                try:
                    craw, _, _ = run_ft_raw(pts, nasm[:end], ppem, ncvt or [0])
                    n_prefix += 1
                    cur = [list(map(int, p)) for p in craw.tolist()]
                except Exception as e:
                    ok = False
                    errors.append(dict(fixture=key, stage=stage, ppem=ppem,
                                       input_hash=ihash,
                                       error="%s: %s" % (type(e).__name__, e)))
                    continue
                row["native_prefixes"].append(dict(
                    constraint_id=step["constraint_id"], before=prev, after=cur,
                    parent_current=[prev[s] for s in step["sources"]]))
                if cur != step["after"]:
                    ok = False
                    errors.append(dict(
                        fixture=key, stage=stage, ppem=ppem, input_hash=ihash,
                        constraint_id=step["constraint_id"],
                        expected_after=step["after"], actual=cur))
                if step["before"] != prev:
                    ok = False
                    errors.append(dict(
                        fixture=key, stage=stage + "-before", ppem=ppem,
                        input_hash=ihash, expected_before=step["before"],
                        previous_prefix=prev))
                kind = step["kind"]
                if kind in ("Dist", "PDist"):
                    s = step["sources"][0]
                    if step["parent_cur"] != prev[s] or \
                            step["parent_org"] != pred["initial"][s]:
                        ok = False
                        errors.append(dict(
                            fixture=key, stage=stage + "-parent", ppem=ppem,
                            input_hash=ihash, expected_parent_cur=step["parent_cur"],
                            previous_prefix_parent=prev[s]))
                elif kind == "Ratio":
                    want = [prev[s] for s in step["sources"]]
                    if step["parent_cur"] != want:
                        ok = False
                        errors.append(dict(
                            fixture=key, stage=stage + "-parent", ppem=ppem,
                            input_hash=ihash, expected_parent_cur=step["parent_cur"],
                            previous_prefix_parents=want))
                else:
                    p = step["point"]
                    if step["point_cur_before"] != prev[p]:
                        ok = False
                        errors.append(dict(
                            fixture=key, stage=stage + "-parent", ppem=ppem,
                            input_hash=ihash,
                            expected_point_before=step["point_cur_before"],
                            previous_prefix_point=prev[p]))
                prev = cur
            row["prefix_exact"] = bool(ok)
            # full program vs predicted final
            try:
                fraw, _, _ = run_ft_raw(pts, nasm, ppem, ncvt or [0])
                n_full += 1
                row["full_raw"] = [list(map(int, p)) for p in fraw.tolist()]
                row["full_exact"] = (row["full_raw"] == pred["final"])
                if not row["full_exact"]:
                    errors.append(dict(
                        fixture=key, stage="full", ppem=ppem, input_hash=ihash,
                        expected=pred["final"], actual=row["full_raw"]))
            except Exception as e:
                row["error"] = "full: %s: %s" % (type(e).__name__, e)
                errors.append(dict(fixture=key, stage="full", ppem=ppem,
                                   input_hash=ihash, error=row["error"]))
            rows.append(row)
        case["ppem_rows"] = rows
        cases.append(case)

    counts = dict(fixtures=len(workload), expected_fixtures=EXPECTED_FIXTURES,
                  full=n_full, expected_full=EXPECTED_FULL,
                  empty=n_empty, expected_empty=EXPECTED_EMPTY,
                  prefix=n_prefix, expected_prefix=EXPECTED_PREFIX,
                  skipped=len(skipped), errors=len(errors))
    passed = (len(workload) == EXPECTED_FIXTURES and n_full == EXPECTED_FULL
              and n_empty == EXPECTED_EMPTY and n_prefix == EXPECTED_PREFIX
              and not errors and all(c.get("supported") for c in cases)
              and all(r.get("full_exact") and r.get("empty_matches_initial")
                      and r.get("prefix_exact") for c in cases
                      for r in c.get("ppem_rows", [])))
    report = dict(microsoft_instruction_contract=MS, ft_version=ft_ver, strict_freetype=True,
                  ppems=PPEMS, units="raw26.6",
                  verification_passed=bool(passed), code_hashes=code_hashes,
                  skipped_oblique=skipped, cases=cases,
                  unexpected_errors=errors, counts=counts)
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(counts))
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
