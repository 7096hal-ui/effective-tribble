#!/usr/bin/env python3
"""M1_physiology -- physiology-first model of hourly and annual study productivity.

Structure (all multipliers; see equations() for the full list):
  Q(t,h) = e(t,h) * eta(t,h)                       [learning units per nominal hour]
  e   = e0 * warm * (1 - F) * m_B * sqrt(phys)      engaged fraction of the nominal hour
  eta = sqrt(phys) * T(G) * c_content * m_cons      encoding/consolidation value of engaged time
  phys = m_thr(S + kappa_I*I - Theta(clock)) * (1 - dip) * (1 - inertia) * (1 - beta_I*I) * (1 - irr)

  S      : Borbely-type homeostatic pressure (rises with time awake, decays in sleep)
  Theta  : circadian wake-maintenance threshold, calibrated so a well-slept person is
           unimpaired until tau_crit (~16 h) awake
  I      : chronic effective sleep debt (h), leaky integrator -> equilibrium, not linear growth
  F      : time-on-task fatigue inside a block, decays during meal / other breaks
  G      : cumulative study hours today -> drift into low-effort methods (Blain 2016)
  B      : slow load-driven fatigue (weeks), partly removed by rest days and leisure
  R = 100*Q(h)/Q(1); A = 100*Q(h)/Q_ref, Q_ref = first hour of a fully recovered twin
All values are model assumptions anchored to the evidence digest; nothing is fitted to data.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import copy
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, "/home/user/effective-tribble/model")
import time_budget as tb  # noqa: E402

DT = 0.25  # h, integration step inside study blocks
N_DAYS = 365

# ---------------------------------------------------------------------------
# Parameters: name -> (value, (lo, hi), label, basis)
# ---------------------------------------------------------------------------
PARAM_META = {
    # --- sleep need and chronic debt ---
    "need": (8.3, (7.9, 8.9), "literature_constrained",
             "Sleep need of ~20 y/o, digest s1: Van Dongen 2003 implied 8.16 h [S], Kitamura 2016 8.4 h [S], Klerman&Dijk asymptote 8.9 h"),
    "tau_I": (4.0, (2.5, 10.0), "indirect_estimate",
              "Debt time constant (days). Kitamura 2016: ~4 days to repay 1 h debt [S]; Belenky 2003: 7 h TIB speed stabilised after ~4 days [M]; upper end allows Van Dongen 6 h TIB declines continuing over 14 d [S]; converges per McCauley 2009 [S,B]"),
    "beta_I": (0.009, (0.004, 0.018), "indirect_estimate",
               "Fractional learning loss per hour of effective debt. Lowe 2017: LTM g=-0.19, exec -0.32, attention -0.41 [S,I]; composite g~-0.25 x assumed outcome CV 0.4 => ~10% at a typical restriction-study effective debt of ~10 h"),
    "kappa_I": (0.006, (0.0, 0.012), "assumption",
                "Debt adds to homeostatic pressure (allostatic idea, McCauley 2009 [S,B]) so evening impairment starts earlier; 6 h of debt moves the ~16 h crossing ~1.5 h earlier"),
    "rho_reb": (0.3, (0.15, 0.5), "assumption",
                "Recovery-sleep capacity on a sleep-in night: actual sleep <= need + rho*I (partial repayment; Belenky/Lo: recovery incomplete after 2-3 nights [M])"),
    "sleepin": (1.5, (0.5, 2.5), "assumption", "Extra time in bed on the night before a full rest day (h)"),
    # --- homeostatic / circadian ---
    "tau_r": (18.2, (15.0, 22.0), "indirect_estimate",
              "Process S rise time constant (h); standard two-process value (Daan/Borbely 1984, from memory, not in digest)"),
    "tau_d": (4.2, (3.0, 5.0), "indirect_estimate",
              "Process S sleep decay time constant (h); standard two-process value (from memory, not in digest)"),
    "tau_crit": (16.0, (15.0, 17.0), "literature_constrained",
                 "Well-slept alertness roughly stable to ~16 h awake (Dijk 1992, Dijk&Czeisler 1994, Wright 2002 [M,B]); Van Dongen critical wake 15.84+/-0.73 h [S]"),
    "a_c": (0.12, (0.08, 0.16), "assumption", "Amplitude of circadian wake-maintenance threshold (S units)"),
    "gamma_S": (0.6, (0.35, 1.2), "indirect_estimate",
                "Learning loss per S-unit above threshold. Calibrated so the morning after an all-nighter loses ~30% (Newbury 2021 deprivation before learning g=0.62 [S,I], mapped with outcome CV 0.4-0.6)"),
    "d_pl": (0.05, (0.0, 0.10), "assumption",
             "Post-lunch dip depth (fraction) at ~14:30, sd 1 h; 'variable post-lunch dip' (Monk 2005 [M,B]); transient"),
    "debt_amp": (0.10, (0.0, 0.2), "assumption",
                 "Debt amplifies time-on-task fatigue and post-lunch dip by (1 + debt_amp*I) (sleep loss unmasks ToT effects; not in digest)"),
    "w0": (0.15, (0.05, 0.30), "assumption", "Sleep inertia at waking (fraction), time constant 0.5 h; mostly gone before hour 1"),
    # --- within-block time-on-task ---
    "F_max": (0.08, (0.03, 0.16), "indirect_estimate",
              "Ceiling of within-block ToT loss. Ackerman 2009/2010: no objective decline over 3.5-5.5 h in motivated students [M,D]; Sievertsen 2016: -0.9% SD per school hour [S,I]; Hopstaken 2015: decline reversible [M,I]"),
    "tau_F": (2.5, (1.5, 4.0), "assumption", "ToT build-up time constant within a block (h)"),
    "tau_Frec": (0.5, (0.25, 1.0), "indirect_estimate",
                 "ToT recovery time constant during breaks (h). Sievertsen 2016: 20-30 min break +1.7% SD ~ offsets ~2 h of decline [S,I]; Albulescu 2022 longer breaks better [S,I]"),
    "adapt": (0.20, (0.0, 0.30), "indirect_estimate",
              "Fractional reduction of ToT ceiling with practice over the first weeks (tau 21 d). Brown et al. 2025: 22% less within-test decline after practice [S,I]"),
    # --- day-level effort drift / allocation ---
    "p_max": (0.40, (0.15, 0.60), "assumption",
              "Max share of late-day time drifting into low-effort methods. Blain 2016 / Wiehler 2022: shift to low-effort choices after ~6-6.25 h of hard cognitive control [S/M,I]; untested for studying"),
    "G50": (7.0, (5.5, 9.0), "indirect_estimate", "Study hours at which drift reaches half its max (~6 h engaged at e0=0.85; Blain/Wiehler)"),
    "v_low": (0.70, (0.55, 0.85), "indirect_estimate",
              "Value of drifted low-effort study relative to effortful methods. Roediger&Karpicke 2006: 40% vs 61% 1-week recall [S] (~0.66); planned light review raises it"),
    "zeta": (0.01, (0.0, 0.04), "assumption",
             "Within-block same-content diminishing return per hour under subject rotation (Rohrer&Taylor 2006 overlearning null [S,D]); high end = one subject per 5 h block"),
    "warm_min": (8.0, (0.0, 15.0), "assumption", "Settling-in minutes at 50% value at the start of every block"),
    "e0": (0.85, (0.75, 0.92), "assumption", "Engaged fraction of a rested nominal hour (lapses, micro-breaks). Cancels in R and A"),
    # --- slow multi-day fatigue ---
    "alpha_B": (0.0010, (0.0, 0.0025), "assumption",
                "Slow load fatigue per nominal hour above H0 per day; tuned so B ~8% mid-cycle at 14 h/day, 13+1, no leisure. Weak anchors: Pencavel 2015 output flattens above ~49 h/wk (manual work) [S,I]; burnout-achievement r=-0.24 [S, correlational]"),
    "H0": (6.0, (4.0, 8.0), "assumption",
           "Daily study hours that build no slow fatigue; Ericsson ~4 h/day (descriptive) [S]; Pencavel proportional below ~49 h/wk [S,I]"),
    "tau_B": (14.0, (7.0, 45.0), "assumption",
              "Decay time constant of slow fatigue (days); vacation effects fade within 1-4 weeks (de Bloom 2009, Speth 2024 [S])"),
    "phi_rest": (0.30, (0.15, 0.50), "indirect_estimate",
                 "Share of slow fatigue removed by one full rest day (half by a half-day). Binnewies 2010 weekend recovery -> next week [M]; vacation d=0.25-0.43 but fades [S]"),
    "lambda_L": (0.40, (0.0, 0.70), "assumption", "Max reduction of daily slow-fatigue build-up by leisure/detachment (saturates at 2 h recovery time)"),
    "omega_ex": (0.5, (0.0, 1.0), "assumption", "Exercise + meditation count as this fraction of leisure for recovery"),
    "c_cons": (0.11, (0.0, 0.20), "indirect_estimate",
               "Loss of consolidation of the day's learning x (nightly deficit / need). Newbury 2021 deprivation after learning g=0.28 [S,I] x CV 0.4; Berres&Erdfelder 2021 sleep after learning g=0.44 [S,I]"),
    "irr": (0.03, (0.0, 0.06), "assumption", "S3 only: extra loss from irregular sleep timing (circadian misalignment); not in digest"),
}
FIXED = {
    "midpoint": 2.75,   # clock time of sleep midpoint (02:45), circadian phase anchored to it
    "tau_W": 0.5,       # sleep inertia time constant (h)
    "dip_sigma": 1.0,   # post-lunch dip width (h)
    "sG": 1.0,          # drift logistic width (h)
    "tau_adapt": 21.0,  # days
    "L_sat": 2.0,       # h of recovery time at which leisure effect saturates
    "w_soft": 0.015,    # softplus smoothing (S units)
}


def base_params() -> dict:
    p = {k: v[0] for k, v in PARAM_META.items()}
    p.update(FIXED)
    return p


def derived(p: dict) -> dict:
    """Calibrate the circadian threshold mean so that a well-slept, entrained person
    (sleep = need centred on the midpoint) reaches the threshold at tau_crit hours awake."""
    d = dict(p)
    n = p["need"]
    w = 24.0 - n
    ed, er = math.exp(-n / p["tau_d"]), math.exp(-w / p["tau_r"])
    S_w = ed * (1 - er) / (1 - ed * er)          # steady-state S at waking, rested
    d["S_ref_w"] = S_w
    wake_ref = p["midpoint"] + n / 2.0
    S_crit = 1 - (1 - S_w) * math.exp(-p["tau_crit"] / p["tau_r"])
    d["t_peak"] = (p["midpoint"] - 6.0) % 24      # wake-maintenance zone ~2-3 h before habitual sleep onset
    d["t_dip"] = (p["midpoint"] + 11.75) % 24     # post-lunch dip ~14:30
    d["H_mean"] = S_crit - p["a_c"] * math.cos(2 * math.pi * (wake_ref + p["tau_crit"] - d["t_peak"]) / 24.0)
    return d


def circ_diff(a, b):
    x = (a - b + 12.0) % 24.0 - 12.0
    return x


def softplus(x):
    if x > 30:
        return x
    return math.log1p(math.exp(x))


# ---------------------------------------------------------------------------
# Day schedules. A schedule is a list of (kind, duration_h) from waking to bedtime.
# ---------------------------------------------------------------------------

def split_blocks(H):
    b1 = min(H, 4.0)
    b2 = min(H - b1, 5.0)
    b3 = max(0.0, H - b1 - b2)
    return b1, b2, b3


def assemble(morning, blocks, breaks, evening):
    segs = [("life", morning)]
    b1, b2, b3 = blocks
    if b1 > 0:
        segs.append(("study", b1))
    segs.append(("life", breaks[0]))
    if b2 > 0:
        segs.append(("study", b2))
    segs.append(("life", breaks[1]))
    if b3 > 0:
        segs.append(("study", b3))
    segs.append(("life", evening))
    # merge consecutive life segments
    out = []
    for k, dur in segs:
        if dur <= 1e-12:
            continue
        if out and out[-1][0] == k == "life":
            out[-1] = ("life", out[-1][1] + dur)
        else:
            out.append((k, dur))
    return out


def p1_segments(H, life, leisure):
    """Prompt-1 / Q1 schedule: life split morning 30%, lunch 25%, dinner 25%, evening 20% (+leisure)."""
    return assemble(0.30 * life, split_blocks(H), (0.25 * life, 0.25 * life), 0.20 * life + leisure)


def p2_items(b: tb.LifeBudget, drop_ex=False, drop_med=False):
    meals, hyg = b.meals / 60, b.hygiene / 60
    ex = 0.0 if drop_ex else b.exercise_per_day() / 60
    med = 0.0 if drop_med else b.meditation / 60
    chores, trans, comm = b.chores / 60, b.transitions / 60, b.commute / 60
    morning = 0.25 * meals + 0.4 * hyg + trans / 3 + comm / 2
    lunch = 0.375 * meals + med + trans / 3
    afternoon = 0.375 * meals + ex + trans / 3
    evening = 0.6 * hyg + chores + comm / 2
    life = morning + lunch + afternoon + evening
    return dict(morning=morning, lunch=lunch, afternoon=afternoon, evening=evening, life=life, exmed=ex + med)


def p2_segments(items, H, leisure):
    return assemble(items["morning"], split_blocks(H), (items["lunch"], items["afternoon"]), items["evening"] + leisure)


def day_spec(kind, H, segs, TIB, SE, rec_time, irr=0.0, partial_rec=None):
    wake = (FIXED["midpoint"] + TIB / 2.0) % 24
    total = sum(d for _, d in segs) + TIB if segs else None
    return dict(type=kind, H=H, segs=segs, TIB=TIB, SE=SE, sleep=TIB * SE, wake=wake,
                rec_time=rec_time, irr=irr, budget_total=total)


def make_pattern(n_rest, n_part, study, partial, rest):
    rest_pos = {0: [], 1: [13], 2: [6, 13], 3: [4, 9, 13], 4: [3, 6, 10, 13]}[n_rest]
    chosen = list(rest_pos)
    part_pos = []
    for _ in range(n_part):
        cands = [i for i in range(14) if i not in chosen]
        def dist(i):
            return min(min((i - r) % 14, (r - i) % 14) for r in chosen) if chosen else 0
        best = sorted(cands, key=lambda i: (-dist(i), i))[0]
        part_pos.append(best)
        chosen.append(best)
    pat = []
    for i in range(14):
        if i in rest_pos:
            pat.append(rest)
        elif i in part_pos:
            pat.append(partial)
        else:
            pat.append(study)
    return pat


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def run_day(segs, wake, S_w, I, B, day_idx, d, irr, m_cons, max_hours=None, record=False):
    """Simulate one study day. Returns per-nominal-hour Q (sum of q*dt), hour weights, S at bedtime,
    and optionally per-hour component means."""
    tau_r, tau_F, tau_Frec = d["tau_r"], d["tau_F"], d["tau_Frec"]
    amp = 1.0 + d["debt_amp"] * I
    Fmax = d["F_max"] * (1 - d["adapt"] * (1 - math.exp(-day_idx / d["tau_adapt"]))) * amp
    mI = max(0.0, 1 - d["beta_I"] * I)
    mB = max(0.0, 1 - B)
    Sshift = d["kappa_I"] * I
    dip_amp = d["d_pl"] * amp
    warm_h = d["warm_min"] / 60.0
    w = d["w_soft"]
    S, F, G, t = S_w, 0.0, 0.0, 0.0
    study_el = 0.0
    Qh, Wh = [], []
    comp = [] if record else None
    er_half = math.exp(-(DT / 2) / tau_r)
    er_full = math.exp(-DT / tau_r)
    ef_half = math.exp(-(DT / 2) / tau_F)
    ef_full = math.exp(-DT / tau_F)
    two_pi_24 = 2 * math.pi / 24.0
    for kind, dur in segs:
        if kind == "nap":  # 80% of the segment asleep; S decays; halves the remaining post-lunch dip (assumption)
            S = S * math.exp(-0.8 * dur / d["tau_d"])
            F *= math.exp(-dur / tau_Frec)
            dip_amp *= 0.5
            t += dur
            continue
        if kind != "study":
            S = 1 - (1 - S) * math.exp(-dur / tau_r)
            F *= math.exp(-dur / tau_Frec)
            t += dur
            continue
        nsub = int(round(dur / DT))
        blk = 0.0
        for _ in range(nsub):
            if max_hours is not None and study_el >= max_hours - 1e-9:
                return Qh, Wh, None, comp
            tm = t + DT / 2
            Smid = 1 - (1 - S) * er_half
            Fmid = Fmax - (Fmax - F) * ef_half
            Gmid = G + DT / 2
            clock = (wake + tm) % 24
            theta = d["H_mean"] + d["a_c"] * math.cos(two_pi_24 * (clock - d["t_peak"]))
            Delta = w * softplus((Smid + Sshift - theta) / w)
            m_thr = max(0.0, 1 - d["gamma_S"] * Delta)
            cd = circ_diff(clock, d["t_dip"]) / d["dip_sigma"]
            dip = dip_amp * math.exp(-0.5 * cd * cd)
            inert = d["w0"] * math.exp(-tm / d["tau_W"])
            phys = m_thr * (1 - dip) * (1 - inert) * mI * (1 - irr)
            ov = max(0.0, min(blk + DT, warm_h) - blk)
            warm = 1 - 0.5 * ov / DT
            content = max(0.0, 1 - d["zeta"] * (blk + DT / 2))
            drift = d["p_max"] / (1 + math.exp(-(Gmid - d["G50"]) / d["sG"]))
            T = 1 - drift * (1 - d["v_low"])
            sp = math.sqrt(max(phys, 0.0))
            e = d["e0"] * warm * (1 - Fmid) * mB * sp
            eta = sp * T * content * m_cons
            q = e * eta
            hi = int(study_el + 1e-9)
            while len(Qh) <= hi:
                Qh.append(0.0)
                Wh.append(0.0)
                if record:
                    comp.append(dict(e=0.0, eta=0.0, thr=0.0, dip=0.0, F=0.0, T=0.0, clock=0.0, awake=0.0))
            Qh[hi] += q * DT
            Wh[hi] += DT
            if record:
                c = comp[hi]
                c["e"] += e * DT; c["eta"] += eta * DT; c["thr"] += m_thr * DT
                c["dip"] += dip * DT; c["F"] += Fmid * DT; c["T"] += T * DT
                c["clock"] += clock * DT; c["awake"] += tm * DT
            S = 1 - (1 - S) * er_full
            F = Fmax - (Fmax - F) * ef_full
            G += DT
            t += DT
            study_el += DT
            blk += DT
    if record:
        for c, wgt in zip(comp, Wh):
            for k in ("e", "eta", "thr", "dip", "F", "T", "clock", "awake"):
                c[k] /= wgt
    return Qh, Wh, S, comp


def strain(H, rec_time, d):
    rec_eff = min(1.0, max(0.0, rec_time) / d["L_sat"])
    return d["alpha_B"] * max(0.0, H - d["H0"]) * (1 - d["lambda_L"] * rec_eff)


def simulate(pattern, p, n_days=N_DAYS, record_days=None, record_comp_days=None):
    """Simulate a year. pattern: list of 14 day specs. Returns dict with annual RHE by hour index,
    per-day records for requested days."""
    d = derived(p)
    need = d["need"]
    qI = math.exp(-1.0 / d["tau_I"])
    qB = math.exp(-1.0 / d["tau_B"])
    I, B = 0.0, 0.0
    S_bed = 0.62
    rhe_by_hour = np.zeros(20)
    nominal = 0.0
    days_out = {}
    states = []
    L = len(pattern)
    for day in range(n_days):
        spec = pattern[day % L]
        nxt = pattern[(day + 1) % L]
        # night before this day
        s = spec["sleep"]
        if spec["type"] == "rest":
            s_opp = (spec["TIB"] + d["sleepin"]) * spec["SE"]
            s = max(spec["sleep"], min(s_opp, need + d["rho_reb"] * I))
        I = max(0.0, I * qI + need - s)
        S_w = S_bed * math.exp(-s / d["tau_d"])
        states.append((day, spec["type"], I, B, s, S_w))
        if spec["type"] == "rest":
            wake_len = 24.0 - spec["TIB"] - d["sleepin"]
            S_bed = 1 - (1 - S_w) * math.exp(-wake_len / d["tau_r"])
            B = B * qB * (1 - d["phi_rest"])
            continue
        # sleep of the coming night (for consolidation of today's learning)
        s_next = nxt["sleep"]
        if nxt["type"] == "rest":
            s_next = max(nxt["sleep"], min((nxt["TIB"] + d["sleepin"]) * nxt["SE"], need + d["rho_reb"] * I))
        m_cons = 1 - d["c_cons"] * max(0.0, need - s_next) / need
        rec = record_comp_days is not None and day in record_comp_days
        Qh, Wh, S_end, comp = run_day(spec["segs"], spec["wake"], S_w, I, B, day, d, spec["irr"], m_cons, record=rec)
        S_bed = S_end
        # rested twin: first hour, same clock/time since wake, fully recovered
        Qr, _, _, _ = run_day(spec["segs"], spec["wake"], d["S_ref_w"], 0.0, 0.0, day, d, 0.0, 1.0, max_hours=1.0)
        Qref = Qr[0]
        A = [q / Qref for q in Qh]
        for i, a in enumerate(A):
            rhe_by_hour[i] += a
        nominal += sum(Wh)
        if record_days is not None and day in record_days:
            days_out[day] = dict(Q=Qh, W=Wh, Qref=Qref, I=I, B=B, s=s, comp=comp, type=spec["type"])
        # slow fatigue update
        if spec["type"] == "partial":
            B = B * qB * (1 - d["phi_rest"] / 2) + strain(spec["H"], spec["rec_time"], d)
        else:
            B = B * qB + strain(spec["H"], spec["rec_time"], d)
    return dict(rhe_by_hour=rhe_by_hour, RHE=float(rhe_by_hour.sum()), nominal=nominal, days=days_out, states=states)


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------
Q1_SCEN = {
    "S1": dict(life=1.75, TIB=8.25, sleep=7.6, irr=False),
    "S2": dict(life=2.5, TIB=7.5, sleep=7.0, irr=False),
    "S3": dict(life=3.0, TIB=7.0, sleep=6.3, irr=True),
}


def q1_pattern(scen, p, H=14.0):
    sc = Q1_SCEN[scen]
    SE = sc["sleep"] / sc["TIB"]
    irr = p["irr"] if sc["irr"] else 0.0
    segs = p1_segments(H, sc["life"], 0.0)
    study = day_spec("study", H, segs, sc["TIB"], SE, rec_time=0.0, irr=irr)
    rest = day_spec("rest", 0.0, None, sc["TIB"], SE, rec_time=24.0, irr=irr)
    return make_pattern(1, 0, study, study, rest), study


def p1_alloc(H, base="S2", need=8.3):
    """Prompt-1 reallocation: start from the 14 h scenario's life and sleep efficiency; freed time goes
    first to sleep (up to need), then to leisure. Returns TIB, sleep, leisure, SE, life, irr flag."""
    sc = Q1_SCEN[base]
    SE = sc["sleep"] / sc["TIB"]
    life = sc["life"]
    avail = 24.0 - H - life
    TIB = min(avail, max(sc["TIB"], need / SE))
    leisure = avail - TIB
    return dict(TIB=TIB, sleep=TIB * SE, leisure=leisure, SE=SE, life=life, irr=sc["irr"])


def p1_pattern(H, p, base="S2", n_rest=1, n_part=0):
    a = p1_alloc(H, base, p["need"])
    irr = p["irr"] if a["irr"] else 0.0
    segs = p1_segments(H, a["life"], a["leisure"])
    study = day_spec("study", H, segs, a["TIB"], a["SE"], rec_time=a["leisure"], irr=irr)
    rest = day_spec("rest", 0.0, None, a["TIB"], a["SE"], rec_time=24.0, irr=irr)
    return make_pattern(n_rest, n_part, study, study, rest), a, study


BUDGETS = {"tight": tb.BUDGETS[0], "base": tb.BUDGETS[1], "generous": tb.BUDGETS[2]}


def p2_alloc(H, bname, leisure_floor=0.0, variant="sleepcut"):
    """Prompt-2: 8.0 h actual sleep, fixed life items. If infeasible, conditional variants:
    'sleepcut' keeps everything else and cuts time in bed; 'dropex' drops exercise+meditation first,
    then cuts sleep if still needed."""
    b = BUDGETS[bname]
    SE = b.sleep_efficiency
    items = p2_items(b)
    TIB = 8.0 / SE
    avail = 24.0 - H - items["life"] - leisure_floor
    feasible = avail >= TIB - 1e-9
    broken = []
    if not feasible:
        if variant == "dropex":
            items = p2_items(b, drop_ex=True, drop_med=True)
            broken.append("exercise+meditation dropped")
            avail = 24.0 - H - items["life"] - leisure_floor
        if avail < TIB - 1e-9:
            broken.append(f"sleep cut to {avail * SE:.2f} h actual")
            TIB = avail
    leisure = 24.0 - H - items["life"] - TIB
    return dict(TIB=TIB, sleep=TIB * SE, SE=SE, leisure=leisure, items=items, feasible=feasible,
                broken=broken, life=items["life"])


def p2_pattern(H, bname, n_rest=1, n_part=0, leisure_floor=0.0, variant="sleepcut", p=None):
    a = p2_alloc(H, bname, leisure_floor, variant)
    items = a["items"]
    rec = a["leisure"] + (p["omega_ex"] if p else 0.5) * items["exmed"]
    segs = p2_segments(items, H, a["leisure"])
    study = day_spec("study", H, segs, a["TIB"], a["SE"], rec_time=rec)
    Hp = H / 2.0
    Hp = math.floor(Hp * 4 + 1e-9) / 4.0
    segs_p = p2_segments(items, Hp, a["leisure"] + (H - Hp))
    partial = day_spec("partial", Hp, segs_p, a["TIB"], a["SE"], rec_time=rec + (H - Hp))
    rest = day_spec("rest", 0.0, None, a["TIB"], a["SE"], rec_time=24.0)
    return make_pattern(n_rest, n_part, study, partial, rest), a, study


# ---------------------------------------------------------------------------
# Q1 analysis
# ---------------------------------------------------------------------------
TIMEPOINTS = {"wk1-2": [0], "1m": [1, 2], "3m": [6], "6m": [12], "12m": [25]}


def tp_days(pattern, cycles):
    out = []
    for c in cycles:
        for i in range(14):
            day = c * 14 + i
            if day < N_DAYS and pattern[i]["type"] == "study":
                out.append(day)
    return out


def q1_run(scen, p, record_comp=False):
    pat, study = q1_pattern(scen, p)
    alld = sorted({dd for cyc in TIMEPOINTS.values() for dd in tp_days(pat, cyc)})
    res = simulate(pat, p, record_days=set(alld), record_comp_days=set(alld) if record_comp else None)
    out = {}
    for tp, cyc in TIMEPOINTS.items():
        dl = tp_days(pat, cyc)
        Rs, As, comps = [], [], []
        Is, Bs = [], []
        for dd in dl:
            r = res["days"][dd]
            Q = np.array(r["Q"][:14])
            Rs.append(100 * Q / Q[0])
            As.append(100 * Q / r["Qref"])
            Is.append(r["I"]); Bs.append(r["B"])
            if record_comp:
                comps.append(r["comp"])
        out[tp] = dict(R=np.mean(Rs, axis=0), A=np.mean(As, axis=0), I=float(np.mean(Is)), B=float(np.mean(Bs)),
                       comp=comps)
    return out, res, study


def thresholds(R, thr):
    """first any hour with R<=thr; first hour from which R stays <=thr to hour 14; transient hours."""
    below = [i + 1 for i, r in enumerate(R) if r <= thr + 1e-9]
    first_any = below[0] if below else None
    first_sus = None
    for h in range(1, len(R) + 1):
        if all(R[i] <= thr + 1e-9 for i in range(h - 1, len(R))):
            first_sus = h
            break
    transient = [h for h in below if first_sus is None or h < first_sus]
    return first_any, first_sus, transient


# ---------------------------------------------------------------------------
# Latin hypercube sampling of the parameter box (sensitivity band, NOT a confidence interval)
# ---------------------------------------------------------------------------

# time constants and scale factors (base chosen near the geometric centre of the range) are sampled log-uniformly
LOG_SAMPLED = {"tau_I", "beta_I", "gamma_S", "F_max", "tau_F", "tau_Frec", "tau_B", "w0", "rho_reb"}


def lhs_samples(n, seed=11):
    rng = np.random.default_rng(seed)
    names = list(PARAM_META.keys())
    k = len(names)
    u = np.zeros((n, k))
    for j in range(k):
        perm = rng.permutation(n)
        u[:, j] = (perm + rng.random(n)) / n
    samples = []
    for i in range(n):
        p = base_params()
        for j, nm in enumerate(names):
            lo, hi = PARAM_META[nm][1]
            if nm in LOG_SAMPLED:
                p[nm] = math.exp(math.log(lo) + (math.log(hi) - math.log(lo)) * u[i, j])
            else:
                p[nm] = lo + (hi - lo) * u[i, j]
        samples.append(p)
    return samples


def _q1_sample(p):
    out = {}
    for sc in Q1_SCEN:
        r, _, _ = q1_run(sc, p)
        out[sc] = {tp: (r[tp]["R"].tolist(), r[tp]["A"].tolist()) for tp in TIMEPOINTS}
    # 12->14 prompt-1 net for the same sample
    r12 = simulate(p1_pattern(12.0, p)[0], p)
    r14 = simulate(p1_pattern(14.0, p)[0], p)
    out["net_12_14_p1"] = r14["RHE"] - r12["RHE"]
    out["block_12_14_p1"] = float(r14["rhe_by_hour"][12:].sum())
    r12b = simulate(p2_pattern(12.0, "base", p=p)[0], p)
    r14b = simulate(p2_pattern(14.0, "base", p=p)[0], p)
    out["net_12_14_p2base"] = r14b["RHE"] - r12b["RHE"]
    rows = q3_grid(p, budgets=("base",), H_grid=[9.5 + 0.25 * i for i in range(7)], rests=(1, 2), parts=(0,), floors=(0,))
    bA, _ = pick(rows, "base", 0, 1)
    out["optA_H"] = bA["H"]; out["optA_rest"] = bA["rest"]
    return out


# ---------------------------------------------------------------------------
# Q2 helpers
# ---------------------------------------------------------------------------

def increments(res_by_H, Hs):
    rows = []
    for a, b in zip(Hs[:-1], Hs[1:]):
        ra, rb = res_by_H[a], res_by_H[b]
        na = int(round(a))
        block = float(rb["rhe_by_hour"][na:].sum())
        spill = float(rb["rhe_by_hour"][:na].sum() - ra["rhe_by_hour"][:na].sum())
        rows.append(dict(step=f"{a:g}->{b:g}", block=block, spill=spill, net=rb["RHE"] - ra["RHE"]))
    return rows


def q2_all(p):
    out = {}
    # prompt-1 (S2 start; S1/S3 starts as sensitivity)
    for base in ("S2", "S1", "S3"):
        key = "prompt1" if base == "S2" else f"prompt1_{base}start"
        res, meta = {}, {}
        for H in (8.0, 10.0, 12.0, 14.0):
            pat, a, study = p1_pattern(H, p, base)
            res[H] = simulate(pat, p)
            meta[H] = dict(a, feasible=True, budget_total=study["budget_total"], broken=[])
        out[key] = (res, meta)
    for bname in ("base", "tight", "generous"):
        for variant in ("sleepcut", "dropex"):
            key = f"prompt2_{bname}" + ("" if variant == "sleepcut" else "_dropex")
            res, meta = {}, {}
            for H in (8.0, 10.0, 12.0, 14.0):
                pat, a, study = p2_pattern(H, bname, variant=variant, p=p)
                res[H] = simulate(pat, p)
                meta[H] = dict(TIB=a["TIB"], sleep=a["sleep"], leisure=a["leisure"], feasible=a["feasible"],
                               broken=a["broken"], life=a["life"], budget_total=study["budget_total"])
            out[key] = (res, meta)
    return out


# ---------------------------------------------------------------------------
# Q3 optimisation grid (prompt-2 conditions, feasible only)
# ---------------------------------------------------------------------------

def q3_grid(p, budgets=("base", "tight", "generous"), H_grid=None, rests=(1, 2, 3, 4), parts=(0, 1, 2),
            floors=(0, 30, 60, 90, 120)):
    if H_grid is None:
        H_grid = [7.0 + 0.25 * i for i in range(23)]  # 7.0 ... 12.5 h
    jobs = []
    for bname in budgets:
        for H in H_grid:
            for nr in rests:
                for npart in parts:
                    a = p2_alloc(H, bname, 0.0)
                    if not a["feasible"]:
                        continue
                    jobs.append((bname, H, nr, npart))
    rows = []
    for bname, H, nr, npart in jobs:
        pat, a, _ = p2_pattern(H, bname, nr, npart, 0.0, p=p)
        r = simulate(pat, p)
        leis = a["leisure"] * 60
        rows.append(dict(budget=bname, H=H, rest=nr, partial=npart, leisure_min=leis, RHE=r["RHE"],
                         nominal=r["nominal"],
                         max_floor=max([f for f in floors if leis >= f - 1e-6], default=None)))
    return rows


def pick(rows, budget, floor, min_rest):
    cand = [r for r in rows if r["budget"] == budget and r["leisure_min"] >= floor - 1e-6 and r["rest"] >= min_rest]
    if not cand:
        return None, []
    best = max(cand, key=lambda r: r["RHE"])
    band = [r for r in cand if r["RHE"] >= 0.98 * best["RHE"]]
    return best, band


def band_str(band):
    Hs = sorted({r["H"] for r in band})
    rs = sorted({r["rest"] for r in band})
    ps = sorted({r["partial"] for r in band})
    return f"H {min(Hs):g}-{max(Hs):g} h; full rest/14d {rs}; partial/14d {ps}; n={len(band)} plans"


# ---------------------------------------------------------------------------
# Sensitivity (one at a time) on the three target quantities
# ---------------------------------------------------------------------------

def targets(p):
    """(a) first sustained <=80% hour, S2 at 3 m; (b) 12->14 net RHE, prompt-1 and prompt-2 base sleep-cut;
    (c) optimal H under prompt-2 base: Scenario A (no floor, >=1 rest/14) and B60 (floor 60, >=2 rest/14)."""
    out = {}
    r, _, _ = q1_run("S2", p)
    R = r["3m"]["R"]
    fa, fs, _ = thresholds(R, 80)
    out["S2_3m_first80_any"] = fa
    out["S2_3m_first80_sus"] = fs
    out["S2_3m_R14"] = float(R[13])
    r3, _, _ = q1_run("S3", p)
    out["S3_3m_first80_sus"] = thresholds(r3["3m"]["R"], 80)[1]
    r12 = simulate(p1_pattern(12.0, p)[0], p)
    r14 = simulate(p1_pattern(14.0, p)[0], p)
    out["net12_14_p1"] = r14["RHE"] - r12["RHE"]
    r12b = simulate(p2_pattern(12.0, "base", p=p)[0], p)
    r14b = simulate(p2_pattern(14.0, "base", p=p)[0], p)
    out["net12_14_p2base_sleepcut"] = r14b["RHE"] - r12b["RHE"]
    rows = q3_grid(p, budgets=("base",), rests=(1, 2), parts=(0,), floors=(0, 60))
    bA, _ = pick(rows, "base", 0, 1)
    bB, _ = pick(rows, "base", 60, 2)
    out["optH_A_base"] = bA["H"]
    out["optH_B60_base"] = bB["H"]
    out["optrest_A_base"] = bA["rest"]
    # marginal value of the last feasible half hour in scenario A (base, 1 rest day)
    rA = {r_["H"]: r_["RHE"] for r_ in rows if r_["rest"] == 1}
    out["marg_10.5_11"] = rA[11.0] - rA[10.5]
    return out


def _oat_job(args):
    name, which, val = args
    p = base_params()
    p[name] = val
    t = targets(p)
    return name, which, val, t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def r5(x):
    return float(5 * round(x / 5.0))


def main():
    p = base_params()
    d = derived(p)
    report = {"derived": {k: d[k] for k in ("S_ref_w", "H_mean", "t_peak", "t_dip")}}

    # --- check: well-slept alertness flat to ~16 h, then declines ---
    chk = []
    S = d["S_ref_w"]
    wake_ref = p["midpoint"] + p["need"] / 2
    for tau in np.arange(0, 22.01, 1.0):
        St = 1 - (1 - S) * math.exp(-tau / d["tau_r"])
        clock = (wake_ref + tau) % 24
        th = d["H_mean"] + d["a_c"] * math.cos(2 * math.pi * (clock - d["t_peak"]) / 24)
        Delta = d["w_soft"] * softplus((St - th) / d["w_soft"])
        chk.append(dict(awake_h=float(tau), clock=float(clock), S=St, theta=th, m_thr=1 - d["gamma_S"] * Delta))
    with open(os.path.join(OUT, "check_rested_alertness.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(chk[0].keys()))
        w.writeheader(); w.writerows(chk)
    # all-nighter check (calibration of gamma_S): 25.5 h awake at ~08:30 with one night lost
    tau = 25.5
    St = 1 - (1 - S) * math.exp(-tau / d["tau_r"]) + d["kappa_I"] * p["need"]
    clock = (wake_ref + tau) % 24
    th = d["H_mean"] + d["a_c"] * math.cos(2 * math.pi * (clock - d["t_peak"]) / 24)
    loss_acute = d["gamma_S"] * d["w_soft"] * softplus((St - th) / d["w_soft"])
    report["allnighter_check_loss"] = 1 - (1 - loss_acute) * (1 - d["beta_I"] * p["need"])

    # --- Q1 base runs ---
    q1 = {}
    q1_records = []
    budget_checks = []
    for sc in Q1_SCEN:
        r, res, study = q1_run(sc, p, record_comp=True)
        q1[sc] = r
        budget_checks.append(dict(schedule=f"Q1_{sc}", H=14, TIB=study["TIB"], life_plus_leisure=sum(dd for k, dd in study["segs"] if k != "study"),
                                  study=sum(dd for k, dd in study["segs"] if k == "study"), total=study["budget_total"],
                                  actual_sleep=study["sleep"]))
        for tp in TIMEPOINTS:
            assert abs(r[tp]["R"][0] - 100) < 1e-9, "R(t,1) must be 100"
            comps = r[tp]["comp"]
            for h in range(14):
                row = dict(scenario=sc, timepoint=tp, hour=h + 1, R=r[tp]["R"][h], A=r[tp]["A"][h],
                           I_debt_h=r[tp]["I"], B_slow=r[tp]["B"])
                for k in ("e", "eta", "thr", "dip", "F", "T", "clock", "awake"):
                    row[k] = float(np.mean([c[h][k] for c in comps]))
                q1_records.append(row)
        # daily states for the whole year
        with open(os.path.join(OUT, f"q1_{sc}_daily_states.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["day", "type", "I_debt_h", "B_slow", "sleep_before_h", "S_wake"])
            w.writerows(res["states"])

    # --- LHS sensitivity band for Q1 and 12->14 sign ---
    NS = 240
    samples = lhs_samples(NS)
    with Pool(4) as pool:
        lhs = pool.map(_q1_sample, samples)
    band = {}
    thr_band = {}
    for sc in Q1_SCEN:
        for tp in TIMEPOINTS:
            Rs = np.array([s[sc][tp][0] for s in lhs])
            As = np.array([s[sc][tp][1] for s in lhs])
            band[(sc, tp)] = dict(R_lo=np.percentile(Rs, 10, axis=0), R_hi=np.percentile(Rs, 90, axis=0),
                                  R_med=np.percentile(Rs, 50, axis=0), A_med=np.percentile(As, 50, axis=0),
                                  A_lo=np.percentile(As, 10, axis=0), A_hi=np.percentile(As, 90, axis=0))
            f80 = [thresholds(R, 80)[1] or 15 for R in Rs]
            f50 = [thresholds(R, 50)[1] or 15 for R in Rs]
            f80a = [thresholds(R, 80)[0] or 15 for R in Rs]
            thr_band[(sc, tp)] = dict(f80_p10=np.percentile(f80, 10), f80_p50=np.percentile(f80, 50), f80_p90=np.percentile(f80, 90),
                                      f80any_p50=np.percentile(f80a, 50), f50_p50=np.percentile(f50, 50),
                                      f80any_p10=np.percentile(f80a, 10),
                                      f50_p10=np.percentile(f50, 10), share50=float(np.mean(np.array(f50) <= 14)),
                                      share80=float(np.mean(np.array(f80) <= 14)))
    nb = np.array([s["net_12_14_p2base"] for s in lhs])
    report["lhs_net12_14_p2base_sleepcut"] = dict(p10=float(np.percentile(nb, 10)), p50=float(np.percentile(nb, 50)),
                                                 p90=float(np.percentile(nb, 90)), share_negative=float(np.mean(nb < 0)))
    oh = np.array([s["optA_H"] for s in lhs]); orr = np.array([s["optA_rest"] for s in lhs])
    report["lhs_optA_base"] = dict(share_at_11=float(np.mean(oh >= 11.0 - 1e-9)), min_H=float(oh.min()),
                                   p10_H=float(np.percentile(oh, 10)), share_rest1=float(np.mean(orr == 1)))
    blk = np.array([s["block_12_14_p1"] for s in lhs])
    report["lhs_block12_14_p1"] = dict(p10=float(np.percentile(blk, 10)), p50=float(np.percentile(blk, 50)), p90=float(np.percentile(blk, 90)))
    nets = np.array([s["net_12_14_p1"] for s in lhs])
    report["lhs_net12_14_p1"] = dict(p10=float(np.percentile(nets, 10)), p50=float(np.percentile(nets, 50)),
                                     p90=float(np.percentile(nets, 90)), share_negative=float(np.mean(nets < 0)))

    # write Q1 table
    with open(os.path.join(OUT, "q1_hourly.csv"), "w", newline="") as f:
        fields = list(q1_records[0].keys()) + ["R_lo10", "R_hi90", "A_lo10", "A_hi90", "R_med", "A_med"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in q1_records:
            b = band[(row["scenario"], row["timepoint"])]
            h = row["hour"] - 1
            row.update(R_lo10=b["R_lo"][h], R_hi90=b["R_hi"][h], A_lo10=b["A_lo"][h], A_hi90=b["A_hi"][h],
                       R_med=b["R_med"][h], A_med=b["A_med"][h])
            w.writerow(row)

    hourly_tables = []
    thr_rows = []
    for sc in Q1_SCEN:
        for tp in TIMEPOINTS:
            R = q1[sc][tp]["R"]; A = q1[sc][tp]["A"]
            b = band[(sc, tp)]
            Rlo = np.minimum(b["R_lo"], R); Rhi = np.maximum(b["R_hi"], R)
            hourly_tables.append(dict(scenario=sc, timepoint=tp,
                                      R=[r5(x) for x in R], R_low=[r5(x) for x in Rlo], R_high=[r5(x) for x in Rhi],
                                      A=[r5(x) for x in A], first_hour_A=r5(A[0]),
                                      daily_RHE=round(float(A.sum() / 100), 1),
                                      raw=dict(R=R.tolist(), A=A.tolist(), I=q1[sc][tp]["I"], B=q1[sc][tp]["B"])))
            fa80, fs80, tr80 = thresholds(R, 80)
            fa50, fs50, tr50 = thresholds(R, 50)
            tb_ = thr_band[(sc, tp)]
            def fmt(x):
                return "none within 14 h" if x is None else f"h{x}"
            def fmtb(x):
                return "none" if x >= 15 else f"h{int(x)}"
            Rmin_h = int(np.argmin(R)) + 1
            thr_rows.append(dict(scenario=sc, timepoint=tp,
                                 first80_any=fa80, first80_sus=fs80, transient80=tr80,
                                 first50_any=fa50, first50_sus=fs50,
                                 band80=(tb_["f80_p10"], tb_["f80_p50"], tb_["f80_p90"]), share80=tb_["share80"], share50=tb_["share50"],
                                 first_hour_R_le_80=(f"base: {fmt(fs80)} sustained" + (f", first touch {fmt(fa80)}" if fa80 != fs80 else "") +
                                                     f" (base min R {R.min():.0f} at h{Rmin_h}; post-lunch trough h7-9 ~{R[6:9].min():.0f}, recovers after dinner break)"
                                                     f"; sampled-parameter band (10th/50th/90th pct) {fmtb(tb_['f80_p10'])}/{fmtb(tb_['f80_p50'])}/{fmtb(tb_['f80_p90'])}; "
                                                     f"reached by h14 in {100 * tb_['share80']:.0f}% of sampled sets"),
                                 first_hour_R_le_50=f"base {fmt(fs50)}; reached within 14 h in {100 * tb_['share50']:.0f}% of sampled parameter sets" +
                                 (f" (10th pct {fmtb(tb_['f50_p10'])})" if tb_['share50'] > 0.1 else "")))

    # --- Q2 ---
    q2 = q2_all(p)
    sched_rows, inc_rows = [], []
    for key, (res, meta) in q2.items():
        for H in (8.0, 10.0, 12.0, 14.0):
            m = meta[H]
            budget_checks.append(dict(schedule=key, H=H, TIB=m["TIB"], life_plus_leisure=m.get("life", 0) + m["leisure"],
                                      study=H, total=m["budget_total"], actual_sleep=m["sleep"]))
            sched_rows.append(dict(framework=key, hours=H, feasible=bool(m["feasible"]), actual_sleep_h=m["sleep"],
                                   leisure_h=m["leisure"], annual_RHE=res[H]["RHE"], annual_nominal_hours=res[H]["nominal"],
                                   broken=m["broken"]))
        for row in increments(res, [8.0, 10.0, 12.0, 14.0]):
            inc_rows.append(dict(framework=key, **row))
    with open(os.path.join(OUT, "q2_schedules.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sched_rows[0].keys())); w.writeheader(); w.writerows(sched_rows)
    with open(os.path.join(OUT, "q2_increments.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inc_rows[0].keys())); w.writeheader(); w.writerows(inc_rows)

    # break-even beta_I for the prompt-1 12->14 net (bisection)
    def net_p1(pp):
        return simulate(p1_pattern(14.0, pp)[0], pp)["RHE"] - simulate(p1_pattern(12.0, pp)[0], pp)["RHE"]
    brk = {}
    for nm, lo, hi in (("beta_I", 0.0, 0.2), ("alpha_B", 0.0, 0.05)):
        pp = base_params()
        pp[nm] = hi
        if net_p1(pp) > 0:
            brk[nm] = f">{hi}"
            continue
        a_, b_ = lo, hi
        for _ in range(30):
            mid = 0.5 * (a_ + b_)
            pp[nm] = mid
            if net_p1(pp) > 0:
                a_ = mid
            else:
                b_ = mid
        brk[nm] = 0.5 * (a_ + b_)
    # joint pessimistic debt corner
    pp = base_params(); pp.update(beta_I=0.018, tau_I=10.0, kappa_I=0.012, need=8.9, c_cons=0.2, debt_amp=0.2)
    brk["debt_all_high_net"] = net_p1(pp)
    pp = base_params(); pp.update(beta_I=0.018, tau_I=10.0, need=8.9)
    brk["beta_tau_need_high_net"] = net_p1(pp)
    pp = base_params(); pp.update(alpha_B=0.0025, H0=4.0, lambda_L=0.7, tau_B=45.0)
    brk["slowfatigue_all_high_net"] = net_p1(pp)
    report["breakeven_12_14_p1"] = brk

    # --- Q3 ---
    rows = q3_grid(p)
    with open(os.path.join(OUT, "q3_grid.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    opt = []
    for bname in ("base", "tight", "generous"):
        for label, floor, mr in (("A", 0, 1), ("B0", 0, 2), ("B60", 60, 2), ("B90", 90, 2), ("B120", 120, 2)):
            best, bnd = pick(rows, bname, floor, mr)
            if best is None:
                continue
            opt.append(dict(scenario=label if bname == "base" else f"{label}-{bname}", budget=bname,
                            daily_hours=best["H"], full_rest_days_per_14=best["rest"], partial_rest_days_per_14=best["partial"],
                            leisure_min=best["leisure_min"], annual_RHE=best["RHE"], annual_nominal_hours=best["nominal"],
                            near_optimal_band=band_str(bnd), floor=floor,
                            band_plans=[(r["H"], r["rest"], r["partial"], round(r["RHE"], 1)) for r in sorted(bnd, key=lambda r: -r["RHE"])]))
    with open(os.path.join(OUT, "q3_optimum.json"), "w") as f:
        json.dump(opt, f, indent=1)

    # --- OAT sensitivity ---
    base_t = targets(p)
    jobs = []
    for nm, (v, (lo, hi), lab, _) in PARAM_META.items():
        if nm == "e0":
            continue
        jobs.append((nm, "lo", lo)); jobs.append((nm, "hi", hi))
    with Pool(4) as pool:
        oat = pool.map(_oat_job, jobs)
    with open(os.path.join(OUT, "oat_sensitivity.csv"), "w", newline="") as f:
        keys = list(base_t.keys())
        w = csv.writer(f)
        w.writerow(["param", "which", "value"] + keys)
        w.writerow(["BASE", "", ""] + [base_t[k] for k in keys])
        for nm, which, val, t in oat:
            w.writerow([nm, which, val] + [t[k] for k in keys])
    report["base_targets"] = base_t
    # how strong must slow fatigue be before the scenario-A optimum (base budget) leaves the feasible maximum?
    def optH(pp, floor=0, mr=1):
        rr = q3_grid(pp, budgets=("base",), rests=(1, 2, 3), parts=(0,), floors=(0, 60))
        b_, bnd_ = pick(rr, "base", floor, mr)
        return b_["H"], b_["rest"], bnd_
    scan = []
    for mult in (1, 2, 3, 5, 8, 12, 20):
        pp = base_params(); pp["alpha_B"] = p["alpha_B"] * mult
        h_, r_, bnd_ = optH(pp)
        pp2 = dict(pp); pp2.update(lambda_L=0.7)
        h2_, r2_, _ = optH(pp2)
        scan.append(dict(alpha_mult=mult, optH=h_, optRest=r_, band=band_str(bnd_), optH_lambda07=h2_, optRest_lambda07=r2_))
    report["alphaB_scan_optH"] = scan
    report["oat"] = [(nm, which, val, t) for nm, which, val, t in oat]

    # --- nap variant (S2): 25-min nap slot (20 min asleep) splitting block 2 after 2 h, paid for by 25 min less TIB ---
    sc = Q1_SCEN["S2"]
    SE = sc["sleep"] / sc["TIB"]
    nap = 25 / 60
    TIBn = sc["TIB"] - nap
    L = sc["life"]
    segs = [("life", 0.3 * L), ("study", 4.0), ("life", 0.25 * L), ("study", 2.0), ("nap", nap), ("study", 3.0),
            ("life", 0.25 * L), ("study", 5.0), ("life", 0.2 * L)]
    study = day_spec("study", 14.0, segs, TIBn, SE, rec_time=0.0)
    study["sleep"] = TIBn * SE + 0.8 * nap  # nap sleep counts toward the daily debt balance
    rest = day_spec("rest", 0.0, None, TIBn, SE, rec_time=24.0)
    rest["sleep"] = TIBn * SE
    patn = make_pattern(1, 0, study, study, rest)
    dl = tp_days(patn, TIMEPOINTS["3m"])
    resn = simulate(patn, p, record_days=set(dl))
    Rn = np.mean([100 * np.array(resn["days"][x]["Q"]) / resn["days"][x]["Q"][0] for x in dl], axis=0)
    An = np.mean([100 * np.array(resn["days"][x]["Q"]) / resn["days"][x]["Qref"] for x in dl], axis=0)
    base_s2 = simulate(q1_pattern("S2", p)[0], p)
    report["nap_variant_S2_3m"] = dict(R=Rn.round(1).tolist(), A=An.round(1).tolist(), dayRHE=float(An.sum() / 100),
                                       annual_RHE=resn["RHE"], annual_RHE_base=base_s2["RHE"],
                                       total=sum(x for _, x in segs) + TIBn)
    report["budget_checks"] = budget_checks
    for bc in budget_checks:
        assert abs(bc["total"] - 24.0) < 1e-6, bc
    with open(os.path.join(OUT, "budget_checks.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(budget_checks[0].keys())); w.writeheader(); w.writerows(budget_checks)

    summary = dict(params={k: dict(value=v[0], range=v[1], label=v[2], basis=v[3]) for k, v in PARAM_META.items()},
                   fixed=FIXED, report=report, hourly_tables=hourly_tables, thresholds=thr_rows,
                   schedules=sched_rows, increments=inc_rows, optimization=opt)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(json.dumps(report["derived"], indent=1))
    print("allnighter loss", report["allnighter_check_loss"])
    print("LHS net 12->14 p1", report["lhs_net12_14_p1"])
    print("breakeven", report["breakeven_12_14_p1"])
    print("base targets", base_t)


if __name__ == "__main__":
    main()
