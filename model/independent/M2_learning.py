#!/usr/bin/env python3
"""M2 -- learning-science-first model of hourly study yield over a 365-day CSAT repeat year.

Core idea
---------
The value of a nominal study hour is built from WHAT the hour is spent on.  Four task types
(NEW = new learning / lectures, PROB = problem solving, RET = retrieval / review,
MOCK = timed mock tests) each have

    yield rate q_k = v_k * e_k * S_k * sat_k * enc_k * mq_k                      (per nominal hour)

  v_k    value of a fully engaged, rested hour of task k (relative units, assumption)
  e_k    engaged fraction of the nominal hour = e0_k * (1 - mw_k) * warm-up * E_F
           mw_k  = mind wandering, rises with time in the current block (resets at meal breaks)
           E_F   = engagement loss from multi-week strain F (bounded, recovers with rest/leisure)
  S_k    state multiplier = (M_sleep(D) * W(tau) * Dip(tau) * irregularity)^sens_k
           M_sleep = 1 - a_sleep*(1-exp(-D/D_scale)) : start-of-day sleep-debt state
           W       = time-awake factor, flat until tau_crit = tau_crit0 - kD*D, then linear decline
           Dip     = transient post-lunch dip (Gaussian in time since wake)
  sat_k  content-specific within-day saturation 1/(1 + sat_rate * m_k / n_streams_k),
           m_k = engaged hours of type k already done today (resets overnight)
  enc_k  daily encoding-capacity decline 1 - enc_w_k*enc_eps*(1-exp(-N_enc/enc_scale))  (Mander 2011, weak)
  mq_k   method quality: late-day drift to low-effort methods
           delta(L) = drift_max*(1-alpha)/(1+exp(-(L-drift_L50)/drift_s)),
           mq_k = 1 - delta*susc_k*(1-rho_k); L = cumulative effort load today (Blain 2016 inference)

The day's learning is then multiplied by Cons(s) = 1 - c_cons*((need-s)/need)^gamma_cons, where s is the
actual sleep of the FOLLOWING night (sleep-dependent consolidation; the 7-day test sees it).

Across days (all bounded, none linear over 365 days):
  sleep debt  D_{n+1} = max(0, (1-lam_debt)*D_n + need - s_n)      (converges to a stable equilibrium)
               rest-day sleep-in s += min(ext_cap, ext_frac*D)      (partial repayment, not a reset)
  strain      F_{n+1} = F_n*(1-mu_n) + eta*max(0, Load_n - L_sus)
               mu_n = mu0 + mu_leis_max*(1-exp(-leisure_n/leis_scale)) + mu_exmed*exmed_h
               (a full rest day has ~11 h leisure -> mu ~0.35: large but partial recovery)
  adaptation  alpha(t) = adapt_max*(1-exp(-t/adapt_tau))  (cognitive endurance, small)

Outputs
  Q(t,h)  = mean yield rate in nominal hour h of day t (incl. consolidation)
  R(t,h)  = 100*Q(t,h)/Q(t,1)
  A(t,h)  = 100*Q(t,h)/Q_ref(t),   Q_ref = hour-1 yield of the rested twin (D=0, F=0, no irregularity,
            full consolidation sleep, same adaptation, same time of day, FIXED daily task mix)
  RHE     = sum over study time of A/100
Knowledge-level (learning-curve) effects are common to all schedules and excluded (they cancel in R and A).
"""
from __future__ import annotations

import copy
import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, "/home/user/effective-tribble/model")
import time_budget as tb  # noqa: E402  (read-only use of the repo's budget numbers)

TYPES = ("NEW", "PROB", "RET", "MOCK")
DT = 0.25                 # slot length (h)
SPH = 4                   # slots per hour
NDAYS = 365
ONE_REST = "SSSSSSSSSSSSSR"   # 13 study + 1 full rest

