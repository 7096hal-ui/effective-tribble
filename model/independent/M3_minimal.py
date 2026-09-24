#!/usr/bin/env python3
"""M3_minimal -- minimal-skeptic model of hourly study value, 365 days.

Structure (three multiplicative layers, no hidden terms):

  Q(t,h)  ∝  K(t) * S_day(t) * V_t(h)                         (K = knowledge level, cancels in R and A)

  S_day(t) = (1 - beta_s * X_t) * (1 - C_t - Z_t) * (1 - iota*irregular)   start-of-day state
      X_t : sleep-debt state = EWMA (time constant tau_X) of nightly shortfall (N - actual sleep), >= 0
      C_t : multi-day study-load state (time constant tau_C) -> target c_max * g(H) * (1 - lam_L*leisure_eff)
            a full rest day multiplies C by (1 - rho_rest)  (never a full reset)
      Z_t : slow (months) load state, target m_slow * g(H) * (...), tau_Z = 90 d
  V_t(h) = w(h) * alloc(D) * (1 - dip*dipf(h)) * (1 - gamma_w * max(0, wake(h) - (W0 - X_t)))
      D   = D14_eff(t) * (1 + kappa*X_t) * shape(L(h)/13.5)       within-day decline, 4 candidate shapes
      L(h)= (1-phi) * [study hours before h] + phi * [study hours since last meal break]   (+ midpoint)
      alloc(D) = max(1 - D, v_low * (1 - 0.5*D))   (switch to lower-demand review when it is worth more)
      w(1) = 1 - u (warm-up), w(h>1) = 1;  dipf = 1 / 0.5 for first / second hour after lunch
      D14_eff(t) = D14 * (1 - alpha_ad * (1 - exp(-t/30)))   (endurance adaptation, small)

  R(t,h) = 100 * V_t(h) / V_t(1)                                (so R(t,1) = 100 exactly)
  A(t,h) = 100 * S_day(t) * V_t(h) / Q_ref,  Q_ref = V of hour 1 with X=C=Z=0 (rested twin)
  RHE    = sum over studied (nominal) hours of A/100.
  Engaged fraction e(h) is reported as a decomposition only: e(h) = e0*(1 - sigma_e*(1 - V/Vpeak)),
  efficiency per engaged minute k(h) = (V/Vpeak)/(e/e0). The split changes no reported number.

Every parameter is swept by Latin hypercube (per within-day form). Bands are 5th-95th percentiles
of the assumption sweep -- NOT confidence intervals.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time

import numpy as np
from scipy.stats import qmc, spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, "/home/user/effective-tribble/model")
from time_budget import BUDGETS, max_study_hours  # noqa: E402

SEED = 20260924
N_PER_FORM = int(os.environ.get("M3_N", "600"))
FORMS = ["linear", "convex", "hinge", "saturating"]
NDAYS = 365
NSEG = 15
L_NORM = 13.5          # effective load of the 14th hour with no breaks at all
W0 = 16.0              # wake hours kept roughly stable by circadian drive when rested (digest s2)
TAU_Z = 90.0
TAU_AD = 30.0
E0, SIGMA_E = 0.85, 0.5
P1_SLEEP_TARGET = float(os.environ.get("M3_P1_TARGET", "8.3"))   # prompt-1: freed time -> sleep up to this
SLEEP_CAP = 10.0

# name, central, lo, hi, label, basis
PARAMS = [
    ("D14", 0.35, 0.05, 0.70, "assumption",
     "Within-day decline of demanding-task learning value at the no-break load of hour 14 (rested, pre-adaptation). "
     "Digest s2/s6: nothing measures learning after ~6 h; anchors Ackerman 2009/2010 (no objective decline 3.5-5.5 h), "
     "Blain 2016/Wiehler 2022 (low-effort shift after ~6 h), Sievertsen 2016 (-0.9% SD/h), Pencavel 2015 (output max ~63 h/wk)."),
    ("phi", 0.40, 0.10, 0.70, "indirect_estimate",
     "Share of within-day load that is transient (reset by a meal break). Sievertsen 2016: 20-30 min break +1.7% SD vs "
     "-0.9% SD/h (~2 h of decline recovered); Hopstaken 2015 reversibility; Albulescu 2022 performance d=0.16 n.s."),
    ("u", 0.03, 0.00, 0.08, "assumption",
     "Warm-up penalty of the first hour (settling in). No direct anchor; allows R(2) > 100."),
    ("dip", 0.04, 0.00, 0.10, "indirect_estimate",
     "Post-lunch dip in first post-lunch hour (half in second). Monk 2005 variable dip; Pope 2016 afternoon penalty."),
    ("v_low", 0.60, 0.35, 0.85, "assumption",
     "Value of lower-demand work (spaced retrieval review, error log) relative to rested demanding work; it is half as "
     "fatigue-sensitive. Rowland 2014 g=0.50 (retrieval valuable); Rohrer 2005/2006 (massed overlearning low value)."),
    ("gamma_w", 0.05, 0.00, 0.12, "indirect_estimate",
     "Loss per hour awake beyond W0 - X (W0 = 16 h). Dijk & Czeisler 1994, Wright 2002 (stable ~16 h when rested); "
     "Van Dongen 2003 critical wake 15.84 h."),
    ("kappa", 0.10, 0.00, 0.25, "assumption",
     "Steepening of within-day decline per hour of chronic sleep shortfall (vigilance time-on-task x sleep loss; not in digest)."),
    ("N", 8.40, 8.00, 8.90, "literature_constrained",
     "Actual sleep need (h). Van Dongen 2003 implied 8.16; Kitamura 2016 8.4 (7.3-9.3); Klerman & Dijk 8.9."),
    ("beta_s", 0.05, 0.02, 0.09, "indirect_estimate",
     "Start-of-day learning loss per hour of chronic nightly shortfall. Lowe 2017 LTM g=-0.19, executive -0.32; "
     "Cousins 2018, Lo 2016 (encoding, adolescents); Crowley 2024 (restriction ~ deprivation). PVT->learning mapping untested."),
    ("tau_X", 4.0, 2.0, 8.0, "indirect_estimate",
     "Sleep-debt state time constant (days). Belenky 2003 stabilises after ~4 d; Kitamura 2016 ~4 d to repay 1 h; "
     "McCauley 2009 equilibrium below ~20 h wake."),
    ("ext", 1.0, 0.5, 2.0, "assumption",
     "Extra sleep on the night before a full rest day (h); half of it before a partial rest day."),
    ("iota", 0.03, 0.00, 0.06, "assumption",
     "S3 only: extra start-of-day loss from irregular sleep timing / low efficiency."),
    ("c_max", 0.10, 0.00, 0.30, "assumption",
     "Multi-day load target at 14 h/day, zero leisure (start-of-day loss). Madigan & Curran 2021 burnout r=-0.24 "
     "(correlational); Pencavel 2015; digest s6: not pinned down."),
    ("H_s", 6.0, 4.0, 9.0, "indirect_estimate",
     "Daily hours below which no multi-day load accumulates. Pencavel ~49 h/wk proportional (~8 h/d x 6); "
     "Ericsson 1993 ~4 h/d (narrative)."),
    ("tau_C", 5.0, 3.0, 14.0, "indirect_estimate",
     "Multi-day load time constant (days). de Bloom 2009 (vacation effect fades 2-4 wk), Speth 2024 (~1 wk)."),
    ("rho_rest", 0.50, 0.20, 0.80, "assumption",
     "Fraction of multi-day load removed by one full rest day (half for a partial day). Binnewies 2010; "
     "digest: a rest day must not fully reset."),
    ("lam_L", 0.30, 0.00, 0.60, "assumption",
     "Max relative reduction of the load target from daily free leisure (saturates at 2 h)."),
    ("m_slow", 0.03, 0.00, 0.08, "assumption",
     "Slow (tau 90 d) load target at full load; allows late-year drift. No evidence on months-scale accumulation."),
    ("alpha_ad", 0.10, 0.00, 0.25, "indirect_estimate",
     "Fractional reduction of within-day decline by endurance adaptation (tau 30 d). Brown et al. 2025 QJE (22% less "
     "within-test decline after practice)."),
]
PNAMES = [p[0] for p in PARAMS]
SHAPE = {  # form-specific shape parameter: central, lo, hi, meaning
    "linear": (0.0, 0.0, 0.0, "none"),
    "convex": (2.0, 1.5, 3.0, "exponent p in D*x^p"),
    "hinge": (5.5, 3.0, 8.0, "onset (h of effective load) of a linear decline"),
    "saturating": (0.30, 0.15, 0.50, "scale c of (1-exp(-x/c)) front-loaded decline"),
}

# ----------------------------------------------------------------------------------------------
# parameter sets
# ----------------------------------------------------------------------------------------------

def make_sweep(n_per_form=N_PER_FORM, seed=SEED):
    cols = {k: [] for k in PNAMES}
    form, shp = [], []
    for fi, f in enumerate(FORMS):
        sampler = qmc.LatinHypercube(d=len(PARAMS) + 1, seed=seed + fi)
        U = sampler.random(n_per_form)
        for j, (name, c, lo, hi, *_rest) in enumerate(PARAMS):
            cols[name].append(lo + (hi - lo) * U[:, j])
        c, lo, hi, _ = SHAPE[f]
        shp.append(lo + (hi - lo) * U[:, -1])
        form.append(np.full(n_per_form, fi))
    P = {k: np.concatenate(v) for k, v in cols.items()}
    P["form"] = np.concatenate(form)
    P["shp"] = np.concatenate(shp)
    return P


def make_central():
    P = {name: np.array([c] * len(FORMS), float) for (name, c, *_r) in PARAMS}
    P["form"] = np.arange(len(FORMS))
    P["shp"] = np.array([SHAPE[f][0] for f in FORMS], float)
    return P


def subset(P, mask):
    return {k: v[mask] for k, v in P.items()}


def shape_fn(x, P):
    """x: (n, s) normalized load. returns shape in [0, ~1]."""
    f = P["form"][:, None]
    shp = P["shp"][:, None]
    x = np.clip(x, 0.0, 1.3)
    lin = x
    p = np.where(f == 1, shp, 1.0)
    cvx = x ** p
    xh = np.where(f == 2, shp / L_NORM, 0.0)
    hin = np.maximum(0.0, x - xh) / (1.0 - xh)
    c = np.where(f == 3, shp, 1.0)
    sat = (1.0 - np.exp(-x / c)) / (1.0 - np.exp(-1.0 / c))
    return np.select([f == 0, f == 1, f == 2, f == 3], [lin, cvx, hin, sat])


# ----------------------------------------------------------------------------------------------
# day geometry and schedules
# ----------------------------------------------------------------------------------------------
_GEOM = {}


def geom(H, life):
    key = (round(H, 4), round(life, 4))
    if key in _GEOM:
        return _GEOM[key]
    m = np.zeros(NSEG); ns = np.zeros(NSEG); wake = np.zeros(NSEG)
    dipf = np.zeros(NSEG); wt = np.zeros(NSEG); first = np.zeros(NSEG, bool)
    if H >= 7:
        B = [math.floor(H * 5 / 14 + 0.5), math.floor(H * 10 / 14 + 0.5)]
    elif H >= 3.5:
        B = [math.floor(H / 2 + 0.5)]
    else:
        B = []
    durs = [0.25 * life, 0.25 * life][: len(B)]
    pre = 0.30 * life
    nfull = int(math.ceil(H - 1e-9))
    for k in range(min(nfull, NSEG)):
        w = min(1.0, H - k)
        mid = k + w / 2
        last = max([0.0] + [b for b in B if b <= mid])
        m[k] = mid
        ns[k] = mid - last
        wake[k] = pre + mid + sum(d for b, d in zip(B, durs) if b <= mid)
        wt[k] = w
        if B:
            b1 = B[0]
            if b1 < mid <= b1 + 1:
                dipf[k] = 1.0
            elif b1 + 1 < mid <= b1 + 2:
                dipf[k] = 0.5
    first[0] = True
    g = dict(m=m, ns=ns, wake=wake, dipf=dipf, wt=wt, first=first, B=B)
    _GEOM[key] = g
    return g


def cycle_positions(r, p):
    """1-based positions (1..14) of r full rest days and p partial days in a 14-day cycle."""
    rest = sorted({int(math.floor(14 * k / r + 0.5)) for k in range(1, r + 1)})
    part = []
    for _ in range(p):
        best, bestd = None, -1
        for d in range(1, 15):
            if d in rest or d in part:
                continue
            occ = rest + part
            dist = min(min(abs(d - o), 14 - abs(d - o)) for o in occ)
            if dist > bestd:
                best, bestd = d, dist
        part.append(best)
    return rest, sorted(part)


def make_schedule(H, life, tib, eff, r=1, p=0, irregular=0.0, name=""):
    """Day arrays. sleep_base[d] = actual sleep on the night before day d (without the ext bonus);
    ext_flag[d] = multiplier of the per-sample ext bonus on that night. leisure on study days is the leftover."""
    rest_pos, part_pos = cycle_positions(r, p)
    Hd = np.zeros(NDAYS); rest = np.zeros(NDAYS, bool); part = np.zeros(NDAYS, bool)
    ext_flag = np.zeros(NDAYS)
    for d in range(NDAYS):
        c = d % 14 + 1
        if c in rest_pos:
            rest[d] = True; ext_flag[d] = 1.0
        elif c in part_pos:
            part[d] = True; Hd[d] = H / 2; ext_flag[d] = 0.5
        else:
            Hd[d] = H
    sleep = tib * eff
    leis_study = 24.0 - H - life - tib
    leis = np.where(rest, 24.0 - life - tib, 24.0 - Hd - life - tib)
    return dict(name=name, H=H, Hd=Hd, rest=rest, part=part, ext_flag=ext_flag, life=life, tib=tib, eff=eff,
                sleep_base=np.full(NDAYS, sleep), leis=leis, leis_study=leis_study, irregular=irregular,
                r=r, p=p)


P1_SCEN = {  # prompt-1 scenarios at 14 h (digest s1)
    "S1": dict(life=1.75, tib=8.25, sleep=7.6, irregular=0.0),
    "S2": dict(life=2.50, tib=7.50, sleep=7.0, irregular=0.0),
    "S3": dict(life=3.00, tib=7.00, sleep=6.3, irregular=1.0),
}


def prompt1_schedule(S, H, target=None):
    target = P1_SLEEP_TARGET if target is None else target
    sc = P1_SCEN[S]
    eff = sc["sleep"] / sc["tib"]
    freed = 14.0 - H
    tib = min(sc["tib"] + freed, max(sc["tib"], target / eff))
    s = make_schedule(H, sc["life"], tib, eff, 1, 0, sc["irregular"], name=f"prompt1_{S}_H{H}")
    s["framework"] = "prompt1"; s["variant"] = "feasible"
    return s


BUD = {"tight": BUDGETS[0], "base": BUDGETS[1], "generous": BUDGETS[2]}


def prompt2_schedule(bname, H, r=1, p=0, variant="auto"):
    b = BUD[bname]
    eff = b.sleep_efficiency
    life = b.non_sleep_non_study() / 60.0
    tib = 8.0 / eff
    leftover = 24.0 - tib - life - H
    feasible = leftover >= -1e-9
    v = "feasible"
    if not feasible:
        if variant in ("auto", "sleep_cut"):
            tib = 24.0 - life - H
            v = "sleep_cut"
        elif variant == "drop_exmed":
            life = life - b.exercise_per_day() / 60.0 - b.meditation / 60.0
            v = "drop_exercise_meditation"
            if 24.0 - tib - life - H < 0:
                tib = 24.0 - life - H
                v += "+sleep_cut"
    s = make_schedule(H, life, tib, eff, r, p, 0.0, name=f"prompt2_{bname}_H{H}_r{r}_p{p}_{v}")
    s["framework"] = f"prompt2_{bname}"; s["variant"] = v; s["feasible"] = feasible
    return s


def budget_check(s, ext_values=(0.5, 1.0, 2.0)):
    """Verify study + TIB + life + leisure = 24 h on every day, leisure >= 0, for ext range."""
    errs = []
    for ext in ext_values:
        sleep = np.minimum(s["sleep_base"] + ext * s["ext_flag"], SLEEP_CAP)
        tib = sleep / s["eff"]
        leis = s["leis"] - (tib - s["tib"])          # extra sleep comes out of that day's leisure
        tot = s["Hd"] + tib + s["life"] + leis
        errs.append(float(np.max(np.abs(tot - 24.0))))
        if np.min(leis) < -1e-6:
            return False, f"negative leisure {np.min(leis):.3f} at ext={ext}"
    ok = max(errs) < 1e-9 and s["leis_study"] >= -1e-9
    return ok, f"max |sum-24|={max(errs):.1e}; study-day leisure {s['leis_study']:.2f} h; TIB {s['tib']:.2f}; sleep {s['tib']*s['eff']:.2f}"


# ----------------------------------------------------------------------------------------------
# simulation
# ----------------------------------------------------------------------------------------------

def simulate(s, P, windows=None):
    n = len(P["form"])
    X = np.zeros(n); C = np.zeros(n); Z = np.zeros(n)
    seg_rhe = np.zeros((n, NSEG))
    rec = None
    if windows:
        rec = {w: dict(A=np.zeros((n, 14)), R=np.zeros((n, 14)), Rs=np.zeros((n, 14)), As=np.zeros((n, 14)),
                       V=np.zeros((n, 14)), Sday=np.zeros(n), X=np.zeros(n), C=np.zeros(n), Z=np.zeros(n), cnt=0)
               for w in windows}
        day2win = {}
        for w, days in windows.items():
            for d in days:
                day2win.setdefault(d, []).append(w)
    phi = P["phi"][:, None]; u = P["u"]; dip = P["dip"][:, None]; vlow = P["v_low"][:, None]
    gam = P["gamma_w"][:, None]; kap = P["kappa"]
    x_ref = np.full((n, 1), 0.5 / L_NORM)
    s_ref = shape_fn(x_ref, P)[:, 0]
    daily_rhe = np.zeros((n, NDAYS))
    for d in range(NDAYS):
        sleep = np.minimum(s["sleep_base"][d] + P["ext"] * s["ext_flag"][d], SLEEP_CAP)
        X = X + ((P["N"] - sleep) - X) / P["tau_X"]
        X = np.maximum(X, 0.0)
        D14e = P["D14"] * (1.0 - P["alpha_ad"] * (1.0 - math.exp(-d / TAU_AD)))
        Hd = s["Hd"][d]
        leis = s["leis"][d]
        leis_eff = min(max(leis, 0.0), 2.0) / 2.0
        if Hd > 0:
            g = geom(Hd, s["life"])
            L = (1 - phi) * g["m"][None, :] + phi * g["ns"][None, :]
            sh = shape_fn(L / L_NORM, P)
            Dm = (D14e * (1.0 + kap * X))[:, None]
            D = np.clip(Dm * sh, 0.0, 0.95)
            alloc = np.maximum(1.0 - D, vlow * (1.0 - 0.5 * D))
            pen = np.clip(gam * np.maximum(0.0, g["wake"][None, :] - (W0 - X[:, None])), 0.0, 1.0)
            warm = np.where(g["first"][None, :], (1.0 - u)[:, None], 1.0)
            V = warm * alloc * (1.0 - dip * g["dipf"][None, :]) * (1.0 - pen)
            Dref = np.clip(D14e * s_ref, 0.0, 0.95)
            Qref = (1.0 - u) * np.maximum(1.0 - Dref, P["v_low"] * (1.0 - 0.5 * Dref))
            Sday = (1.0 - P["beta_s"] * X) * (1.0 - C - Z) * (1.0 - P["iota"] * s["irregular"])
            Sday = np.clip(Sday, 0.0, 1.0)
            A = 100.0 * Sday[:, None] * V / Qref[:, None]
            contrib = A * g["wt"][None, :] / 100.0
            seg_rhe += contrib
            daily_rhe[:, d] = contrib.sum(1)
            if rec is not None and d in day2win:
                Ls = (1 - phi) * g["m"][None, :] + phi * 0.5
                shs = shape_fn(Ls / L_NORM, P)
                Ds = np.clip(Dm * shs, 0.0, 0.95)
                alloc_s = np.maximum(1.0 - Ds, vlow * (1.0 - 0.5 * Ds))
                Vs = warm * alloc_s * (1.0 - pen)
                for w in day2win[d]:
                    r_ = rec[w]
                    r_["A"] += A[:, :14]
                    r_["As"] += (100.0 * Sday[:, None] * Vs / Qref[:, None])[:, :14]
                    r_["R"] += (100.0 * V / V[:, :1])[:, :14]
                    r_["Rs"] += (100.0 * Vs / V[:, :1])[:, :14]
                    r_["V"] += V[:, :14]
                    r_["Sday"] += Sday; r_["X"] += X; r_["C"] += C; r_["Z"] += Z
                    r_["cnt"] += 1
        # end-of-day state updates
        if s["rest"][d]:
            C = C * (1.0 - P["rho_rest"])
            load = np.zeros(n)
        else:
            gH = np.clip((Hd - P["H_s"]) / (14.0 - P["H_s"]), 0.0, None)
            load = gH * (1.0 - P["lam_L"] * leis_eff)
            C = C + (P["c_max"] * load - C) / P["tau_C"]
            if s["part"][d]:
                C = C * (1.0 - 0.5 * P["rho_rest"])
        Z = Z + (P["m_slow"] * load - Z) / TAU_Z
    out = dict(seg_rhe=seg_rhe, rhe=seg_rhe.sum(1), daily_rhe=daily_rhe,
               nominal=float(s["Hd"].sum()))
    if rec is not None:
        for w, r_ in rec.items():
            c = max(r_["cnt"], 1)
            for k in ("A", "As", "R", "Rs", "V", "Sday", "X", "C", "Z"):
                r_[k] = r_[k] / c
        out["rec"] = rec
    return out


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------

def pct(a, q, axis=0):
    return np.percentile(a, q, axis=axis)


def r5(x):
    return float(5 * np.round(np.asarray(x) / 5.0)) if np.ndim(x) == 0 else [float(v) for v in 5 * np.round(np.asarray(x) / 5.0)]


def first_le(Rbar, thr):
    """Rbar (n,14): first hour (1-based) with R <= thr, 15 if never within 14 h."""
    hit = Rbar <= thr + 1e-9
    hit[:, 0] = False
    idx = np.where(hit.any(1), hit.argmax(1) + 1, 15)
    return idx


def hstr(v):
    v = int(round(v))
    return ">14 (not reached)" if v >= 15 else f"h{v}"


def write_csv(path, rows, header=None):
    if not rows:
        return
    header = header or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


WINDOWS = {
    "wk1-2": [d for d in range(0, 13)],
    "1m": [d for d in list(range(14, 27)) + list(range(28, 41))],
    "3m": [d for d in range(84, 97)],
    "6m": [d for d in range(168, 181)],
    "12m": [d for d in range(350, 363)],
}
TPS = list(WINDOWS.keys())


def main():
    t0 = time.time()
    P = make_sweep()
    PC = make_central()
    n = len(P["form"])
    forms = P["form"]
    # Ackerman-consistency flag: rested decline of demanding work at hour-5 no-break load <= 10 %
    ack = (P["D14"] * shape_fn(np.full((n, 1), 4.5 / L_NORM), P)[:, 0]) <= 0.10
    with open(os.path.join(OUT, "sweep_samples.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["i", "form"] + PNAMES + ["shp", "ackerman_consistent"])
        for i in range(n):
            w.writerow([i, FORMS[forms[i]]] + [f"{P[k][i]:.5f}" for k in PNAMES] + [f"{P['shp'][i]:.4f}", int(ack[i])])
    json.dump(dict(params=[dict(name=a, central=b, lo=c, hi=d, label=e, basis=f) for (a, b, c, d, e, f) in PARAMS],
                   shapes={k: dict(central=v[0], lo=v[1], hi=v[2], meaning=v[3]) for k, v in SHAPE.items()},
                   fixed=dict(W0=W0, TAU_Z=TAU_Z, TAU_AD=TAU_AD, e0=E0, sigma_e=SIGMA_E, L_NORM=L_NORM,
                              P1_SLEEP_TARGET=P1_SLEEP_TARGET, meal_split="pre 30%, lunch 25%, dinner 25%, post 20% of life"),
                   seed=SEED, n_per_form=N_PER_FORM),
              open(os.path.join(OUT, "parameters.json"), "w"), indent=1)

    checks = []
    summary = {"n_samples": int(n), "ackerman_consistent_share": float(ack.mean())}

    # ------------------------------------------------------------------ Q1
    q1_rows, thr_rows, q1_struct, thr_struct = [], [], [], []
    q1_res = {}
    for S in ("S1", "S2", "S3"):
        s = prompt1_schedule(S, 14)
        ok, msg = budget_check(s); checks.append(dict(schedule=s["name"], ok=ok, msg=msg))
        res = simulate(s, P, WINDOWS)
        resc = simulate(s, PC, WINDOWS)
        q1_res[S] = res
        for tp in TPS:
            rc = res["rec"][tp]; cc = resc["rec"][tp]
            R, A, Rs, As = rc["R"], rc["A"], rc["Rs"], rc["As"]
            assert np.allclose(R[:, 0], 100.0), "R(t,1) must be 100"
            assert np.allclose(cc["R"][:, 0], 100.0)
            Rm, Rl, Rh = pct(R, 50), pct(R, 5), pct(R, 95)
            Am = pct(A, 50)
            Rsm = pct(Rs, 50)
            vpk = np.maximum(rc["V"].max(1, keepdims=True), 1e-9)
            rel = rc["V"] / vpk
            e = E0 * (1 - SIGMA_E * (1 - rel))
            kk = rel / (e / E0)
            for h in range(14):
                row = dict(scenario=S, timepoint=tp, hour=h + 1,
                           R_med=Rm[h], R_p5=Rl[h], R_p95=Rh[h], A_med=Am[h], A_p5=pct(A[:, h], 5), A_p95=pct(A[:, h], 95),
                           R_sustained_med=Rsm[h], transient_gap_med=pct(Rs[:, h] - R[:, h], 50),
                           e_med=pct(e[:, h], 50), k_med=pct(kk[:, h], 50))
                for fi, f in enumerate(FORMS):
                    row[f"R_med_{f}"] = pct(R[forms == fi, h], 50)
                    row[f"R_central_{f}"] = cc["R"][fi, h]
                    row[f"A_central_{f}"] = cc["A"][fi, h]
                row["R_med_ackerman"] = pct(R[ack, h], 50)
                q1_rows.append(row)
            drhe = A.sum(1) / 100.0
            q1_struct.append(dict(scenario=S, timepoint=tp, R=r5(Rm), R_low=r5(Rl), R_high=r5(Rh), A=r5(Am),
                                  first_hour_A=r5(pct(A[:, 0], 50)), daily_RHE=round(float(pct(drhe, 50)), 1),
                                  _daily_RHE_band=[round(float(pct(drhe, 5)), 1), round(float(pct(drhe, 95)), 1)],
                                  _first_hour_A_band=[r5(pct(A[:, 0], 5)), r5(pct(A[:, 0], 95))],
                                  _state=dict(X=float(pct(rc["X"], 50)), C=float(pct(rc["C"], 50)), Z=float(pct(rc["Z"], 50)),
                                              Sday=float(pct(rc["Sday"], 50)))))
            # thresholds
            h80 = first_le(R, 80); h50 = first_le(R, 50)
            hs80 = first_le(Rs, 80); hs50 = first_le(Rs, 50)
            idx = np.clip(h80 - 1, 0, 13)
            transient80 = (h80 < 15) & (Rs[np.arange(n), idx] > 80)
            trow = dict(scenario=S, timepoint=tp,
                        h80_p5=pct(h80, 5), h80_med=pct(h80, 50), h80_p95=pct(h80, 95), h80_never=float((h80 == 15).mean()),
                        h50_p5=pct(h50, 5), h50_med=pct(h50, 50), h50_p95=pct(h50, 95), h50_never=float((h50 == 15).mean()),
                        sust80_med=pct(hs80, 50), sust80_p5=pct(hs80, 5), sust80_p95=pct(hs80, 95), sust80_never=float((hs80 == 15).mean()),
                        first80_is_transient=float(transient80[h80 < 15].mean()) if (h80 < 15).any() else 0.0,
                        h80_med_ackerman=pct(h80[ack], 50), h80_never_ackerman=float((h80[ack] == 15).mean()))
            for fi, f in enumerate(FORMS):
                trow[f"h80_med_{f}"] = pct(h80[forms == fi], 50)
                trow[f"h80_never_{f}"] = float((h80[forms == fi] == 15).mean())
                trow[f"h50_never_{f}"] = float((h50[forms == fi] == 15).mean())
                trow[f"h80_central_{f}"] = int(first_le(cc["R"][fi:fi + 1], 80)[0])
            thr_rows.append(trow)
            q1_res[(S, tp, "h80")] = h80
            q1_res[(S, tp, "hs80")] = hs80
            q1_res[(S, tp, "h50")] = h50
            q1_res[(S, tp, "R")] = R
            q1_res[(S, tp, "Rs")] = Rs
    write_csv(os.path.join(OUT, "q1_hourly.csv"), q1_rows)
    write_csv(os.path.join(OUT, "q1_thresholds.csv"), thr_rows)
    print(f"Q1 done {time.time()-t0:.0f}s")

    # ------------------------------------------------------------------ Q2
    q2_rows, inc_rows = [], []
    q2 = {}
    for S in ("S1", "S2", "S3"):
        for H in range(8, 15):
            s = prompt1_schedule(S, H)
            ok, msg = budget_check(s); checks.append(dict(schedule=s["name"], ok=ok, msg=msg))
            res = simulate(s, P)
            q2[("prompt1", S, H)] = (s, res)
    for bn in ("tight", "base", "generous"):
        for H in (8, 10, 12, 14):
            for variant in ("auto", "drop_exmed"):
                s = prompt2_schedule(bn, H, variant=variant)
                if variant == "drop_exmed" and s["feasible"]:
                    continue
                ok, msg = budget_check(s); checks.append(dict(schedule=s["name"], ok=ok, msg=msg))
                res = simulate(s, P)
                q2[(f"prompt2_{bn}", variant, H)] = (s, res)
    for key, (s, res) in q2.items():
        r = res["rhe"]
        q2_rows.append(dict(framework=key[0], scen_or_variant=key[1], H=key[2], variant=s["variant"],
                            feasible=s.get("feasible", True), tib=s["tib"], actual_sleep=s["tib"] * s["eff"],
                            leisure_study_day=s["leis_study"], life=s["life"], nominal_hours=res["nominal"],
                            rhe_med=pct(r, 50), rhe_p5=pct(r, 5), rhe_p95=pct(r, 95),
                            rhe_per_nominal_med=pct(r / res["nominal"], 50),
                            **{f"rhe_med_{f}": pct(r[forms == fi], 50) for fi, f in enumerate(FORMS)}))
    write_csv(os.path.join(OUT, "q2_schedules.csv"), q2_rows)

    def increment(k1, k2, H1, H2, label):
        s1, r1 = q2[k1]; s2, r2 = q2[k2]
        block = r2["seg_rhe"][:, H1:H2].sum(1)
        spill = r2["seg_rhe"][:, :H1].sum(1) - r1["rhe"]
        net = r2["rhe"] - r1["rhe"]
        assert np.allclose(block + spill, net)
        added_nom = r2["nominal"] - r1["nominal"]
        row = dict(framework=label, step=f"{H1}->{H2}", variant_H2=s2["variant"],
                   block_med=pct(block, 50), block_p5=pct(block, 5), block_p95=pct(block, 95),
                   spill_med=pct(spill, 50), spill_p5=pct(spill, 5), spill_p95=pct(spill, 95),
                   net_med=pct(net, 50), net_p5=pct(net, 5), net_p95=pct(net, 95), net_neg_share=float((net < 0).mean()),
                   added_nominal=added_nom, net_per_added_hour_med=pct(net / added_nom, 50),
                   block_per_added_hour_med=pct(block / added_nom, 50),
                   net_neg_share_ackerman=float((net[ack] < 0).mean()))
        for fi, f in enumerate(FORMS):
            row[f"net_med_{f}"] = pct(net[forms == fi], 50)
            row[f"net_neg_share_{f}"] = float((net[forms == fi] < 0).mean())
        return row, net, block, spill

    inc_nets = {}
    for S in ("S1", "S2", "S3"):
        for H1, H2 in ((8, 10), (10, 12), (12, 14)):
            row, net, b, sp = increment(("prompt1", S, H1), ("prompt1", S, H2), H1, H2, f"prompt1_{S}")
            inc_rows.append(row); inc_nets[(f"prompt1_{S}", H1, H2)] = (net, b, sp)
    for bn in ("tight", "base", "generous"):
        for H1, H2 in ((8, 10), (10, 12), (12, 14)):
            row, net, b, sp = increment((f"prompt2_{bn}", "auto", H1), (f"prompt2_{bn}", "auto", H2), H1, H2, f"prompt2_{bn}")
            inc_rows.append(row); inc_nets[(f"prompt2_{bn}", H1, H2)] = (net, b, sp)
    write_csv(os.path.join(OUT, "q2_increments.csv"), inc_rows)
    # prompt-1 lifestyle optimum (no fixed life conditions)
    p1opt = {}
    for S in ("S1", "S2", "S3"):
        M = np.stack([q2[("prompt1", S, H)][1]["rhe"] for H in range(8, 15)], 1)
        p1opt[S] = np.arange(8, 15)[M.argmax(1)]
    print(f"Q2 done {time.time()-t0:.0f}s")

    # ------------------------------------------------------------------ Q3
    plan_rows = []
    plans = {}
    for bn in ("base", "tight", "generous"):
        hmax = max_study_hours(BUD[bn])
        Hgrid = [h for h in np.arange(7.0, 12.51, 0.5) if h <= hmax + 1e-9]
        for H in Hgrid:
            for r in (1, 2, 3, 4):
                for pp in (0, 1, 2):
                    s = prompt2_schedule(bn, float(H), r, pp)
                    assert s["feasible"]
                    ok, msg = budget_check(s); checks.append(dict(schedule=s["name"], ok=ok, msg=msg))
                    res = simulate(s, P)
                    plans[(bn, float(H), r, pp)] = dict(rhe=res["rhe"], nominal=res["nominal"], leis=s["leis_study"])
        print(f"Q3 {bn} done {time.time()-t0:.0f}s")

    def optimise(bn, floor_min, min_rest):
        keys = [k for k in plans if k[0] == bn and plans[k]["leis"] * 60 >= floor_min - 1e-6 and k[2] >= min_rest]
        M = np.stack([plans[k]["rhe"] for k in keys], 1)
        med = np.median(M, 0)
        best = int(med.argmax())
        band = [keys[i] for i in range(len(keys)) if med[i] >= 0.98 * med[best]]
        best_per = M.argmax(1)
        within = (M >= 0.98 * M.max(1, keepdims=True)).mean(0)
        optH = np.array([keys[i][1] for i in best_per])
        optR = np.array([keys[i][2] for i in best_per])
        optP = np.array([keys[i][3] for i in best_per])
        hmax_allowed = max(k[1] for k in keys)
        return dict(keys=keys, med=med, best=keys[best], band=band, within=within, optH=optH, optR=optR, optP=optP,
                    M=M, hmax=hmax_allowed)

    opt = {}
    for bn in ("base", "tight", "generous"):
        opt[(bn, "A")] = optimise(bn, 0, 1)
        for fl in (60, 90, 120):
            opt[(bn, f"B{fl}")] = optimise(bn, fl, 2)
    opt_rows = []
    for (bn, sc), o in opt.items():
        for i, k in enumerate(o["keys"]):
            opt_rows.append(dict(budget=bn, scenario=sc, H=k[1], rest=k[2], partial=k[3], leisure_min=plans[k]["leis"] * 60,
                                 rhe_med=o["med"][i], rhe_p5=pct(o["M"][:, i], 5), rhe_p95=pct(o["M"][:, i], 95),
                                 share_within2pct_of_sample_best=o["within"][i], nominal=plans[k]["nominal"],
                                 in_band=k in o["band"], is_best=k == o["best"]))
    write_csv(os.path.join(OUT, "q3_plans.csv"), opt_rows)
    optsum = []
    for (bn, sc), o in opt.items():
        row = dict(budget=bn, scenario=sc, best_H=o["best"][1], best_rest=o["best"][2], best_partial=o["best"][3],
                   best_rhe_med=float(o["med"].max()), hmax_allowed=o["hmax"],
                   optH_p5=pct(o["optH"], 5), optH_med=pct(o["optH"], 50), optH_p95=pct(o["optH"], 95),
                   optH_at_max_share=float((o["optH"] >= o["hmax"] - 1e-9).mean()),
                   optR_share1=float((o["optR"] == 1).mean()), optR_share2=float((o["optR"] == 2).mean()),
                   optR_share3plus=float((o["optR"] >= 3).mean()), optP_share0=float((o["optP"] == 0).mean()),
                   band=";".join(f"{k[1]}h/r{k[2]}/p{k[3]}" for k in o["band"]),
                   optH_med_ackerman=pct(o["optH"][ack], 50))
        for fi, f in enumerate(FORMS):
            row[f"optH_med_{f}"] = pct(o["optH"][forms == fi], 50)
            row[f"optH_at_max_{f}"] = float((o["optH"][forms == fi] >= o["hmax"] - 1e-9).mean())
        optsum.append(row)
    write_csv(os.path.join(OUT, "q3_optimum_summary.csv"), optsum)
    # break-even: what uniform efficiency gain would leisure / extra rest have to deliver?
    be_rows = []
    for bn in ("base", "tight", "generous"):
        o = opt[(bn, "A")]
        Hb = o["best"][1]
        r1 = plans[(bn, Hb, 1, 0)]["rhe"]
        for dh in (0.5, 1.0, 2.0):
            k = (bn, Hb - dh, 1, 0)
            if k in plans:
                ratio = r1 / plans[k]["rhe"] - 1
                be_rows.append(dict(budget=bn, comparison=f"{Hb}h vs {Hb-dh}h (1 rest/14)",
                                    extra_leisure_h=dh, gain_needed_med=pct(ratio, 50), gain_needed_p5=pct(ratio, 5),
                                    gain_needed_p95=pct(ratio, 95), share_shorter_better=float((ratio < 0).mean())))
        for rr in (2, 3, 4):
            ratio = r1 / plans[(bn, Hb, rr, 0)]["rhe"] - 1
            be_rows.append(dict(budget=bn, comparison=f"{Hb}h: 1 vs {rr} rest days/14", extra_leisure_h=0,
                                gain_needed_med=pct(ratio, 50), gain_needed_p5=pct(ratio, 5), gain_needed_p95=pct(ratio, 95),
                                share_shorter_better=float((ratio < 0).mean())))
        ratio = r1 / plans[(bn, Hb, 1, 1)]["rhe"] - 1
        be_rows.append(dict(budget=bn, comparison=f"{Hb}h: no partial vs 1 half-day/14", extra_leisure_h=0,
                            gain_needed_med=pct(ratio, 50), gain_needed_p5=pct(ratio, 5), gain_needed_p95=pct(ratio, 95),
                            share_shorter_better=float((ratio < 0).mean())))
    # cost of the scenario-B constraints relative to scenario A (same sample)
    for bn in ("base", "tight", "generous"):
        rA = plans[(bn,) + opt[(bn, "A")]["best"][1:]]["rhe"]
        for fl in (60, 90, 120):
            kB = opt[(bn, f"B{fl}")]["best"]
            ratio = 1 - plans[kB]["rhe"] / rA
            be_rows.append(dict(budget=bn, comparison=f"cost of B{fl} best ({kB[1]}h/r{kB[2]}) vs A best", extra_leisure_h=fl / 60,
                                gain_needed_med=pct(ratio, 50), gain_needed_p5=pct(ratio, 5), gain_needed_p95=pct(ratio, 95),
                                share_shorter_better=float((ratio < 0).mean())))
    write_csv(os.path.join(OUT, "q3_breakeven.csv"), be_rows)
    # conditional (infeasible) extension beyond the prompt-2 base maximum: which H would maximise RHE if
    # the 8 h sleep condition (sleep_cut) or exercise+meditation (drop_exmed) were broken?
    ext_rows = []
    for variant in ("sleep_cut", "drop_exmed"):
        Hs = [11.0 + 0.5 * i for i in range(7)]
        M = np.stack([simulate(prompt2_schedule("base", h, 1, 0, variant=variant), P)["rhe"] for h in Hs], 1)
        am = np.array(Hs)[M.argmax(1)]
        med = np.median(M, 0)
        for i, h in enumerate(Hs):
            s_ = prompt2_schedule("base", h, 1, 0, variant=variant)
            ext_rows.append(dict(variant=s_["variant"], H=h, actual_sleep=s_["tib"] * s_["eff"], rhe_med=med[i],
                                 rhe_p5=pct(M[:, i], 5), rhe_p95=pct(M[:, i], 95),
                                 share_argmax=float((am == h).mean())))
    write_csv(os.path.join(OUT, "q3_conditional_extension.csv"), ext_rows)
    print(f"Q3 done {time.time()-t0:.0f}s")

    # ------------------------------------------------------------------ sensitivity (Spearman over sweep)
    outcomes = {
        "h80_S2_3m": q1_res[("S2", "3m", "h80")].astype(float),
        "h80_S3_3m": q1_res[("S3", "3m", "h80")].astype(float),
        "sust80_S2_3m": q1_res[("S2", "3m", "hs80")].astype(float),
        "net12to14_prompt1_S2": inc_nets[("prompt1_S2", 12, 14)][0],
        "net12to14_prompt2_base_sleepcut": inc_nets[("prompt2_base", 12, 14)][0],
        "net10to12_prompt2_base_sleepcut": inc_nets[("prompt2_base", 10, 12)][0],
        "optH_A_base": opt[("base", "A")]["optH"],
        "optR_A_base": opt[("base", "A")]["optR"].astype(float),
        "optH_B90_base": opt[("base", "B90")]["optH"],
        "optH_prompt1_S2_grid8to14": p1opt["S2"].astype(float),
    }
    sens_rows = []
    for oname, y in outcomes.items():
        for pn in PNAMES + ["shp"]:
            xs = P[pn]
            rho = spearmanr(xs, y).correlation if np.std(y) > 0 else float("nan")
            q = np.quantile(xs, [0.2, 0.8])
            lo_m = float(np.mean(y[xs <= q[0]])); hi_m = float(np.mean(y[xs >= q[1]]))
            sens_rows.append(dict(outcome=oname, param=pn, spearman=rho, mean_bottom_quintile=lo_m, mean_top_quintile=hi_m))
        for fi, f in enumerate(FORMS):
            sens_rows.append(dict(outcome=oname, param=f"form={f}", spearman=float("nan"),
                                  mean_bottom_quintile=float(np.mean(y[forms == fi])), mean_top_quintile=float(np.median(y[forms == fi]))))
    write_csv(os.path.join(OUT, "sensitivity_spearman.csv"), sens_rows)
    # sign-flip conditional shares for the 12->14 net under prompt-1 S2
    net = outcomes["net12to14_prompt1_S2"]
    flip_rows = []
    for pn in PNAMES:
        xs = P[pn]; q = np.quantile(xs, [0.2, 0.8])
        flip_rows.append(dict(param=pn, neg_share_bottom=float((net[xs <= q[0]] < 0).mean()),
                              neg_share_top=float((net[xs >= q[1]] < 0).mean())))
    write_csv(os.path.join(OUT, "sensitivity_net12to14_signflip.csv"), flip_rows)

    # ------------------------------------------------------------------ one-at-a-time structural checks (central params)
    oat = []
    for tgt in (8.2, 8.3, 8.5):
        r12 = simulate(prompt1_schedule("S2", 12, target=tgt), PC)["rhe"]
        r14 = simulate(prompt1_schedule("S2", 14, target=tgt), PC)["rhe"]
        oat.append(dict(check=f"prompt1 S2 sleep target {tgt}", **{f"net12to14_{f}": float(r14[i] - r12[i]) for i, f in enumerate(FORMS)}))
    json.dump(oat, open(os.path.join(OUT, "oat_checks.json"), "w"), indent=1)

    # ------------------------------------------------------------------ checks + summary
    write_csv(os.path.join(OUT, "budget_checks.csv"), checks)
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
    summary.update(dict(q1=q1_struct, n_budget_checks=len(checks), all_budgets_ok=all(c["ok"] for c in checks),
                        p1opt={S: dict(med=float(np.median(v)), p5=float(pct(v, 5)), p95=float(pct(v, 95)),
                                       share14=float((v == 14).mean()),
                                       by_form={f: float(np.median(v[forms == fi])) for fi, f in enumerate(FORMS)})
                               for S, v in p1opt.items()},
                        runtime_s=time.time() - t0))
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
    print(f"all done {time.time()-t0:.0f}s; budget checks ok: {summary['all_budgets_ok']} ({len(checks)})")


if __name__ == "__main__":
    main()
