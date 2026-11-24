#!/usr/bin/env python3
"""Deterministic Harbor verifier helpers for orfs-ppa-timing-closure.

Writes /logs/verifier/reward.txt (4 decimal places, [0, 1]) and
/logs/verifier/reward.json (gates, sub-scores, raw PPA).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE = Path(os.environ.get("WORKSPACE", os.environ.get("WORKDIR", "/workspace")))
TESTS_DIR = Path(os.environ.get("TESTS_DIR", "/tests"))
# Harbor uploads task tests/ to /tests, and may overlay step tests/.
# Shared golden/helpers live either at /tests (option 1) or next to this file.
HERE = Path(__file__).resolve().parent
if not (TESTS_DIR / "golden").exists() and (HERE / "golden").exists():
    TESTS_DIR = HERE
if not (TESTS_DIR / "golden").exists() and (HERE.parent / "golden").exists():
    TESTS_DIR = HERE.parent

GOLDEN_DIR = TESTS_DIR / "golden"
GOLDEN_SDC = GOLDEN_DIR / "constraint.sdc"
GOLDEN_RTL = GOLDEN_DIR / "rtl_golden"
GOLDEN_TB = GOLDEN_DIR / "tb_signoff.sv"
SCRIPTS_DIR = TESTS_DIR / "scripts"
BASELINES_PATH = TESTS_DIR / "baselines.json"

RESULTS_DIR = WORKSPACE / "results" / "nangate45" / "aes" / "base"
SYNTH_V = RESULTS_DIR / "1_synth.v"
CTS_ODB = RESULTS_DIR / "4_cts.odb"
FINAL_ODB = RESULTS_DIR / "6_final.odb"
FINAL_V = RESULTS_DIR / "6_final.v"
FINAL_GDS = RESULTS_DIR / "6_final.gds"
FINAL_SPEF = RESULTS_DIR / "6_final.spef"

LOGDIR = Path(os.environ.get("HARBOR_VERIFIER_LOGDIR", "/logs/verifier"))
if not LOGDIR.parent.exists() and not str(LOGDIR).startswith("/logs"):
    pass
if not Path("/logs").exists() and not LOGDIR.exists():
    LOGDIR = Path(os.environ.get("HARBOR_VERIFIER_LOGDIR", WORKSPACE / "logs" / "verifier"))

PLATFORM_DIR = Path(
    os.environ.get("PLATFORM_DIR", "/OpenROAD-flow-scripts/flow/platforms/nangate45")
)
LIBERTY = PLATFORM_DIR / "lib" / "NangateOpenCellLibrary_typical.lib"

ILLEGAL_PATTERNS = [
    (re.compile(r"set_false_path", re.I), "set_false_path"),
    (re.compile(r"set_multicycle_path", re.I), "set_multicycle_path"),
    (re.compile(r"set_disable_timing", re.I), "set_disable_timing"),
    (re.compile(r"set_clock_groups", re.I), "set_clock_groups"),
    (re.compile(r"set_max_delay", re.I), "set_max_delay"),
    (re.compile(r"set_min_delay", re.I), "set_min_delay"),
    (re.compile(r"set_dont_touch", re.I), "set_dont_touch"),
    (re.compile(r"set_annotated_delay", re.I), "set_annotated_delay"),
    (re.compile(r"set_ideal_network", re.I), "set_ideal_network"),
    (re.compile(r"\bCLOCK_PERIOD\s*[+:?]?=", re.I), "CLOCK_PERIOD override"),
    (re.compile(r"create_clock.*-period\s+", re.I), "create_clock in hook/config"),
]


def ensure_logdir() -> Path:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    return LOGDIR


def log(msg: str) -> None:
    ensure_logdir()
    line = msg if msg.endswith("\n") else msg + "\n"
    print(line, end="")
    with (LOGDIR / "verifier.log").open("a") as f:
        f.write(line)


def load_baselines() -> Dict[str, Any]:
    path = BASELINES_PATH
    if not path.exists():
        # bundled next to helpers when tests/ is overlaid
        alt = HERE / "baselines.json"
        path = alt if alt.exists() else path
    with path.open() as f:
        return json.load(f)


def write_reward(reward: float, details: Dict[str, Any]) -> None:
    ensure_logdir()
    reward = max(0.0, min(1.0, float(reward)))
    txt = f"{reward:.4f}\n"
    (LOGDIR / "reward.txt").write_text(txt)
    payload = {"reward": round(reward, 4), **details}
    (LOGDIR / "reward.json").write_text(json.dumps(payload, indent=2) + "\n")
    # Debug copy when /logs is not mounted
    try:
        (WORKSPACE / "out").mkdir(parents=True, exist_ok=True)
        (WORKSPACE / "out" / "reward.txt").write_text(txt)
        (WORKSPACE / "out" / "reward.json").write_text(json.dumps(payload, indent=2) + "\n")
    except Exception:
        pass
    log(f"reward={reward:.4f}")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def _iter_scan_files() -> List[Path]:
    files: List[Path] = []
    for rel in [
        WORKSPACE / "config.mk",
        WORKSPACE / "constraints" / "constraint.sdc",
    ]:
        if rel.is_file():
            files.append(rel)
    override = WORKSPACE / "scripts_override"
    if override.is_dir():
        for p in override.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".tcl", ".sdc", ".mk", ".sh", ".txt"}:
                files.append(p)
    # Common hook drop-ins
    for p in WORKSPACE.glob("*.tcl"):
        files.append(p)
    return files


def golden_clock_period() -> Optional[float]:
    text = _read_text(GOLDEN_SDC)
    m = re.search(r"set\s+clk_period\s+([0-9.]+)", text)
    return float(m.group(1)) if m else None


def sdc_clock_period(path: Path) -> Optional[float]:
    text = _read_text(path)
    m = re.search(r"set\s+clk_period\s+([0-9.]+)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"create_clock[^\n]*-period\s+([0-9.]+)", text)
    return float(m.group(1)) if m else None


def check_config_integrity() -> Tuple[float, List[str]]:
    """Return (G_integrity, reasons). 1.0 only if no cheat is detected."""
    reasons: List[str] = []
    cfg = WORKSPACE / "config.mk"
    cfg_text = _read_text(cfg)

    # SDC_FILE must stay on the workspace (or golden-equivalent) constraint.
    for m in re.finditer(r"^\s*export\s+SDC_FILE\s*\??=\s*(.+)$", cfg_text, re.M):
        val = m.group(1).strip().strip("\"'")
        if val and "constraint.sdc" not in val and "constraints" not in val:
            reasons.append(f"SDC_FILE redirected to {val}")

    ws_sdc = WORKSPACE / "constraints" / "constraint.sdc"
    if ws_sdc.is_file() and GOLDEN_SDC.is_file():
        gper = golden_clock_period()
        wper = sdc_clock_period(ws_sdc)
        if gper is not None and wper is not None and abs(gper - wper) > 1e-9:
            reasons.append(f"workspace SDC period {wper} != golden {gper}")
        # Also catch any extra exception commands in the workspace SDC
        for rx, name in ILLEGAL_PATTERNS:
            if name.startswith("create_clock"):
                continue  # allowed in the official SDC
            if rx.search(_read_text(ws_sdc)):
                reasons.append(f"illegal command in workspace SDC: {name}")

    for path in _iter_scan_files():
        # The starter/golden SDC itself contains create_clock; skip that file
        # for the create_clock rule, already handled above.
        text = _read_text(path)
        for rx, name in ILLEGAL_PATTERNS:
            if path.name == "constraint.sdc" and name == "create_clock in hook/config":
                continue
            if rx.search(text):
                reasons.append(f"{name} in {path}")

    # Top-level module / ports must remain aes_cipher_top with the original ports.
    top = WORKSPACE / "rtl" / "aes_cipher_top.v"
    if not top.is_file():
        reasons.append("missing /workspace/rtl/aes_cipher_top.v")
    else:
        src = _read_text(top)
        if not re.search(r"\bmodule\s+aes_cipher_top\b", src):
            reasons.append("top module aes_cipher_top missing or renamed")
        for port in ("clk", "rst", "ld", "done", "key", "text_in", "text_out"):
            if not re.search(rf"\b{port}\b", src):
                reasons.append(f"port {port} missing from aes_cipher_top")

    if reasons:
        log("integrity FAIL: " + " | ".join(reasons))
        return 0.0, reasons
    log("integrity PASS")
    return 1.0, []


def _rtl_sources(rtl_dir: Path) -> List[Path]:
    files = sorted(p for p in rtl_dir.glob("*.v") if p.is_file())
    return files


def run_functional_sim(rtl_dir: Path, tb_path: Path = GOLDEN_TB) -> Tuple[float, str]:
    """Compile Agent RTL + golden TB with iverilog; require ALL_TESTS_PASSED."""
    if not tb_path.is_file():
        return 0.0, f"missing golden TB {tb_path}"
    sources = _rtl_sources(rtl_dir)
    if not sources:
        return 0.0, f"no Verilog sources in {rtl_dir}"
    ensure_logdir()
    work = Path(tempfile.mkdtemp(prefix="funcsim_"))
    vvp = work / "tb_signoff.vvp"
    log_path = LOGDIR / "funcsim.log"
    cmd = [
        "iverilog",
        "-g2012",
        "-I",
        str(rtl_dir),
        "-o",
        str(vvp),
        *[str(s) for s in sources],
        str(tb_path),
    ]
    try:
        comp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        (log_path).write_text(
            "CMD: " + " ".join(cmd) + "\n" + comp.stdout + "\n" + comp.stderr
        )
        if comp.returncode != 0 or not vvp.exists():
            log(f"func sim compile failed rc={comp.returncode}")
            return 0.0, "iverilog compile failed"
        run = subprocess.run(
            ["vvp", str(vvp)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        with log_path.open("a") as f:
            f.write("\n===== vvp =====\n")
            f.write(out)
        ok = (run.returncode == 0) and ("ALL_TESTS_PASSED" in out)
        log("func sim " + ("PASS" if ok else "FAIL"))
        return (1.0 if ok else 0.0), ("ALL_TESTS_PASSED" if ok else "simulation failed")
    except subprocess.TimeoutExpired:
        log("func sim TIMEOUT")
        return 0.0, "simulation timeout"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_yosys_lec(
    golden_rtl_dir: Path,
    candidate: Path,
    top: str = "aes_cipher_top",
) -> Tuple[float, str]:
    """Yosys combinational/sequential equivalence vs golden RTL.

    Candidate may be a directory of RTL, a single RTL file, or a mapped netlist.
    """
    ensure_logdir()
    log_path = LOGDIR / "lec.log"
    gold_files = _rtl_sources(golden_rtl_dir)
    if not gold_files:
        return 0.0, f"no golden RTL in {golden_rtl_dir}"

    cand_files: List[Path] = []
    is_netlist = False
    if candidate.is_dir():
        cand_files = _rtl_sources(candidate)
    elif candidate.is_file():
        cand_files = [candidate]
        text = _read_text(candidate)
        # Heuristic: mapped ORFS netlists instantiate library cells / dont_touch.
        if "Nangate" in text or "INV_X" in text or "BUF_X" in text or "DFF_X" in text:
            is_netlist = True
    else:
        return 0.0, f"candidate not found: {candidate}"
    if not cand_files:
        return 0.0, f"no candidate sources at {candidate}"

    script = Path(tempfile.mkdtemp(prefix="lec_")) / "check_lec.ys"
    lines = [
        "hierarchy -check",  # placeholder, rewritten below
    ]
    ys: List[str] = []
    # Gold
    for f in gold_files:
        ys.append(f"read_verilog -sv {f}")
    ys += [
        f"hierarchy -top {top}",
        "proc",
        "memory_map",
        "flatten",
        "opt -purge",
        "rename -top gold",
        "design -stash gold",
        "design -reset",
    ]
    # Gate
    if is_netlist and LIBERTY.exists():
        ys.append(f"read_liberty -lib {LIBERTY}")
    for f in cand_files:
        ys.append(f"read_verilog -sv {f}")
    ys += [
        f"hierarchy -top {top}",
        "proc",
        "memory_map",
        "flatten",
        "opt -purge",
        "rename -top gate",
        "design -stash gate",
        "design -reset",
        "design -copy-from gold -as gold gold",
        "design -copy-from gate -as gate gate",
        "equiv_make gold gate equiv",
        "equiv_simple -seq 10",
        "equiv_induct -seq 10",
        "equiv_status -assert",
    ]
    script.write_text("\n".join(ys) + "\n")
    try:
        run = subprocess.run(
            ["yosys", "-q", "-s", str(script)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        log_path.write_text("SCRIPT:\n" + script.read_text() + "\n===== yosys =====\n" + out)
        ok = run.returncode == 0
        log("LEC " + ("PASS" if ok else "FAIL"))
        return (1.0 if ok else 0.0), ("equiv_status ok" if ok else "LEC failed")
    except subprocess.TimeoutExpired:
        log("LEC TIMEOUT")
        return 0.0, "LEC timeout"
    finally:
        shutil.rmtree(script.parent, ignore_errors=True)



def _kepler_bin() -> Optional[str]:
    return shutil.which("kepler-formal")


def run_kepler_netlist_lec(net1: Path, net2: Path) -> Tuple[float, str]:
    """Independently LEC two liberty-mapped netlists with Kepler Formal (KISSAT).

    Yosys equiv_induct cannot build a SAT model for Nangate DFF_X1 cells when
    they are read as liberty black boxes, and functional liberty + induct is
    too slow for the verifier budget. Kepler is the ORFS bundled checker.
    """
    ensure_logdir()
    exe = _kepler_bin()
    if not exe:
        return 0.0, "kepler-formal not found"
    if not net1.is_file() or not net2.is_file():
        return 0.0, f"missing netlist ({net1} / {net2})"
    if not LIBERTY.is_file():
        return 0.0, f"missing liberty {LIBERTY}"
    work = Path(tempfile.mkdtemp(prefix="kepler_lec_"))
    cfg = work / "lec.yml"
    logf = work / "kepler.log"
    cfg.write_text(
        "format: verilog\n"
        "input_paths:\n"
        f"  - {net1}\n"
        f"  - {net2}\n"
        "liberty_files:\n"
        f"  - {LIBERTY}\n"
        f"log_file: {logf}\n"
    )
    try:
        run = subprocess.run(
            [exe, "--config", str(cfg)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (run.stdout or "") + "\n" + (run.stderr or "")
        logtxt = logf.read_text() if logf.is_file() else ""
        (LOGDIR / "kepler_lec.log").write_text(out + "\n===== log =====\n" + logtxt)
        blob = out + "\n" + logtxt
        if "Circuits are IDENTICAL" in blob or "No difference was found" in blob:
            log("netlist LEC PASS (kepler)")
            return 1.0, "kepler: circuits identical"
        return 0.0, "kepler: difference or error"
    except subprocess.TimeoutExpired:
        return 0.0, "kepler LEC timeout"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def extract_signoff_metrics(odb: Path = FINAL_ODB, spef: Optional[Path] = None) -> Dict[str, Any]:
    """Recompute PPA/DRC from the ODB with the golden SDC. Never trust agent reports."""
    ensure_logdir()
    if not odb.is_file():
        raise FileNotFoundError(str(odb))
    if spef is None and FINAL_SPEF.is_file():
        spef = FINAL_SPEF
    out_json = LOGDIR / "signoff_metrics.json"
    tcl = SCRIPTS_DIR / "extract_signoff_metrics.tcl"
    if not tcl.is_file():
        # helpers may live beside scripts/ when tests/ is mounted as /tests
        alt = HERE / "scripts" / "extract_signoff_metrics.tcl"
        tcl = alt if alt.exists() else tcl
    env = os.environ.copy()
    env["SIGNOFF_ODB"] = str(odb)
    env["GOLDEN_SDC"] = str(GOLDEN_SDC)
    env["METRICS_JSON"] = str(out_json)
    env["PLATFORM_DIR"] = str(PLATFORM_DIR)
    if spef and spef.is_file():
        env["SPEF_FILE"] = str(spef)
    cmd = ["openroad", "-no_init", "-no_splash", "-exit", str(tcl)]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    (LOGDIR / "signoff_extract.log").write_text(
        "CMD: " + " ".join(cmd) + "\n" + (run.stdout or "") + "\n" + (run.stderr or "")
    )
    if not out_json.is_file():
        raise RuntimeError(f"signoff metrics not written (rc={run.returncode})")
    with out_json.open() as f:
        metrics = json.load(f)
    power_json = out_json.parent / "power.json"
    if power_json.is_file():
        try:
            pdata = json.loads(power_json.read_text())
            total = pdata.get("Total") or {}
            if total.get("total") is not None:
                metrics["internal_power_w"] = float(total.get("internal"))
                metrics["switching_power_w"] = float(total.get("switching"))
                metrics["leakage_power_w"] = float(total.get("leakage"))
                metrics["total_power_w"] = float(total["total"])
        except Exception as exc:
            log(f"warning: failed to parse power.json: {exc}")
    # Persist merged power so signoff_metrics.json is the complete source of truth.
    out_json.write_text(json.dumps(metrics, indent=2) + "\n")
    log("signoff metrics: " + json.dumps(metrics, sort_keys=True))
    return metrics


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str) and x.upper() in {"INF", "INFINITY", "N/A", ""}:
            return default
        return float(x)
    except Exception:
        return default


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def compute_final_reward(
    metrics: Dict[str, Any],
    baselines: Dict[str, Any],
    gates: Dict[str, float],
) -> Tuple[float, Dict[str, Any]]:
    """R = G_int * G_func * G_flow * clip(0.45 St + 0.30 Sa + 0.15 Sp + 0.10 Sq, 0, 1)."""
    details: Dict[str, Any] = {
        "metrics": metrics,
        "gates": gates,
    }
    g_int = float(gates.get("G_integrity", gates.get("integrity", 0.0)))
    g_func = float(gates.get("G_func", gates.get("func", 0.0)))
    g_flow = float(gates.get("G_flow", gates.get("flow", 0.0)))
    details["G_integrity"] = g_int
    details["G_func"] = g_func
    details["G_flow"] = g_flow

    b = baselines.get("baseline") or {}
    o = baselines.get("oracle") or {}
    tol = float(baselines.get("tolerance") or 0.02)

    wns = _f(metrics.get("wns_setup"))
    tns = _f(metrics.get("tns_setup"))
    wns_b = _f(b.get("wns_setup"), -1.0)
    wns_o_meas = o.get("wns_setup")
    # Positive WNS oracle anchor is measured * (1 - tolerance), per the plan.
    # Fall back to 0.05 ns only when the oracle WNS has not been locked yet.
    if wns_o_meas is None:
        wns_o = 0.05
    else:
        wns_o_meas_f = _f(wns_o_meas, 0.0)
        wns_o = wns_o_meas_f * (1.0 - tol) if wns_o_meas_f > 0 else 0.05

    if wns < 0:
        denom = 0.0 - wns_b
        s_timing = 0.65 * clip01((wns - wns_b) / denom) if abs(denom) > 1e-12 else 0.0
    elif tns >= -1e-6:
        s_timing = 0.75 + 0.25 * clip01(wns / max(wns_o, 1e-12))
    else:
        # WNS >= 0 but TNS still negative (shouldn't happen); treat as not fully closed.
        s_timing = 0.65

    def _lower_better(metric_key: str, meas_key: Optional[str] = None) -> float:
        key = meas_key or metric_key
        a = _f(metrics.get(key), 0.0)
        a_b = _f(b.get(key), 0.0)
        a_o_meas = o.get(key)
        if a_o_meas is None or a_b <= 0:
            return 0.0
        # Relax the oracle (lower-is-better) anchor by +2%.
        a_o = _f(a_o_meas) * (1.0 + tol)
        denom = a_b - a_o
        if abs(denom) <= 1e-18:
            return 1.0 if a <= a_o else 0.0
        return clip01((a_b - a) / denom)

    # Prefer core area; fall back to stdcell / die.
    if metrics.get("core_area_um2") and b.get("core_area_um2"):
        s_area = _lower_better("core_area_um2")
        area_key = "core_area_um2"
    elif metrics.get("stdcell_area_um2") and b.get("stdcell_area_um2"):
        s_area = _lower_better("stdcell_area_um2")
        area_key = "stdcell_area_um2"
    else:
        s_area = _lower_better("die_area_um2")
        area_key = "die_area_um2"
    s_power = _lower_better("total_power_w")

    ant = int(_f(metrics.get("antenna_violations"), 99))
    slew = int(_f(metrics.get("max_slew_violations"), 99))
    cap = int(_f(metrics.get("max_cap_violations"), 99))
    fan = int(_f(metrics.get("max_fanout_violations"), 99))
    s_phys = 0.5 * (1.0 if ant == 0 else 0.0) + 0.5 * (
        1.0 if (slew == 0 and cap == 0 and fan == 0) else 0.0
    )

    weighted = 0.45 * s_timing + 0.30 * s_area + 0.15 * s_power + 0.10 * s_phys
    weighted = clip01(weighted)
    reward = g_int * g_func * g_flow * weighted
    details.update(
        {
            "S_timing": round(s_timing, 6),
            "S_area": round(s_area, 6),
            "S_power": round(s_power, 6),
            "S_phys": round(s_phys, 6),
            "area_key": area_key,
            "weighted": round(weighted, 6),
            "wns_setup": wns,
            "tns_setup": tns,
        }
    )
    return reward, details


def check_synth_artifact() -> Tuple[float, str]:
    if SYNTH_V.is_file() and SYNTH_V.stat().st_size > 0:
        # Reject empty / obviously broken netlists
        text = _read_text(SYNTH_V)
        if "endmodule" in text or "module" in text:
            return 1.0, str(SYNTH_V)
    return 0.0, f"missing or invalid {SYNTH_V}"


def check_cts_artifact() -> Tuple[float, str]:
    if not CTS_ODB.is_file() or CTS_ODB.stat().st_size < 1000:
        return 0.0, f"missing or tiny {CTS_ODB}"
    # Light-weight legality: openroad can read the db and see instances.
    ensure_logdir()
    tcl = Path(tempfile.mkdtemp(prefix="ctscheck_")) / "check_cts.tcl"
    tcl.write_text(
        "\n".join(
            [
                f"if {{[catch {{read_db {CTS_ODB}}} err]}} {{ puts \"READ_FAIL $err\"; exit 1 }}",
                "set block [ord::get_db_block]",
                "if {$block eq \"NULL\"} { puts {NO_BLOCK}; exit 1 }",
                "set n [llength [$block getInsts]]",
                "puts \"CTS_INSTS $n\"",
                "if {$n < 100} { exit 1 }",
                "exit 0",
                "",
            ]
        )
    )
    try:
        run = subprocess.run(
            ["openroad", "-no_init", "-no_splash", "-exit", str(tcl)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        (LOGDIR / "cts_check.log").write_text((run.stdout or "") + (run.stderr or ""))
        ok = run.returncode == 0 and "CTS_INSTS" in (run.stdout or "")
        return (1.0 if ok else 0.0), ("4_cts.odb ok" if ok else "4_cts.odb not a legal design db")
    except subprocess.TimeoutExpired:
        return 0.0, "cts odb check timeout"
    finally:
        shutil.rmtree(tcl.parent, ignore_errors=True)


def compute_flow_gate(metrics: Optional[Dict[str, Any]], baselines: Dict[str, Any]) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    if not FINAL_ODB.is_file():
        reasons.append("missing 6_final.odb")
    if not FINAL_GDS.is_file() or FINAL_GDS.stat().st_size < 100:
        reasons.append("missing 6_final.gds")
    if metrics is None:
        reasons.append("signoff metrics unavailable")
        return 0.0, reasons
    hold_min = float((baselines.get("gates") or {}).get("hold_wns_min_ns", 0.0))
    drc_max = int((baselines.get("gates") or {}).get("drc_max", 0))
    wns_hold = _f(metrics.get("wns_hold"), -1e9)
    drc = int(_f(metrics.get("drc_violations"), 999999))
    if wns_hold < hold_min:
        reasons.append(f"hold WNS {wns_hold} < {hold_min}")
    if drc > drc_max:
        reasons.append(f"DRC {drc} > {drc_max}")
    return (0.0 if reasons else 1.0), reasons


def evaluate_step1() -> int:
    ensure_logdir()
    g_int, reasons = check_config_integrity()
    g_func, func_msg = run_functional_sim(WORKSPACE / "rtl", GOLDEN_TB)
    g_lec, lec_msg = run_yosys_lec(GOLDEN_RTL, WORKSPACE / "rtl")
    g_synth, synth_msg = check_synth_artifact()
    # If a netlist exists, also LEC it (best-effort; RTL LEC remains the gate).
    lec_net = None
    if g_synth == 1.0:
        try:
            lec_net, lec_net_msg = run_yosys_lec(GOLDEN_RTL, SYNTH_V)
            log(f"netlist LEC: {lec_net_msg}")
        except Exception as exc:
            lec_net, lec_net_msg = 0.0, str(exc)
    passed = g_int == 1.0 and g_func == 1.0 and g_lec == 1.0 and g_synth == 1.0
    reward = 1.0 if passed else 0.0
    details = {
        "func_pass": g_func,
        "lec_pass": g_lec,
        "synth_pass": g_synth,
        "integrity": g_int,
        "G_integrity": g_int,
        "G_func": g_func if g_lec == 1.0 else 0.0,
        "func_msg": func_msg,
        "lec_msg": lec_msg,
        "synth_msg": synth_msg,
        "integrity_reasons": reasons,
        "lec_netlist_pass": lec_net,
        "step": "step-1-frontend-synth",
    }
    write_reward(reward, details)
    return 0


def evaluate_step2() -> int:
    ensure_logdir()
    g_int, reasons = check_config_integrity()
    g_cts, cts_msg = check_cts_artifact()
    reward = 1.0 if (g_int == 1.0 and g_cts == 1.0) else 0.0
    details = {
        "cts_pass": g_cts if g_int == 1.0 else 0.0,
        "integrity": g_int,
        "G_integrity": g_int,
        "cts_msg": cts_msg,
        "integrity_reasons": reasons,
        "step": "step-2-place-cts",
    }
    write_reward(reward, details)
    return 0


def evaluate_step3() -> int:
    ensure_logdir()
    baselines = load_baselines()
    g_int, reasons = check_config_integrity()
    g_func, func_msg = run_functional_sim(WORKSPACE / "rtl", GOLDEN_TB)
    # LEC RTL vs golden; also try final netlist if present.
    g_lec, lec_msg = run_yosys_lec(GOLDEN_RTL, WORKSPACE / "rtl")
    final_lec = RESULTS_DIR / "6_final_lec.v"
    synth_lec = RESULTS_DIR / "1_synth_lec.v"
    net_gate = final_lec if final_lec.is_file() else FINAL_V
    net_gold = synth_lec if synth_lec.is_file() else (RESULTS_DIR / "1_synth.v")
    if net_gate.is_file() and net_gold.is_file():
        try:
            lec_v, lec_v_msg = run_kepler_netlist_lec(net_gold, net_gate)
            log(f"netlist LEC ({net_gold.name} vs {net_gate.name}): {lec_v_msg}")
            if lec_v != 1.0:
                g_lec = 0.0
                lec_msg = lec_v_msg
        except Exception as exc:
            log(f"netlist LEC error: {exc}")
            g_lec = 0.0
            lec_msg = str(exc)
    elif FINAL_V.is_file():
        # Fall back to Yosys only if Kepler ingredients are missing.
        try:
            lec_v, lec_v_msg = run_yosys_lec(GOLDEN_RTL, FINAL_V)
            log(f"6_final.v LEC: {lec_v_msg}")
            if lec_v != 1.0:
                g_lec = 0.0
                lec_msg = lec_v_msg
        except Exception as exc:
            log(f"6_final.v LEC error: {exc}")
    g_func_gate = 1.0 if (g_func == 1.0 and g_lec == 1.0) else 0.0

    metrics = None
    extract_err = None
    if FINAL_ODB.is_file():
        try:
            metrics = extract_signoff_metrics(FINAL_ODB)
        except Exception as exc:
            extract_err = str(exc)
            log(f"signoff extract failed: {exc}")
    g_flow, flow_reasons = compute_flow_gate(metrics, baselines)
    gates = {
        "G_integrity": g_int,
        "G_func": g_func_gate,
        "G_flow": g_flow,
    }
    if metrics is None:
        reward, details = 0.0, {
            "S_timing": 0.0,
            "S_area": 0.0,
            "S_power": 0.0,
            "S_phys": 0.0,
            "extract_error": extract_err,
        }
    else:
        reward, details = compute_final_reward(metrics, baselines, gates)
    details.update(
        {
            "func_pass": g_func,
            "lec_pass": g_lec,
            "func_msg": func_msg,
            "lec_msg": lec_msg,
            "integrity_reasons": reasons,
            "flow_reasons": flow_reasons,
            "step": "step-3-route-signoff",
        }
    )
    # If any hard gate failed, force 0.0000 regardless of weighted sub-scores.
    if g_int != 1.0 or g_func_gate != 1.0 or g_flow != 1.0:
        reward = 0.0
        details["G_integrity"] = g_int
        details["G_func"] = g_func_gate
        details["G_flow"] = g_flow
    write_reward(reward, details)
    return 0


if __name__ == "__main__":
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "step3"
    if which in {"step1", "step-1", "step-1-frontend-synth"}:
        raise SystemExit(evaluate_step1())
    if which in {"step2", "step-2", "step-2-place-cts"}:
        raise SystemExit(evaluate_step2())
    raise SystemExit(evaluate_step3())