# --------------------------------------------------------------------------------------------
# Parameters: name -> (value, low, high, label, basis)
# --------------------------------------------------------------------------------------------
PARAMS = {
    # ---- sleep / circadian ----
    "need": (8.3, 8.0, 8.6, "literature_constrained",
             "Digest s1: Van Dongen 2003 implied need 8.16 h; Kitamura 2016 8.4 h (range 7.3-9.3)"),
    "lam_debt": (0.20, 0.10, 0.35, "indirect_estimate",
                 "Debt leak -> stable equilibrium (McCauley 2009; Belenky 2003 7 h stabilised after days 1-4); "
                 "Van Dongen 6 h still worsening at 14 d bounds it below; Kitamura 1 h debt ~4 d to repay"),
    "a_sleep": (0.25, 0.12, 0.40, "indirect_estimate",
                "Max learning loss from chronic debt. Calibrated so a 5 h-TIB week (debt ~15 h) costs ~13% "
                "(~g -0.45 at CV 0.3), between Lowe 2017 LTM g=-0.19 and overall -0.38 / Newbury 2021 "
                "pre-learning deprivation g=0.62; Cousins 2018 encoding impaired after partial restriction"),
    "D_scale": (20.0, 12.0, 30.0, "assumption", "Debt (h) at which 63% of max loss is reached"),
    "ext_cap": (2.0, 1.0, 3.0, "assumption",
                "Max rest-day sleep-in (h); Lo 2016/2017 and Kitamura 2016: catch-up is partial"),
    "ext_frac": (0.5, 0.3, 0.8, "assumption", "Rest-day sleep-in = ext_frac*debt (capped)"),
    "D0": (1.0, 0.0, 3.0, "assumption", "Sleep debt (h) on day 1"),
    "c_cons": (0.15, 0.05, 0.25, "indirect_estimate",
               "Loss of 7-day retention with NO sleep after learning; Berres & Erdfelder 2021 g=0.44, "
               "Newbury 2021 after-learning g=0.28 (pub. bias); g->% via CV~0.3"),
    "gamma_cons": (1.0, 0.7, 2.0, "assumption",
                   "Shape of consolidation loss vs sleep deficit (>1: SWS preserved under mild restriction)"),
    "tau_crit0": (16.0, 15.0, 17.0, "literature_constrained",
                  "Alertness ~stable over ~16 h wake in entrained sleepers (Dijk & Czeisler 1994; Wright 2002); "
                  "Van Dongen critical wake 15.84 h"),
    "kD_tcrit": (0.30, 0.10, 0.50, "assumption", "h of earlier late-day decline per h of sleep debt"),
    "w_slope": (0.06, 0.03, 0.10, "assumption", "Yield loss per h awake beyond tau_crit"),
    "p_dip": (0.05, 0.0, 0.10, "indirect_estimate", "Post-lunch dip amplitude; variable (Monk 2005)"),
    "tau_dip": (7.5, 7.0, 8.0, "assumption", "Dip centre, h after waking (~14:00 for 06:30 wake)"),
    "irr_pen": (0.03, 0.0, 0.06, "assumption", "S3 only: circadian-misalignment penalty on state"),
    "irr_sd": (0.6, 0.3, 1.0, "assumption", "S3 only: night-to-night SD of actual sleep (h)"),
    "irr_tshift": (0.5, 0.0, 1.0, "assumption", "S3 only: earlier tau_crit (h)"),
    # ---- task-type engagement ----
    "mw0_scale": (1.0, 0.5, 1.75, "indirect_estimate",
                  "Baseline mind wandering NEW 0.20/PROB 0.12/RET 0.08/MOCK 0.05; Szpunar 2013 41% lab lecture, "
                  "19% with tests; Wammes 2016 low in motivated real classes"),
    "mw_slope_scale": (1.0, 0.5, 2.0, "indirect_estimate",
                       "Within-block rise NEW 0.05/PROB 0.025/RET 0.015/MOCK 0 per h; Risko 2012 rise; "
                       "Hopstaken 2015 ~2 h decline reversible; Sievertsen 2016 -0.9%SD/h, +1.7%SD per break"),
    "sens_scale": (1.0, 0.7, 1.4, "indirect_estimate",
                   "Task sensitivity exponents to state NEW 1.3/PROB 1.2/RET 0.8/MOCK 1.0; Lowe 2017 exec "
                   "g=-0.32 vs LTM -0.19; Newbury 2021 encoding"),
    "warm_day": (0.15, 0.0, 0.30, "assumption", "Engagement loss in first 15-min slot of day (settling, inertia)"),
    "warm_meal": (0.08, 0.0, 0.20, "assumption", "Engagement loss in first slot after a meal break"),
    # ---- content saturation / encoding ----
    "sat_rate": (0.35, 0.15, 0.70, "indirect_estimate",
                 "Per-stream saturation per engaged h; Rohrer & Taylor 2006 (9 vs 3 problems: no gain), "
                 "Rohrer 2005 overlearning short-lived"),
    "stream_scale": (1.0, 0.5, 2.0, "assumption",
                     "Number of distinct content streams per day NEW 4/PROB 5/RET 6 (x scale)"),
    "enc_eps": (0.12, 0.0, 0.25, "indirect_estimate",
                "Daily encoding-capacity decline (Mander 2011, n=44, magnitude not seen; Guttesen 2025 nulls) "
                "-> kept small"),
    "enc_scale": (4.0, 2.0, 6.0, "assumption", "Encoding load (engaged h) for 63% of enc_eps"),
    # ---- late-day low-effort drift ----
    "drift_max": (0.35, 0.15, 0.55, "assumption",
                  "Max share of work drifting to low-effort methods (Blain 2016 / Wiehler 2022 inference; untested "
                  "for studying)"),
    "drift_L50": (6.5, 5.0, 8.0, "indirect_estimate",
                  "Effort load (demand-weighted engaged h) at half-max drift; Blain 2016 shift after ~6-6.25 h"),
    "drift_s": (1.2, 0.6, 2.0, "assumption", "Logistic width of drift (h)"),
    "rho_scale": (1.0, 0.8, 1.2, "literature_constrained",
                  "Low-effort yield ratio NEW 0.60/PROB 0.55/RET 0.66/MOCK 0.70; RET from Roediger & Karpicke "
                  "2006 40% vs 61% at 1 wk; Rowland 2014 g=0.5 (others assumption)"),
    "beta_break": (0.15, 0.0, 0.40, "assumption",
                   "Fraction/h of effort load recovered during long breaks (Albulescu 2022; Sievertsen 2016)"),
    # ---- strain (multi-week) ----
    "L_sus": (5.5, 4.5, 6.5, "indirect_estimate",
              "Sustainable daily effort load (~8-8.5 nominal h); Pencavel 2015 proportional output below ~49 h/wk"),
    "eta": (0.12, 0.06, 0.24, "assumption", "Strain inflow per unit load above L_sus"),
    "mu0": (0.05, 0.03, 0.10, "indirect_estimate",
            "Baseline daily strain decay; de Bloom 2009 / Speth 2024 recovery effects fade over 1-4 weeks"),
    "mu_leis_max": (0.30, 0.15, 0.45, "assumption",
                    "Max extra strain recovery from leisure (saturating); Binnewies 2010 weekend recovery"),
    "leis_scale": (3.0, 1.5, 6.0, "assumption", "Leisure h for 63% of mu_leis_max"),
    "mu_exmed": (0.02, 0.0, 0.05, "assumption", "Extra strain recovery per h exercise+meditation"),
    "f_max": (0.25, 0.15, 0.40, "indirect_estimate",
              "Max engagement loss from strain; burnout-achievement r=-0.24 (Madigan & Curran 2021, correlational)"),
    "F_scale": (4.0, 2.5, 6.0, "assumption", "Strain units for 63% of f_max"),
    # ---- adaptation ----
    "adapt_max": (0.15, 0.0, 0.30, "indirect_estimate",
                  "Cognitive endurance trainable: 22% less within-test decline (Brown et al. 2025); applied to "
                  "within-block mind-wandering slopes and drift"),
    "adapt_tau": (30.0, 15.0, 60.0, "assumption", "Adaptation time constant (days)"),
    # ---- partial rest day ----
    "partial_frac": (0.5, 0.5, 0.5, "assumption", "Partial rest day = this fraction of H studied (morning)"),
}

TASK = {
    #        v     e0    mw0   slope  sens  demand n_str  enc_w  rho   susc   mix
    "NEW":  (1.00, 0.88, 0.20, 0.050, 1.3,  0.8,   4.0,  1.0,   0.60, 1.0,  0.25),
    "PROB": (1.10, 0.88, 0.12, 0.025, 1.2,  1.0,   5.0,  0.5,   0.55, 1.0,  0.40),
    "RET":  (0.95, 0.90, 0.08, 0.015, 0.8,  0.6,   6.0,  0.2,   0.66, 0.6,  0.25),
    "MOCK": (0.85, 0.95, 0.05, 0.000, 1.0,  1.0,   0.0,  0.3,   0.70, 0.3,  0.10),
}
TASK_BASIS = {
    "v": "assumption: relative value per engaged rested hour on a 7-day retention+application test "
         "(PROB highest because the test includes application; RET slightly below 1 because it prevents "
         "forgetting of old material; MOCK lower because much time is diagnostic)",
    "e0": "assumption: on-task share of the nominal hour excluding short breaks/lapses",
    "demand": "assumption: cognitive-control demand weight for the effort load L",
    "n_streams": "assumption: distinct content streams a student can rotate through per day (MOCK: none)",
    "mix": "assumption: daily task mix of a repeat student (NEW 25%, PROB 40%, RET 25%, MOCK 10%)",
}


def base_params() -> dict:
    return {k: v[0] for k, v in PARAMS.items()}


def task_arrays(P: dict, mix=None):
    """Return per-type parameter tuples after applying scale parameters."""
    out = []
    for k in TYPES:
        v, e0, mw0, slope, sens, dem, nst, encw, rho, susc, m = TASK[k]
        out.append(dict(
            v=v, e0=e0, mw0=min(0.8, mw0 * P["mw0_scale"]), slope=slope * P["mw_slope_scale"],
            sens=sens * P["sens_scale"], demand=dem, nst=nst * P["stream_scale"], encw=encw,
            rho=min(1.0, rho * P["rho_scale"]), susc=susc, mix=(mix[k] if mix else m)))
    return out


# --------------------------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------------------------
def prompt1_schedule(H, scen, P, alloc="fixed"):
    """Prompt-1 framework.  scen in S1/S2/S3 defines life hours and sleep efficiency (digest s1).
    Freed time (24-H-life) goes to TIB up to need/eff, remainder to leisure."""
    life = {"S1": 1.75, "S2": 2.5, "S3": 3.0}[scen]
    eff = {"S1": 7.6 / 8.25, "S2": 7.0 / 7.5, "S3": 6.3 / 7.0}[scen]
    avail = 24.0 - H - life
    tib = min(avail, P["need"] / eff)
    leisure = avail - tib
    return dict(
        name=f"prompt1_{scen}_H{H}", H=H, pattern=ONE_REST, life=life,
        morning=0.2 * life, lunch=0.3 * life, dinner=0.3 * life, evening=0.2 * life,
        tib=tib, eff=eff, sleep=tib * eff, leisure=leisure, exmed=0.0,
        irregular=(scen == "S3"), alloc=alloc, feasible=True, broken="")


