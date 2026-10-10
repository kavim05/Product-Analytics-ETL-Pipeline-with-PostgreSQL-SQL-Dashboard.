"""SQL ANALYTICS INTERFACE: run the analytical queries and build the charts."""
from __future__ import annotations

import logging
import re
import string
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.ticker  # noqa: F401
import pandas as pd
from sqlalchemy.engine import Engine

from etl.config import settings

log = logging.getLogger("etl.analytics")

# ---- style ------------------------------------------------------------------
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
TIER_COLORS = {"budget": "#54A24B", "mid": "#4C78A8", "premium": "#F58518"}
plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.labelsize": 10,
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.grid": True,
    "grid.alpha": 0.25, "axes.axisbelow": True,
})


# ---- query runner -------------------------------------------------------------
def load_queries(path: Path | None = None) -> dict[str, str]:
    """Parse sql/analytics_queries.sql into {name: sql}."""
    path = path or settings.sql_dir / "analytics_queries.sql"
    text = path.read_text(encoding="utf-8")
    queries: dict[str, str] = {}
    for block in re.split(r"^-- name:\s*", text, flags=re.MULTILINE)[1:]:
        name, _, body = block.partition("\n")
        sql_lines = [ln for ln in body.splitlines() if not ln.strip().startswith("--")]
        queries[name.strip()] = "\n".join(sql_lines).strip().rstrip(";")
    return queries


