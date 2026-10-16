"""Step 17e — figures for the revision (static PNG 300 dpi + PDF).

fig3_marginal_effect_true_cov   Figure 3 redrawn with the true covariance of
                                (GPR x FTA, GPR x Depth), two-way clustered band,
                                plus the distribution of depth among FTA links.
fig_size_groups                 GPR x Depth effect on survival by lagged link size:
                                pooled model (S3) and split samples, in percentage
                                points and relative to each group's exit rate.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r17_common import FIGURES, TABLES  # noqa: E402

INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
BAR = "#b9b8b3"

plt.rcParams.update(
    {
        "font.family": "Arial",
        "font.size": 9,
        "axes.edgecolor": INK_2,
        "axes.labelcolor": INK,
        "axes.linewidth": 0.6,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    }
)


def hairline_grid(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, linewidth=0.6, linestyle="-")
    ax.set_axisbelow(True)


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------- Figure 3
curve = pd.read_csv(TABLES / "17d_figure3_curve.csv")
curve = curve[curve["inference"] == "pair_year"]
thr = pd.read_csv(TABLES / "17d_figure3_thresholds.csv")
thr = thr[(thr["inference"] == "pair_year") & (thr["band"] == "true covariance")].iloc[0]
hist = pd.read_csv(TABLES / "17b_depth_histogram_members.csv")
hist = hist[hist["sample"] == "survival"]

fig, (ax, axh) = plt.subplots(
    2, 1, figsize=(6.5, 4.6), sharex=True, gridspec_kw={"height_ratios": [4, 1.1], "hspace": 0.08}
)
x = curve["provisions"].to_numpy()
ax.fill_between(x, 100 * curve["ci_low"], 100 * curve["ci_high"], color=SERIES_1, alpha=0.14, linewidth=0)
ax.plot(x, 100 * curve["net_effect"], color=SERIES_1, linewidth=2, solid_capstyle="round")
ax.axhline(0, color=INK_2, linewidth=0.8)
zero_cross = float(thr["zero_crossing_provisions"])
beyond = float(thr["band_excludes_zero_from_provisions"])
ax.axvline(zero_cross, color=INK_2, linewidth=0.6)
ax.text(zero_cross + 0.6, ax.get_ylim()[1] * 0.0 + 0.45, f"net effect = 0\nat {zero_cross:.1f} provisions", color=INK_2, fontsize=8, va="top")
if np.isfinite(beyond):
    ax.axvline(beyond, color=INK_2, linewidth=0.6)
    ax.text(beyond - 0.6, -2.55, f"95% CI excludes 0\nfrom {np.ceil(beyond):.0f} provisions", color=INK_2, fontsize=8, ha="right", va="bottom")
ax.text(1.0, -0.62, "95% CI", color=SERIES_1, fontsize=8, alpha=0.9)
ax.set_ylabel("Change in one-year survival\nprobability (percentage points)")
hairline_grid(ax)
ax.set_xlim(0, 38)

axh.bar(hist["provisions"], 100 * hist["share"], width=0.8, color=BAR, linewidth=0)
axh.set_ylabel("FTA link-\nyears (%)")
axh.set_xlabel("Legally enforceable provisions in force (t − 1)")
hairline_grid(axh)
axh.set_xticks(range(0, 39, 5))
save(fig, "fig3_marginal_effect_true_cov")

# --------------------------------------------------------------- size groups
pooled = pd.read_csv(TABLES / "17c_size_group_effects.csv")
pooled = pooled[(pooled["model"] == "S3_size_groups") & (pooled["inference"] == "pair_year")].reset_index(drop=True)
split = pd.read_csv(TABLES / "17c2_size_diagnostics_groups.csv")
split = split[(split["model"] == "(a) split samples") & (split["inference"] == "pair_year")].reset_index(drop=True)
crit = stats.t.ppf(0.975, 15)

labels = ["< $10k", "$10k–100k", "$100k–1M", "≥ $1M"]
ticks = [f"{lab}\nexit {100 * r:.1f}%" for lab, r in zip(labels, pooled["exit_rate"])]
pos = np.arange(4)

fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.3), gridspec_kw={"wspace": 0.32})
series = [
    ("Pooled model, common fixed effects", pooled["theta_gpr_x_depth"] * 100,
     (pooled["theta_ci_low"] * 100, pooled["theta_ci_high"] * 100),
     pooled["relative_change_exit_prob"] * 100,
     (pooled["relative_ci_low"] * 100, pooled["relative_ci_high"] * 100), SERIES_1, "o", -0.09),
    ("Separate model per size group", split["theta_pp"],
     (split["theta_pp"] - crit * split["theta_se_pp"], split["theta_pp"] + crit * split["theta_se_pp"]),
     split["relative_pct"],
     (split["relative_pct"] - crit * split["relative_se_pct"], split["relative_pct"] + crit * split["relative_se_pct"]), SERIES_2, "s", 0.09),
]
for panel, ax in enumerate(axes):
    for name, est, ci, rel, rel_ci, color, marker, shift in series:
        y = est if panel == 0 else rel
        lo, hi = ci if panel == 0 else rel_ci
        ax.errorbar(pos + shift, y, yerr=[y - lo, hi - y], fmt=marker, color=color, ecolor=color,
                    elinewidth=1.2, capsize=0, markersize=5.5, markeredgecolor="white", markeredgewidth=1.0,
                    label=name)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.set_xticks(pos)
    ax.set_xticklabels(ticks, fontsize=7.5)
    ax.set_xlim(-0.5, 3.5)
    hairline_grid(ax)
axes[0].set_ylabel("Change in survival probability\nper SD of GPR × 10 provisions (pp)")
axes[1].set_ylabel("Change in exit probability relative\nto the group's exit rate (%)")
axes[0].set_title("A. Absolute effect", loc="left", fontsize=9, color=INK)
axes[1].set_title("B. Relative to baseline exit risk", loc="left", fontsize=9, color=INK)
fig.supxlabel("Lagged link value (t − 1) and the group's one-year exit rate", fontsize=9, color=INK, y=-0.03)
handles, names = axes[0].get_legend_handles_labels()
fig.legend(handles, names, loc="upper center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.08))
save(fig, "fig_size_groups")
print("figures written to", FIGURES)