def budget_parts(b: "tb.LifeBudget", drop_exmed=False):
    """Place prompt-2 life items in the day (h).  Exercise sits in the dinner break."""
    ex = 0.0 if drop_exmed else b.exercise_per_day()
    med = 0.0 if drop_exmed else b.meditation
    morning = 0.45 * b.hygiene + 0.25 * b.meals + 0.5 * med + 0.5 * b.commute + b.transitions / 3
    lunch = 0.375 * b.meals + b.transitions / 3
    dinner = 0.375 * b.meals + ex + b.transitions / 3
    evening = 0.55 * b.hygiene + 0.5 * med + b.chores + 0.5 * b.commute
    return dict(morning=morning / 60, lunch=lunch / 60, dinner=dinner / 60, evening=evening / 60,
                exmed=(ex + med) / 60)


def prompt2_schedule(H, budget_idx, P, leisure_floor=0.0, pattern=ONE_REST, variant="sleep_cut",
                     alloc="fixed", sleep_actual=8.0):
    """Prompt-2 framework: 8.0 h actual sleep, fixed life (tight/base/generous).  If H does not fit,
    a conditional variant is built: 'sleep_cut' (sleep absorbs the deficit) or 'drop_exmed'
    (exercise+meditation dropped first, then sleep cut)."""
    b = tb.BUDGETS[budget_idx]
    parts = budget_parts(b)
    life = parts["morning"] + parts["lunch"] + parts["dinner"] + parts["evening"]
    tib = sleep_actual / b.sleep_efficiency
    slack = 24.0 - H - life - tib - leisure_floor / 60.0
    feasible = slack >= -1e-9
    broken = ""
    if feasible:
        leisure = leisure_floor / 60.0 + slack
    else:
        leisure = leisure_floor / 60.0
        if variant == "drop_exmed":
            parts = budget_parts(b, drop_exmed=True)
            life = parts["morning"] + parts["lunch"] + parts["dinner"] + parts["evening"]
            broken = "exercise+meditation dropped"
            slack = 24.0 - H - life - tib - leisure
            if slack < 0:
                tib += slack
                broken += f"; sleep cut to {tib * b.sleep_efficiency:.2f} h actual"
            else:
                leisure += slack
        else:
            tib += slack
            broken = f"sleep cut to {tib * b.sleep_efficiency:.2f} h actual (8.0 h condition broken)"
    return dict(
        name=f"prompt2_{['tight', 'base', 'generous'][budget_idx]}_H{H}", H=H, pattern=pattern, life=life,
        morning=parts["morning"], lunch=parts["lunch"], dinner=parts["dinner"], evening=parts["evening"],
        tib=tib, eff=b.sleep_efficiency, sleep=tib * b.sleep_efficiency, leisure=leisure,
        exmed=parts["exmed"], irregular=False, alloc=alloc, feasible=feasible, broken=broken)


def check_budget(s):
    tot = s["life"] + s["H"] + s["leisure"] + s["tib"]
    return abs(tot - 24.0) < 1e-6, tot


# --------------------------------------------------------------------------------------------
# Day layout and allocation sequences
# --------------------------------------------------------------------------------------------
def layout(Hday, s):
    """Blocks: B1 <= 4 h (morning), lunch, B2 <= 5 h, dinner(+exercise), B3 = rest.  Returns per-slot
    (tau, time-in-block, first_of_day, first_after_meal) and the break durations before each slot."""
    n = int(round(Hday / DT))
    b1 = min(n, 4 * SPH)
    b2 = min(n - b1, 5 * SPH)
    b3 = n - b1 - b2
    slots = []
    tau = s["morning"]
    for bi, (nb, brk) in enumerate(((b1, 0.0), (b2, s["lunch"]), (b3, s["dinner"]))):
        if nb == 0:
            continue
        tau += brk
        for j in range(nb):
            slots.append((tau + (j + 0.5) * DT, j * DT, bi == 0 and j == 0, bi > 0 and j == 0,
                          brk if j == 0 else 0.0))
        tau += nb * DT
    return slots


def fixed_sequence(n, mix=None):
    m = [TASK[k][10] if mix is None else mix[k] for k in TYPES]
    return np.tile(np.array(m), (n, 1))


def counts_for(n, mix=None):
    m = np.array([TASK[k][10] if mix is None else mix[k] for k in TYPES])
    c = np.floor(m * n).astype(int)
    rem = n - c.sum()
    order = np.argsort(-(m * n - c))
    for i in range(rem):
        c[order[i]] += 1
    return c


def heuristic_sequence(n, mix=None):
    """'Hard tasks early, retrieval/review later': MOCK first (CSAT-like morning), NEW/PROB interleaved
    by subject, RET at the end."""
    c = counts_for(n, mix)
    seq = [3] * c[3]
    nn, pp = c[0], c[1]
    tot = nn + pp
    acc = 0.0
    for i in range(tot):
        acc += nn / max(tot, 1)
        if acc >= 1 - 1e-9 and nn > 0:
            seq.append(0)
            acc -= 1
            nn -= 1
        elif pp > 0:
            seq.append(1)
            pp -= 1
        else:
            seq.append(0)
            nn -= 1
    seq += [2] * c[2]
    out = np.zeros((n, 4))
    out[np.arange(n), seq] = 1.0
    return out


# --------------------------------------------------------------------------------------------
# Day simulation
# --------------------------------------------------------------------------------------------
def simulate_day(Hday, s, P, tasks, D, F, alpha, irr, seq, twin=False, transients=True, record=False):
    """Returns per-slot yield rates (before consolidation), total effort load, per-slot engaged
    fraction, and optional components."""
    slots = layout(Hday, s)
    n = len(slots)
    Ms = 1.0 - P["a_sleep"] * (1.0 - math.exp(-D / P["D_scale"]))
    EF = 1.0 - P["f_max"] * (1.0 - math.exp(-F / P["F_scale"]))
    tcrit = P["tau_crit0"] - P["kD_tcrit"] * D - (P["irr_tshift"] if irr else 0.0)
    irrf = (1.0 - P["irr_pen"]) if irr else 1.0
    m = [0.0] * 4
    Nenc = 0.0
    L = 0.0
    Ltot = 0.0
    q = np.zeros(n)
    eng = np.zeros(n)
    comp = [] if record else None
    for i, (tau, btime, first_day, first_meal, brk) in enumerate(slots):
        if brk > 0:
            L *= math.exp(-P["beta_break"] * brk)
        W = 1.0 if tau <= tcrit else max(0.3, 1.0 - P["w_slope"] * (tau - tcrit))
        dip = 1.0 - P["p_dip"] * math.exp(-0.5 * ((tau - P["tau_dip"]) / 0.8) ** 2) if transients else 1.0
        base_state = Ms * W * dip * irrf
        warm = 1.0
        if transients:
            if first_day:
                warm -= P["warm_day"]
            elif first_meal:
                warm -= P["warm_meal"]
        drift = P["drift_max"] * (1.0 - alpha) / (1.0 + math.exp(-(L - P["drift_L50"]) / P["drift_s"]))
        encf = 1.0 - math.exp(-Nenc / P["enc_scale"])
        qi = 0.0
        ei = 0.0
        dL = 0.0
        dN = 0.0
        cs = [0.0] * 6
        for k in range(4):
            sh = seq[i, k]
            if sh <= 0.0:
                continue
            t = tasks[k]
            mw = t["mw0"] + (t["slope"] * (1.0 - alpha) * btime if transients else 0.0)
            mw = min(0.85, mw)
            e = t["e0"] * (1.0 - mw) * warm * EF
            st = base_state ** t["sens"]
            sat = 1.0 / (1.0 + P["sat_rate"] * m[k] / t["nst"]) if t["nst"] > 0 else 1.0
            enc = 1.0 - t["encw"] * P["enc_eps"] * encf
            mq = 1.0 - drift * t["susc"] * (1.0 - t["rho"])
            qk = t["v"] * e * st * sat * enc * mq
            qi += sh * qk
            ei += sh * e
            ed = sh * e * DT
            m[k] += ed
            dN += ed * t["encw"]
            dL += ed * t["demand"]
            if record:
                cs[0] += sh * e
                cs[1] += sh * st
                cs[2] += sh * sat
                cs[3] += sh * enc
                cs[4] += sh * mq
        Nenc += dN
        L += dL
        Ltot += dL
        q[i] = qi
        eng[i] = ei
        if record:
            cs[5] = drift
            comp.append(cs)
    return q, Ltot, eng, (np.array(comp) if record else None)


