"""outputs/results.json -> figures/*.png (정적 그림, 라이트 모드)."""

from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401  (NanumGothic)
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(ROOT, "figures")

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURF = "#fcfcfb"
S = {"S1": "#2a78d6", "S2": "#eb6834", "S3": "#1baf7a"}
LAB = {"S1": "S1 회복 유리(실수면 약 7.7h)", "S2": "S2 기준(약 7.0h)", "S3": "S3 회복 불리(약 6.1h)"}


def style(ax):
    ax.set_facecolor(SURF)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_R(res):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True, facecolor=SURF)
    h = np.arange(1, 15)
    for ax, tp in zip(axes, ("1-2주", "3개월", "12개월")):
        style(ax)
        for lab in ("S1", "S2", "S3"):
            d = res["hourly"][lab][tp]
            ax.plot(h, d["R"], color=S[lab], linewidth=2, marker="o", markersize=4, label=LAB[lab])
            if lab == "S2":
                ax.fill_between(h, d["R_lo"], d["R_hi"], color=S[lab], alpha=0.12, linewidth=0,
                                label="S2 가정 범위(10~90백분위)")
        for y in (80, 50):
            ax.axhline(y, color=MUTED, linewidth=0.8)
            ax.text(14.3, y, f"{y}%", color=INK2, fontsize=8, va="center")
        ax.set_title(f"{tp}", color=INK, fontsize=11)
        ax.set_xticks(h)
        ax.set_xlabel("그날의 몇 번째 명목 공부 시간", color=INK2, fontsize=9)
        ax.set_ylim(30, 120)
    axes[0].set_ylabel("R: 같은 날 첫 시간 대비(%)", color=INK2, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("14시간 일정의 시간별 추가 학습성과(조건부 모형값, 관측값 아님)", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig1_R_hourly.png"), dpi=160)
    plt.close(fig)


def fig_A(res):
    fig, ax = plt.subplots(figsize=(7.5, 4.2), facecolor=SURF)
    style(ax)
    h = np.arange(1, 15)
    for lab in ("S1", "S2", "S3"):
        d = res["hourly"][lab]["12개월"]
        ax.plot(h, d["A"], color=S[lab], linewidth=2, marker="o", markersize=4, label=LAB[lab])
        ax.fill_between(h, d["A_lo"], d["A_hi"], color=S[lab], alpha=0.08, linewidth=0)
    ax.axhline(100, color=MUTED, linewidth=0.8)
    ax.text(14.2, 101, "충분히 회복된 첫 시간 = 100", color=INK2, fontsize=8, ha="right", va="bottom")
    ax.set_xticks(h)
    ax.set_ylim(20, 115)
    ax.set_xlabel("그날의 몇 번째 명목 공부 시간", color=INK2, fontsize=9)
    ax.set_ylabel("A: 회복된 기준 첫 시간 대비(%)", color=INK2, fontsize=9)
    ax.set_title("12개월 시점 A(음영: 가정 범위 10~90백분위)", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig2_A_12m.png"), dpi=160)
    plt.close(fig)


def fig_year(res):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), facecolor=SURF)
    for ax in axes:
        style(ax)
    for lab in ("S1", "S2", "S3"):
        rows = np.array(res["yearly"][lab], dtype=float)
        cyc = rows[:, 0] * 14 / 30.4
        axes[0].plot(cyc, rows[:, 1], color=S[lab], linewidth=2, label=LAB[lab])
        axes[0].fill_between(cyc, rows[:, 4], rows[:, 5], color=S[lab], alpha=0.08, linewidth=0)
        axes[1].plot(cyc, rows[:, 2], color=S[lab], linewidth=2, label=LAB[lab])
        axes[1].fill_between(cyc, rows[:, 6], rows[:, 7], color=S[lab], alpha=0.08, linewidth=0)
    axes[0].set_title("첫 1시간의 A(%)", color=INK, fontsize=11)
    axes[1].set_title("공부일 하루 총학습량(RHE: 회복된 첫 시간 몇 개분)", color=INK, fontsize=11)
    for ax in axes:
        ax.set_xlabel("경과 개월(14일 주기 평균)", color=INK2, fontsize=9)
    axes[0].set_ylim(50, 100)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig3_year.png"), dpi=160)
    plt.close(fig)


def fig_opt(res):
    fig, ax = plt.subplots(figsize=(7.5, 4.2), facecolor=SURF)
    style(ax)
    cols = {"1": "#2a78d6", "2": "#eb6834"}
    names = {"1": "완전 휴일 14일에 1일", "2": "완전 휴일 7일에 1일"}
    for k in ("1", "2"):
        sw = res["opt_sweep"][k]
        H = np.array(sw["H"])
        ax.plot(H, np.array(sw["rel_p50"]) * 100, color=cols[k], linewidth=2, marker="o", markersize=4, label=names[k] + " (중앙값)")
        ax.fill_between(H, np.array(sw["rel_p10"]) * 100, np.array(sw["rel_p90"]) * 100, color=cols[k], alpha=0.10, linewidth=0)
    ax.set_xlabel("공부일 명목 공부시간(h) — 실수면 8h·운동·명상 조건, 기준 생활시간", color=INK2, fontsize=9)
    ax.set_ylabel("연간 총학습량(같은 가정 조합에서 휴일 14일에 1일·최대 시간 = 100)", color=INK2, fontsize=9)
    ax.set_title("두 번째 질문 틀: 일일 공부시간별 연간 총량(음영: 가정 범위)", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig4_opt_prompt2.png"), dpi=160)
    plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    with open(os.path.join(HERE, "outputs", "results.json"), encoding="utf-8") as f:
        res = json.load(f)
    fig_R(res)
    fig_A(res)
    fig_year(res)
    fig_opt(res)


if __name__ == "__main__":
    main()