def _numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Decimal columns (Postgres NUMERIC) to float for plotting."""
    for col in df.columns:
        if df[col].dtype == object and df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def run_queries(engine: Engine) -> dict[str, pd.DataFrame]:
    results = {}
    for name, sql in load_queries().items():
        results[name] = _numeric(pd.read_sql_query(sql, engine))
        log.info("query %-28s -> %d rows", name, len(results[name]))
    return results


def export_reports(results: dict[str, pd.DataFrame], directory: Path | None = None) -> None:
    directory = directory or settings.reports_dir
    directory.mkdir(parents=True, exist_ok=True)
    for name, df in results.items():
        df.to_csv(directory / f"{name}.csv", index=False)
    log.info("CSV reports written to %s", directory)


# ---- charts ---------------------------------------------------------------------
def _pretty(label: str) -> str:
    return string.capwords(label).replace("Jewelery", "Jewelry")


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def _bar_avg_price(ax, df):
    d = df.sort_values("avg_price")
    bars = ax.barh([_pretty(c) for c in d["category"]], d["avg_price"], color=PALETTE[0])
    ax.bar_label(bars, labels=[f"${v:,.2f}" for v in d["avg_price"]], padding=4, fontsize=9)
    ax.set_xlabel("Average price (USD)")
    ax.set_title("Average Price by Category")
    ax.set_xlim(0, d["avg_price"].max() * 1.18)
    ax.grid(axis="y", visible=False)


def _bar_rating_dist(ax, df):
    ax.bar(df["rating_bucket"].astype(float), df["products"], width=0.4, color=PALETTE[2])
    for x, y in zip(df["rating_bucket"].astype(float), df["products"]):
        ax.text(x, y + 0.05, str(int(y)), ha="center", fontsize=9)
    ax.set_xlabel("Rating (rounded to nearest 0.5 star)")
    ax.set_ylabel("Products")
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_ylim(0, df["products"].max() + 0.8)
    ax.set_title("Rating Distribution")
    ax.set_xticks(df["rating_bucket"].astype(float))
    ax.grid(axis="x", visible=False)


def _bar_top_categories(ax, df):
    d = df.sort_values("total_reviews")
    bars = ax.barh([_pretty(c) for c in d["category"]], d["total_reviews"], color=PALETTE[1])
    labels = [f"{int(r):,}  (avg {a:.2f}★)" for r, a in zip(d["total_reviews"], d["avg_rating"])]
    ax.bar_label(bars, labels=labels, padding=4, fontsize=9)
    ax.set_xlabel("Total reviews")
    ax.set_title("Top Categories by Customer Engagement")
    ax.set_xlim(0, d["total_reviews"].max() * 1.35)
    ax.grid(axis="y", visible=False)


def _donut_tiers(ax, df):
    colors = [TIER_COLORS.get(t, "#999") for t in df["price_tier"]]
    wedges, _, autotexts = ax.pie(
        df["products"], colors=colors, startangle=90, counterclock=False,
        autopct=lambda p: f"{p:.0f}%", pctdistance=0.78,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
        textprops=dict(color="white", fontweight="bold", fontsize=10),
    )
    ax.legend(wedges, [f"{t.title()} ({n})" for t, n in zip(df["price_tier"], df["products"])],
              loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3,
              frameon=False, fontsize=9, handlelength=1, columnspacing=1.2)
    ax.set_title("Catalogue by Price Tier")
    ax.grid(False)


def _scatter(ax, df):
    for color, (cat, g) in zip(PALETTE, df.groupby("category")):
        ax.scatter(g["price"], g["rating_rate"], s=g["rating_count"] / 3 + 20,
                   color=color, alpha=0.75, edgecolor="white", linewidth=0.8,
                   label=_pretty(cat))
    ax.set_xscale("log")
    ax.set_xlabel("Price (USD, log scale)")
    ax.set_ylabel("Rating")
    ax.set_title("Price vs Rating (bubble size = review count)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")


def make_charts(results: dict[str, pd.DataFrame], directory: Path | None = None) -> list[Path]:
    """Create 5 individual charts + 1 combined dashboard. Returns the file paths."""
    directory = directory or settings.charts_dir
    specs = [
        ("avg_price_by_category.png", _bar_avg_price, "avg_price_by_category", (7, 4)),
        ("rating_distribution.png", _bar_rating_dist, "rating_distribution", (7, 4)),
        ("top_categories.png", _bar_top_categories, "top_categories", (7.5, 4)),
        ("price_tier_distribution.png", _donut_tiers, "price_tier_summary", (6.5, 4)),
        ("price_vs_rating.png", _scatter, "scatter_price_rating", (7.5, 4.6)),
    ]
    paths = []
    for filename, fn, key, size in specs:
        fig, ax = plt.subplots(figsize=size)
        fn(ax, results[key])
        paths.append(_save(fig, directory / filename))

    # ---- combined dashboard --------------------------------------------------
    kpi = results["kpi_overview"].iloc[0]
    fig = plt.figure(figsize=(16, 11))
    fig.suptitle("E-commerce Product Analytics Dashboard", fontsize=22, fontweight="bold", y=0.975)
    fig.text(0.5, 0.935, "Fake Store API  \u2192  pandas  \u2192  PostgreSQL  \u2192  SQL analytics",
             ha="center", fontsize=11, color="#5B6B7F")

    cards = [
        ("Products", f"{int(kpi.total_products)}"),
        ("Categories", f"{int(kpi.categories)}"),
        ("Avg Price", f"${kpi.avg_price:,.2f}"),
        ("Avg Rating", f"{kpi.avg_rating:.2f} \u2605"),
        ("Total Reviews", f"{int(kpi.total_reviews):,}"),
        ("Highly Rated (\u22654.0)", f"{int(kpi.highly_rated_products)}"),
    ]
    gs_kpi = fig.add_gridspec(1, 6, left=0.06, right=0.97, top=0.89, bottom=0.79, wspace=0.12)
    for i, (label, value) in enumerate(cards):
        ax = fig.add_subplot(gs_kpi[0, i])
        ax.set_facecolor("#F3F6FA"); ax.grid(False)
        for sp in ax.spines.values():
            sp.set_visible(True); sp.set_color("#D0D7E2")
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.5, 0.60, value, ha="center", va="center", fontsize=21, fontweight="bold", color="#1F3A5F")
        ax.text(0.5, 0.17, label, ha="center", va="center", fontsize=10, color="#5B6B7F")

    gs_mid = fig.add_gridspec(1, 2, left=0.14, right=0.97, top=0.71, bottom=0.45, wspace=0.55)
    _bar_avg_price(fig.add_subplot(gs_mid[0, 0]), results["avg_price_by_category"])
    _bar_top_categories(fig.add_subplot(gs_mid[0, 1]), results["top_categories"])

    gs_bot = fig.add_gridspec(1, 3, left=0.06, right=0.97, top=0.34, bottom=0.06, wspace=0.32)
    _bar_rating_dist(fig.add_subplot(gs_bot[0, 0]), results["rating_distribution"])
    _donut_tiers(fig.add_subplot(gs_bot[0, 1]), results["price_tier_summary"])
    ax_sc = fig.add_subplot(gs_bot[0, 2])
    _scatter(ax_sc, results["scatter_price_rating"])
    ax_sc.set_title("Price vs Rating (size = reviews)")
    paths.append(_save(fig, directory / "dashboard.png"))

    log.info("Generated %d charts in %s", len(paths), directory)
    return paths