def consolidation(sleep_after, P):
    deficit = max(0.0, (P["need"] - sleep_after) / P["need"])
    return 1.0 - P["c_cons"] * deficit ** P["gamma_cons"]


def get_sequence(s, Hday, mix=None):
    n = int(round(Hday / DT))
    a = s.get("alloc", "fixed")
    if isinstance(a, str):
        if a == "fixed":
            return fixed_sequence(n, mix)
        if a == "heuristic":
            return heuristic_sequence(n, mix)
        raise ValueError(a)
    # an explicit sequence of task indices defined as fractions of the day -> resample to n slots
    arr = np.asarray(a)
    idx = np.minimum((np.arange(n) + 0.5) / n * len(arr), len(arr) - 1).astype(int)
    out = np.zeros((n, 4))
    out[np.arange(n), arr[idx]] = 1.0
    return out


def qref_rate(s, P, tasks, alpha, mix=None):
    """Rested twin: D=0, F=0, no irregularity, same time of day, fixed daily mix, hour 1."""
    seq = fixed_sequence(SPH, mix)
    q, _, _, _ = simulate_day(1.0, s, P, tasks, 0.0, 0.0, alpha, False, seq)
    return float(q.mean())


# --------------------------------------------------------------------------------------------
# Year simulation
# --------------------------------------------------------------------------------------------
def simulate_year(s, P, mix=None, record=False, transients=True, ndays=NDAYS):
    tasks = task_arrays(P, mix)
    pat = s["pattern"]
    D = P["D0"]
    F = 0.0
    rng = np.random.default_rng(20260924)
    noise = rng.normal(0.0, P["irr_sd"], ndays) if s["irregular"] else np.zeros(ndays)
    days = []
    seq_cache = {}
    qref_cache = {}
    for d in range(ndays):
        typ = pat[d % 14]
        nxt = pat[(d + 1) % 14]
        alpha = P["adapt_max"] * (1.0 - math.exp(-d / P["adapt_tau"]))
        sl = s["sleep"] + noise[d]
        ext = min(P["ext_cap"], P["ext_frac"] * max(D, 0.0))
        if nxt == "R":
            sl += ext
        elif nxt == "P":
            sl += 0.5 * ext
        sl = max(3.0, sl)
        rec = dict(day=d, type=typ, D=D, F=F, alpha=alpha, sleep_after=sl)
        if typ == "R":
            Hday = 0.0
            load = 0.0
            leisure = 24.0 - s["tib"] - s["life"]
            rec.update(Hday=0.0, RHE=0.0, load=0.0)
        else:
            Hday = s["H"] if typ == "S" else round(s["H"] * P["partial_frac"] / DT) * DT
            key = round(Hday / DT)
            if key not in seq_cache:
                seq_cache[key] = get_sequence(s, Hday, mix)
            seq = seq_cache[key]
            q, load, eng, comp = simulate_day(Hday, s, P, tasks, D, F, alpha, s["irregular"], seq,
                                              transients=transients, record=record)
            cons = consolidation(sl, P)
            q = q * cons
            ak = round(alpha, 4)
            if ak not in qref_cache:
                qref_cache[ak] = qref_rate(s, P, tasks, alpha, mix)
            qref = qref_cache[ak]
            n = len(q)
            nh = int(math.ceil(n / SPH))
            Qh = np.array([q[h * SPH:(h + 1) * SPH].mean() for h in range(nh)])
            Eh = np.array([eng[h * SPH:(h + 1) * SPH].mean() for h in range(nh)])
            rec.update(Hday=Hday, Qh=Qh, Eh=Eh, qref=qref, cons=cons, load=load,
                       RHE=float(q.sum() * DT / qref))
            if record:
                rec["comp"] = np.array([comp[h * SPH:(h + 1) * SPH].mean(axis=0) for h in range(nh)])
            leisure = s["leisure"] + (s["H"] - Hday)
        mu = P["mu0"] + P["mu_leis_max"] * (1.0 - math.exp(-leisure / P["leis_scale"])) + \
            P["mu_exmed"] * s["exmed"]
        F = F * (1.0 - min(mu, 0.95)) + P["eta"] * max(0.0, load - P["L_sus"])
        D = max(0.0, (1.0 - P["lam_debt"]) * D + P["need"] - sl)
        days.append(rec)
    return days


def annual(days):
    rhe = sum(r["RHE"] for r in days)
    nom = sum(r["Hday"] for r in days)
    return rhe, nom


TIMEPOINTS = {"wk1-2": [0], "1m": [1, 2], "3m": [6], "6m": [13], "12m": [25]}


def timepoint_curves(days, cycles, nh=14):
    """Mean over study days in the given 14-day cycles of R(t,h), A(t,h), e(t,h)."""
    Rs, As, Es, rhe, comps = [], [], [], [], []
    for c in cycles:
        for d in range(14 * c, 14 * c + 14):
            r = days[d]
            if r["type"] != "S":
                continue
            Qh = r["Qh"][:nh]
            Rs.append(100 * Qh / Qh[0])
            As.append(100 * Qh / r["qref"])
            Es.append(r["Eh"][:nh])
            rhe.append(r["RHE"])
            if "comp" in r:
                comps.append(r["comp"][:nh])
    out = dict(R=np.mean(Rs, axis=0), A=np.mean(As, axis=0), E=np.mean(Es, axis=0), RHE=float(np.mean(rhe)))
    if comps:
        out["comp"] = np.mean(comps, axis=0)
    return out


def first_le(arr, thr):
    for i, x in enumerate(arr):
        if x <= thr + 1e-9:
            return i + 1
    return None


def classify(R, thr):
    """First hour R<=thr; 'transient' if a later hour rises back above thr, else 'sustained'."""
    h = first_le(R, thr)
    if h is None:
        return None, "not reached by h14"
    later = R[h:]
    if len(later) and np.any(later > thr + 1e-9):
        h2 = None
        for j in range(h, len(R)):
            if R[j] <= thr and np.all(R[j:] <= thr + 1e-9):
                h2 = j + 1
                break
        return h, f"transient at h{h} (recovers after break); sustained from h{h2}" if h2 else \
            f"transient at h{h}; never sustained"
    return h, "sustained"


# --------------------------------------------------------------------------------------------
# Allocation optimisation (hill climb on slot order, fixed daily totals)
# --------------------------------------------------------------------------------------------
def optimise_sequence(s, P, D, F, alpha, mix=None, start="heuristic", max_pass=6):
    tasks = task_arrays(P, mix)
    Hday = s["H"]
    n = int(round(Hday / DT))
    seq = heuristic_sequence(n, mix) if start == "heuristic" else None
    idx = list(np.argmax(seq, axis=1))

    def val(ix):
        arr = np.zeros((n, 4))
        arr[np.arange(n), ix] = 1.0
        q, _, _, _ = simulate_day(Hday, s, P, tasks, D, F, alpha, s["irregular"], arr)
        return q.sum()

    best = val(idx)
    for _ in range(max_pass):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                if idx[i] == idx[j]:
                    continue
                idx[i], idx[j] = idx[j], idx[i]
                v = val(idx)
                if v > best + 1e-12:
                    best = v
                    improved = True
                else:
                    idx[i], idx[j] = idx[j], idx[i]
        if not improved:
            break
    return np.array(idx), best


# --------------------------------------------------------------------------------------------
# Q1 / Q2 / Q3 runners
# --------------------------------------------------------------------------------------------
def run_q1(P, alloc="fixed", record=False, transients=True):
    res = {}
    for scen in ("S1", "S2", "S3"):
        s = prompt1_schedule(14.0, scen, P, alloc=alloc)
        days = simulate_year(s, P, record=record, transients=transients)
        res[scen] = {tp: timepoint_curves(days, cyc) for tp, cyc in TIMEPOINTS.items()}
        res[scen]["_annual"] = annual(days)
        res[scen]["_sched"] = s
        res[scen]["_days"] = days
    return res


def run_q2(P, alloc="fixed"):
    rows = []
    for H in (8.0, 10.0, 12.0, 14.0):
        for scen in ("S1", "S2", "S3"):
            s = prompt1_schedule(H, scen, P, alloc=alloc)
            days = simulate_year(s, P)
            rows.append(dict(framework="prompt1", sub=scen, H=H, sched=s, days=days))
        for bi, nm in enumerate(("prompt2_tight", "prompt2_base", "prompt2_generous")):
            for variant in ("sleep_cut", "drop_exmed"):
                s = prompt2_schedule(H, bi, P, variant=variant, alloc=alloc)
                if s["feasible"] and variant == "drop_exmed":
                    continue
                days = simulate_year(s, P)
                rows.append(dict(framework=nm, sub=variant if not s["feasible"] else "feasible", H=H,
                                 sched=s, days=days))
    return rows


def block_split(days_long, Ha):
    """RHE of hours <= Ha and of hours > Ha inside the long schedule (slot-exact)."""
    first = 0.0
    added = 0.0
    for r in days_long:
        if r["type"] == "R":
            continue
        q = r["Qh"]
        # Qh is the mean rate per hour; hours are whole for H in {8,10,12,14} and partial days 4..7
        for h, v in enumerate(q):
            w = min(1.0, r["Hday"] - h)
            if h < Ha:
                first += w * v / r["qref"]
            else:
                added += w * v / r["qref"]
    return first, added


def increments(rows, P):
    """Block contribution of added hours vs spillover on hours <= Ha (same and later days).
    Spillover is split by counterfactual runs of the long schedule:
      CF1 = long schedule with sleep, leisure and exercise/meditation of the short schedule (accounting only)
      CF2 = long schedule with sleep of the short schedule
      load/strain channel   = first_Ha(CF1) - total(short)
      leisure(+ex/med) chan = first_Ha(CF2) - first_Ha(CF1)
      sleep channel         = first_Ha(long) - first_Ha(CF2)   (debt, consolidation, earlier late-day decline)"""
    out = []
    chains = {}
    for r in rows:
        if r["framework"] == "prompt1":
            chains.setdefault(("prompt1", r["sub"]), {})[r["H"]] = r
        else:
            ch = chains.setdefault((r["framework"], "sleep_cut_if_needed"), {})
            ch2 = chains.setdefault((r["framework"], "drop_exmed_if_needed"), {})
            if r["sub"] in ("feasible", "sleep_cut"):
                ch[r["H"]] = r
            if r["sub"] in ("feasible", "drop_exmed"):
                ch2[r["H"]] = r
    for (fw, sub), ch in chains.items():
        for Ha, Hb in ((8.0, 10.0), (10.0, 12.0), (12.0, 14.0)):
            if Ha not in ch or Hb not in ch:
                continue
            ra, rb = ch[Ha], ch[Hb]
            sa, sb = ra["sched"], rb["sched"]
            tot_a, _ = annual(ra["days"])
            tot_b, _ = annual(rb["days"])
            first_b, added_b = block_split(rb["days"], Ha)
            cf1 = dict(sb, sleep=sa["sleep"], leisure=sa["leisure"], exmed=sa["exmed"])
            cf2 = dict(sb, sleep=sa["sleep"])
            f1, _ = block_split(simulate_year(cf1, P), Ha)
            f2, _ = block_split(simulate_year(cf2, P), Ha)
            out.append(dict(framework=fw, sub=sub, step=f"{int(Ha)}->{int(Hb)}", block=added_b,
                            spill=first_b - tot_a, net=tot_b - tot_a,
                            spill_load=f1 - tot_a, spill_leisure=f2 - f1, spill_sleep=first_b - f2,
                            feasible_a=sa["feasible"], feasible_b=sb["feasible"],
                            sleep_a=sa["sleep"], sleep_b=sb["sleep"],
                            leisure_a=sa["leisure"], leisure_b=sb["leisure"], broken_b=sb["broken"]))
    return out


REST_POS = {1: [13], 2: [6, 13], 3: [4, 9, 13], 4: [3, 6, 10, 13]}


def make_pattern(nfull, npart):
    pat = ["S"] * 14
    for p in REST_POS[nfull]:
        pat[p] = "R"
    for _ in range(npart):
        # middle of the longest run of study days
        best, bs, be = -1, 0, 0
        i = 0
        while i < 14:
            if pat[i] == "S":
                j = i
                while j < 14 and pat[j] == "S":
                    j += 1
                if j - i > best:
                    best, bs, be = j - i, i, j
                i = j
            else:
                i += 1
        pat[(bs + be - 1) // 2] = "P"
    return "".join(pat)


def q3_grid(P, budget_idx=1, Hs=None, fulls=(1, 2, 3, 4), parts=(0, 1, 2), alloc="fixed"):
    if Hs is None:
        Hs = [7.0 + 0.25 * i for i in range(23)]
    rows = []
    for H in Hs:
        for nf in fulls:
            for npart in parts:
                pat = make_pattern(nf, npart)
                s = prompt2_schedule(H, budget_idx, P, pattern=pat, alloc=alloc)
                if not s["feasible"]:
                    continue
                days = simulate_year(s, P)
                rhe, nom = annual(days)
                rows.append(dict(H=H, full=nf, partial=npart, pattern=pat, leisure_min=s["leisure"] * 60,
                                 RHE=rhe, nominal=nom, sleep=s["sleep"]))
    return rows


def q3_select(rows, floor_min=None, min_full=1, band=0.02):
    cand = [r for r in rows if r["full"] >= min_full and
            (floor_min is None or r["leisure_min"] >= floor_min - 1e-6)]
    if not cand:
        return None, []
    best = max(cand, key=lambda r: r["RHE"])
    near = [r for r in cand if r["RHE"] >= (1 - band) * best["RHE"]]
    return best, near


def band_str(near):
    if not near:
        return ""
    Hs = sorted(set(r["H"] for r in near))
    fs = sorted(set(r["full"] for r in near))
    ps = sorted(set(r["partial"] for r in near))
    return (f"{len(near)} plans within 2%: H {Hs[0]:.1f}-{Hs[-1]:.1f} h/day, full rest {fs} per 14 d, "
            f"partial {ps} per 14 d")


# --------------------------------------------------------------------------------------------
# Sensitivity (parallel)
# --------------------------------------------------------------------------------------------
SENS_KEYS = ["need", "lam_debt", "a_sleep", "D_scale", "ext_cap", "c_cons", "gamma_cons", "tau_crit0",
             "kD_tcrit", "w_slope", "p_dip", "mw0_scale", "mw_slope_scale", "sens_scale", "warm_day",
             "sat_rate", "stream_scale", "enc_eps", "drift_max", "drift_L50", "drift_s", "rho_scale",
             "beta_break", "L_sus", "eta", "mu0", "mu_leis_max", "leis_scale", "f_max", "F_scale",
             "adapt_max", "irr_pen"]

PESS = dict(a_sleep=0.40, lam_debt=0.10, c_cons=0.25, kD_tcrit=0.5, w_slope=0.10, mw_slope_scale=2.0,
            sat_rate=0.70, enc_eps=0.25, drift_max=0.55, drift_L50=5.0, L_sus=4.5, eta=0.24, f_max=0.40,
            adapt_max=0.0, mu_leis_max=0.15)
OPT = dict(a_sleep=0.12, lam_debt=0.35, c_cons=0.05, kD_tcrit=0.1, w_slope=0.03, mw_slope_scale=0.5,
           sat_rate=0.15, enc_eps=0.0, drift_max=0.15, drift_L50=8.0, L_sus=6.5, eta=0.06, f_max=0.15,
           adapt_max=0.30, mu_leis_max=0.45)

MIX_VARIANTS = {
    "mix_newheavy": {"NEW": 0.40, "PROB": 0.35, "RET": 0.15, "MOCK": 0.10},
    "mix_reviewheavy": {"NEW": 0.15, "PROB": 0.40, "RET": 0.35, "MOCK": 0.10},
}


def sens_eval(args):
    label, P, mix = args
    out = {"label": label}
    # (a) Q1 curves for all scenarios/timepoints (R bands) and <=80 hour (S2 3m)
    q1 = {}
    for scen in ("S1", "S2", "S3"):
        s = prompt1_schedule(14.0, scen, P)
        days = simulate_year(s, P, mix=mix)
        q1[scen] = {tp: timepoint_curves(days, cyc)["R"].tolist() for tp, cyc in TIMEPOINTS.items()}
        q1[scen + "_A"] = {tp: timepoint_curves(days, cyc)["A"].tolist() for tp, cyc in TIMEPOINTS.items()}
    out["q1"] = q1
    out["h80_S2_3m"] = first_le(np.array(q1["S2"]["3m"]), 80.0)
    out["h50_S2_3m"] = first_le(np.array(q1["S2"]["3m"]), 50.0)
    # (b) 12->14 net under prompt-1 (S1/S2/S3)
    nets = {}
    for scen in ("S1", "S2", "S3"):
        r12 = annual(simulate_year(prompt1_schedule(12.0, scen, P), P, mix=mix))[0]
        d14 = simulate_year(prompt1_schedule(14.0, scen, P), P, mix=mix)
        r14 = annual(d14)[0]
        first, added = block_split(d14, 12.0)
        nets[scen] = dict(net=r14 - r12, block=added, spill=first - r12)
    out["net12_14"] = nets
    # (c) optimal H under prompt-2 base (scenario A and B90)
    rows = q3_grid(P, 1, Hs=[7.0 + 0.5 * i for i in range(9)], fulls=(1, 2, 3, 4), parts=(0, 1))
    bestA, nearA = q3_select(rows)
    bestB, nearB = q3_select(rows, floor_min=90, min_full=2)
    out["optA"] = dict(H=bestA["H"], full=bestA["full"], partial=bestA["partial"], RHE=bestA["RHE"],
                       band=[min(r["H"] for r in nearA), max(r["H"] for r in nearA)])
    out["optB90"] = dict(H=bestB["H"], full=bestB["full"], partial=bestB["partial"], RHE=bestB["RHE"],
                         band=[min(r["H"] for r in nearB), max(r["H"] for r in nearB)])
    return out



# --------------------------------------------------------------------------------------------
# Post-processing: one-at-a-time (OAT) bands, threshold bands, Q3 stress tests
# --------------------------------------------------------------------------------------------
def sustained_onset(R, thr):
    for i in range(len(R)):
        if np.all(np.asarray(R[i:]) <= thr + 1e-9):
            return i + 1
    return None


def postprocess(run_stress=True):
    """R_low/R_high = envelope over OAT settings + task-mix variants (single-assumption changes).
    The stacked pessimistic/optimistic corners are reported separately (stress test, not a band)."""
    with open(os.path.join(OUT, "sensitivity_raw.json")) as f:
        sens = json.load(f)
    with open(os.path.join(OUT, "q1_tables.json")) as f:
        tables = json.load(f)
    oat = [x for x in sens if not x["label"].startswith("combined")]
    corners = {x["label"]: x for x in sens if x["label"].startswith("combined")}
    final_tables, final_thr = [], []
    for t in tables:
        scen, tp = t["scenario"], t["timepoint"]
        arr = np.array([x["q1"][scen][tp] for x in oat])
        lo, hi = arr.min(axis=0), arr.max(axis=0)
        t2 = dict(t)
        t2["R_low"] = [r5(x) for x in lo]
        t2["R_high"] = [r5(x) for x in hi]
        t2["R_low_raw"], t2["R_high_raw"] = lo.tolist(), hi.tolist()
        t2["R_corner_pess"] = [r5(x) for x in corners["combined_pessimistic"]["q1"][scen][tp]]
        t2["R_corner_opt"] = [r5(x) for x in corners["combined_optimistic"]["q1"][scen][tp]]
        final_tables.append(t2)
        R = np.array(t["raw_R"])
        rs = np.array(t["raw_Rsust"])
        firsts80 = [first_le(np.array(x["q1"][scen][tp]), 80) for x in oat]
        onsets80 = [sustained_onset(np.array(x["q1"][scen][tp]), 80) for x in oat]
        firsts50 = [first_le(np.array(x["q1"][scen][tp]), 50) for x in oat]
        onsets50 = [sustained_onset(np.array(x["q1"][scen][tp]), 50) for x in oat]

        def rng(v):
            nums = [x for x in v if x is not None]
            nn = sum(1 for x in v if x is None)
            if not nums:
                return "never by h14 in all OAT settings"
            s = f"h{min(nums)}-h{max(nums)}"
            if nn:
                s += f" ({nn} of {len(v)} OAT settings: not by h14)"
            return s
        final_thr.append(dict(
            scenario=scen, timepoint=tp,
            first80=first_le(R, 80), onset80=sustained_onset(R, 80), sust_only80=first_le(rs, 80),
            first50=first_le(R, 50), onset50=sustained_onset(R, 50), sust_only50=first_le(rs, 50),
            oat_first80=rng(firsts80), oat_onset80=rng(onsets80), oat_first50=rng(firsts50),
            oat_onset50=rng(onsets50),
            corner_pess_first80=first_le(np.array(corners["combined_pessimistic"]["q1"][scen][tp]), 80),
            corner_pess_first50=first_le(np.array(corners["combined_pessimistic"]["q1"][scen][tp]), 50),
            corner_opt_first80=first_le(np.array(corners["combined_optimistic"]["q1"][scen][tp]), 80),
            raw_R=[round(x, 1) for x in R]))
    with open(os.path.join(OUT, "q1_tables_final.json"), "w") as f:
        json.dump(final_tables, f, indent=1)
    with open(os.path.join(OUT, "q1_thresholds_final.json"), "w") as f:
        json.dump(final_thr, f, indent=1)
    if run_stress:
        q3_stress()


STRESS = {
    "strain_x2": dict(eta=0.24, f_max=0.40),
    "strain_x3_Lsus4.5": dict(eta=0.36, f_max=0.40, L_sus=4.5),
    "strain_x4_Lsus4": dict(eta=0.48, f_max=0.50, L_sus=4.0, mu0=0.03),
    "strain_x4_Lsus4_leisure_strong": dict(eta=0.48, f_max=0.50, L_sus=4.0, mu0=0.03, mu_leis_max=0.45,
                                           leis_scale=6.0),
    "strain_x6_Lsus4": dict(eta=0.72, f_max=0.60, L_sus=4.0, mu0=0.03, F_scale=3.0),
}


def _stress_one(args):
    label, upd = args
    P = base_params()
    P.update(upd)
    rows = q3_grid(P, 1, Hs=[7.0 + 0.5 * i for i in range(9)], fulls=(1, 2, 3, 4), parts=(0, 1, 2))
    bA, nA = q3_select(rows)
    bB, nB = q3_select(rows, floor_min=90, min_full=2)
    r12 = annual(simulate_year(prompt1_schedule(12.0, "S2", P), P))[0]
    r14 = annual(simulate_year(prompt1_schedule(14.0, "S2", P), P))[0]
    r10 = annual(simulate_year(prompt1_schedule(10.0, "S2", P), P))[0]
    return dict(label=label, upd=upd, optA=(bA["H"], bA["full"], bA["partial"], round(bA["RHE"], 1)),
                bandA=band_str(nA), optB90=(bB["H"], bB["full"], bB["partial"], round(bB["RHE"], 1)),
                bandB90=band_str(nB), net10_12_S2=r12 - r10, net12_14_S2=r14 - r12)


def q3_stress():
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(_stress_one, list(STRESS.items())))
    with open(os.path.join(OUT, "q3_stress.json"), "w") as f:
        json.dump(res, f, indent=1)
    return res

# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------
def r5(x):
    return float(5 * round(float(x) / 5.0))


def main():
    os.makedirs(OUT, exist_ok=True)
    P = base_params()
    summary = {}

    # ---------------- budgets check ----------------
    budget_log = []
    for scen in ("S1", "S2", "S3"):
        for H in (8.0, 10.0, 12.0, 14.0):
            s = prompt1_schedule(H, scen, P)
            ok, tot = check_budget(s)
            budget_log.append(dict(name=s["name"], ok=ok, total=tot, H=H, life=s["life"], tib=s["tib"],
                                   sleep=s["sleep"], leisure=s["leisure"]))
    for bi in range(3):
        for H in (8.0, 10.0, 12.0, 14.0):
            for v in ("sleep_cut", "drop_exmed"):
                s = prompt2_schedule(H, bi, P, variant=v)
                ok, tot = check_budget(s)
                budget_log.append(dict(name=s["name"] + "_" + v, ok=ok, total=tot, H=H, life=s["life"],
                                       tib=s["tib"], sleep=s["sleep"], leisure=s["leisure"],
                                       feasible=s["feasible"], broken=s["broken"]))
        b = tb.BUDGETS[bi]
        summary[f"maxstudy_budget{bi}"] = tb.max_study_hours(b)
    assert all(r["ok"] for r in budget_log), "24 h budget violated"
    with open(os.path.join(OUT, "budget_check.json"), "w") as f:
        json.dump(budget_log, f, indent=1)

    # ---------------- Q1 ----------------
    q1 = run_q1(P, record=True)
    q1_sust = run_q1(P, transients=False)
    q1_rows = []
    hourly = {}
    for scen in ("S1", "S2", "S3"):
        for tp in TIMEPOINTS:
            c = q1[scen][tp]
            cs = q1_sust[scen][tp]
            assert abs(c["R"][0] - 100.0) < 1e-9
            hourly[(scen, tp)] = dict(R=c["R"], A=c["A"], E=c["E"], RHE=c["RHE"], Rsust=cs["R"],
                                      comp=c.get("comp"))
            for h in range(14):
                cp = c["comp"][h]
                q1_rows.append(dict(scenario=scen, timepoint=tp, hour=h + 1, R=c["R"][h], A=c["A"][h],
                                    engaged=c["E"][h], R_sustained_only=cs["R"][h],
                                    eng_comp=cp[0], state=cp[1], sat=cp[2], enc=cp[3], method_q=cp[4],
                                    drift=cp[5]))
    with open(os.path.join(OUT, "q1_hourly_raw.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(q1_rows[0].keys()))
        w.writeheader()
        w.writerows(q1_rows)
    # daily state trajectory (S2)
    with open(os.path.join(OUT, "q1_daily_state.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "day", "type", "debt_h", "strain_F", "alpha", "sleep_after", "cons", "load",
                    "RHE", "A_h1"])
        for scen in ("S1", "S2", "S3"):
            for r in q1[scen]["_days"]:
                w.writerow([scen, r["day"], r["type"], round(r["D"], 3), round(r["F"], 3),
                            round(r["alpha"], 3), round(r["sleep_after"], 3), round(r.get("cons", 1), 4),
                            round(r["load"], 3), round(r["RHE"], 3),
                            round(100 * r["Qh"][0] / r["qref"], 2) if "Qh" in r else ""])

    # allocation comparison (S2): heuristic and hill-climbed sequence at a 3-month state
    s2_days = q1["S2"]["_days"]
    ref = s2_days[91]
    s2 = prompt1_schedule(14.0, "S2", P)
    opt_idx, _ = optimise_sequence(s2, P, ref["D"], ref["F"], ref["alpha"])
    alloc_res = {}
    for nm, al in (("fixed", "fixed"), ("heuristic", "heuristic"), ("optimized", opt_idx.tolist())):
        s = prompt1_schedule(14.0, "S2", P, alloc=al)
        days = simulate_year(s, P)
        alloc_res[nm] = dict(curves={tp: timepoint_curves(days, cyc) for tp, cyc in TIMEPOINTS.items()},
                             annual=annual(days)[0])
    seq_str = "".join("NPRM"[i] for i in opt_idx)
    with open(os.path.join(OUT, "allocation_S2.json"), "w") as f:
        json.dump({nm: dict(annual_RHE=v["annual"],
                            R_3m=v["curves"]["3m"]["R"].tolist(), A_3m=v["curves"]["3m"]["A"].tolist(),
                            daily_RHE_3m=v["curves"]["3m"]["RHE"]) for nm, v in alloc_res.items()} |
                  {"optimized_sequence_15min_slots(N=new,P=prob,R=ret,M=mock)": seq_str}, f, indent=1)

    # ---------------- Q2 ----------------
    q2 = run_q2(P)
    inc = increments(q2, P)
    comp_rows = []
    for r in q2:
        rhe, nom = annual(r["days"])
        s = r["sched"]
        comp_rows.append(dict(framework=r["framework"], sub=r["sub"], H=r["H"], feasible=s["feasible"],
                              sleep=s["sleep"], tib=s["tib"], leisure=s["leisure"], life=s["life"],
                              exmed=s["exmed"], annual_RHE=rhe, annual_nominal=nom, broken=s["broken"],
                              mean_RHE_per_nominal_h=rhe / nom))
    with open(os.path.join(OUT, "q2_schedules.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comp_rows[0].keys()))
        w.writeheader()
        w.writerows(comp_rows)
    with open(os.path.join(OUT, "q2_increments.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inc[0].keys()))
        w.writeheader()
        w.writerows(inc)
    # allocation effect on the 12->14 increment (prompt-1 S2): hill-climb per H
    alloc_inc = {}
    for H in (12.0, 14.0):
        sH = prompt1_schedule(H, "S2", P)
        dH = simulate_year(sH, P)
        st = dH[91]
        idx, _ = optimise_sequence(sH, P, st["D"], st["F"], st["alpha"])
        dO = simulate_year(prompt1_schedule(H, "S2", P, alloc=idx.tolist()), P)
        alloc_inc[H] = dict(fixed=annual(dH)[0], optimized=annual(dO)[0])
    summary["alloc_12_14_prompt1_S2"] = alloc_inc

    # ---------------- Q3 ----------------
    q3 = {}
    for bi, nm in enumerate(("tight", "base", "generous")):
        q3[nm] = q3_grid(P, bi)
    with open(os.path.join(OUT, "q3_grid.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["budget", "H", "full", "partial", "pattern", "leisure_min", "sleep", "annual_RHE",
                    "annual_nominal"])
        for nm, rows in q3.items():
            for r in rows:
                w.writerow([nm, r["H"], r["full"], r["partial"], r["pattern"], round(r["leisure_min"], 1),
                            round(r["sleep"], 2), round(r["RHE"], 2), r["nominal"]])
    opt_rows = []
    for label, bud, floor, mf in (("A", "base", None, 1), ("B60", "base", 60, 2), ("B90", "base", 90, 2),
                                  ("B120", "base", 120, 2), ("A_tight", "tight", None, 1),
                                  ("A_generous", "generous", None, 1), ("B90_tight", "tight", 90, 2),
                                  ("B90_generous", "generous", 90, 2)):
        best, near = q3_select(q3[bud], floor_min=floor, min_full=mf)
        if best is None:
            opt_rows.append(dict(scenario=label, infeasible=True))
            continue
        opt_rows.append(dict(scenario=label, budget=bud, H=best["H"], full=best["full"],
                             partial=best["partial"], leisure_min=best["leisure_min"], RHE=best["RHE"],
                             nominal=best["nominal"], band=band_str(near),
                             near=[(r["H"], r["full"], r["partial"], round(r["RHE"], 1)) for r in
                                   sorted(near, key=lambda r: -r["RHE"])]))
    with open(os.path.join(OUT, "q3_optimum.json"), "w") as f:
        json.dump(opt_rows, f, indent=1)

    # best-plan allocation effect (Q3 A, base) with heuristic allocation
    bA = next(r for r in opt_rows if r["scenario"] == "A")
    sA = prompt2_schedule(bA["H"], 1, P, pattern=make_pattern(bA["full"], bA["partial"]))
    dA = simulate_year(sA, P)
    idxA, _ = optimise_sequence(sA, P, dA[91]["D"], dA[91]["F"], dA[91]["alpha"])
    sAo = prompt2_schedule(bA["H"], 1, P, pattern=make_pattern(bA["full"], bA["partial"]), alloc=idxA.tolist())
    summary["q3A_alloc"] = dict(fixed=annual(dA)[0], optimized=annual(simulate_year(sAo, P))[0])

    # ---------------- sensitivity ----------------
    tasks_list = [("base", P, None)]
    for k in SENS_KEYS:
        v, lo, hi, _, _ = PARAMS[k]
        for tag, val in (("lo", lo), ("hi", hi)):
            if val == v:
                continue
            Pk = dict(P)
            Pk[k] = val
            tasks_list.append((f"{k}={val}", Pk, None))
    for nm, mix in MIX_VARIANTS.items():
        tasks_list.append((nm, P, mix))
    Pp = dict(P)
    Pp.update(PESS)
    Po = dict(P)
    Po.update(OPT)
    tasks_list += [("combined_pessimistic", Pp, None), ("combined_optimistic", Po, None)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        sens = list(ex.map(sens_eval, tasks_list))
    with open(os.path.join(OUT, "sensitivity_raw.json"), "w") as f:
        json.dump(sens, f)

    # ---------------- assemble ----------------
    base_s = sens[0]
    env = {}
    for scen in ("S1", "S2", "S3"):
        for tp in TIMEPOINTS:
            arr = np.array([x["q1"][scen][tp] for x in sens])
            env[(scen, tp)] = (arr.min(axis=0), arr.max(axis=0))
    tables = []
    thr_rows = []
    for scen in ("S1", "S2", "S3"):
        for tp in TIMEPOINTS:
            hc = hourly[(scen, tp)]
            lo, hi = env[(scen, tp)]
            tables.append(dict(scenario=scen, timepoint=tp, R=[r5(x) for x in hc["R"]],
                               R_low=[r5(x) for x in lo], R_high=[r5(x) for x in hi],
                               A=[r5(x) for x in hc["A"]], first_hour_A=r5(hc["A"][0]),
                               daily_RHE=round(float(hc["A"].sum() / 100), 1),
                               raw_R=hc["R"].tolist(), raw_A=hc["A"].tolist(), raw_E=hc["E"].tolist(),
                               raw_Rsust=hc["Rsust"].tolist(), R_low_raw=lo.tolist(), R_high_raw=hi.tolist()))
            h80, c80 = classify(hc["R"], 80)
            h50, c50 = classify(hc["R"], 50)
            hs80 = first_le(hc["Rsust"], 80)
            hs50 = first_le(hc["Rsust"], 50)
            h80lo = first_le(lo, 80)
            h80hi = first_le(hi, 80)
            thr_rows.append(dict(scenario=scen, timepoint=tp, h80=h80, c80=c80, h50=h50, c50=c50,
                                 hs80=hs80, hs50=hs50, h80_band=(h80lo, h80hi),
                                 h50_band=(first_le(lo, 50), first_le(hi, 50))))
    with open(os.path.join(OUT, "q1_tables.json"), "w") as f:
        json.dump(tables, f, indent=1)
    with open(os.path.join(OUT, "q1_thresholds.json"), "w") as f:
        json.dump(thr_rows, f, indent=1, default=str)

    # sensitivity summary
    sens_summary = []
    for x in sens:
        sens_summary.append(dict(label=x["label"], h80_S2_3m=x["h80_S2_3m"], h50_S2_3m=x["h50_S2_3m"],
                                 net12_14_S1=x["net12_14"]["S1"]["net"], net12_14_S2=x["net12_14"]["S2"]["net"],
                                 net12_14_S3=x["net12_14"]["S3"]["net"],
                                 block12_14_S2=x["net12_14"]["S2"]["block"],
                                 spill12_14_S2=x["net12_14"]["S2"]["spill"],
                                 optA_H=x["optA"]["H"], optA_full=x["optA"]["full"],
                                 optA_partial=x["optA"]["partial"], optA_band=x["optA"]["band"],
                                 optB90_H=x["optB90"]["H"], optB90_full=x["optB90"]["full"],
                                 optB90_band=x["optB90"]["band"]))
    with open(os.path.join(OUT, "sensitivity_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sens_summary[0].keys()))
        w.writeheader()
        w.writerows(sens_summary)

    summary.update(dict(
        q1_annual={scen: q1[scen]["_annual"] for scen in ("S1", "S2", "S3")},
        allocation={nm: dict(annual=v["annual"], daily_RHE_3m=v["curves"]["3m"]["RHE"],
                             R_3m=[round(x, 1) for x in v["curves"]["3m"]["R"]],
                             A_3m=[round(x, 1) for x in v["curves"]["3m"]["A"]])
                    for nm, v in alloc_res.items()},
        optimized_sequence=seq_str,
    ))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    with open(os.path.join(OUT, "params.json"), "w") as f:
        json.dump({k: dict(value=v[0], low=v[1], high=v[2], label=v[3], basis=v[4]) for k, v in PARAMS.items()}
                  | {"TASK(v,e0,mw0,slope,sens,demand,n_streams,enc_w,rho,susc,mix)": TASK,
                     "TASK_BASIS": TASK_BASIS}, f, indent=1)
    postprocess()
    print("done")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--post":
        postprocess()
        print("post done")
    else:
        main()
