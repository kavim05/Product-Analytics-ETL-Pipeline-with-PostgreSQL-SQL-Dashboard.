"""STAGE 2 - TRANSFORM: clean, validate, and enrich the raw product data.

Rules are explicit and every rejected row is *kept* with a reason
(quarantine pattern) instead of being silently dropped.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger("etl.transform")

# Price tiers (USD). Right-closed bins: (0, 25] budget, (25, 100] mid, (100, inf) premium
PRICE_BINS = [0, 25, 100, np.inf]
PRICE_LABELS = ["budget", "mid", "premium"]
HIGHLY_RATED_THRESHOLD = 4.0

CLEAN_COLUMNS = [
    "id", "title", "category", "price", "price_tier", "description",
    "description_length", "image_url", "rating_rate", "rating_count",
    "popularity_score", "is_highly_rated",
]


@dataclass
class TransformResult:
    clean: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict = field(default_factory=dict)


def _clean_text(series: pd.Series) -> pd.Series:
    """Trim and collapse repeated whitespace; keep missing values as NaN."""
    s = series.astype("object").where(series.notna(), None)
    return s.map(lambda v: " ".join(str(v).split()) if v is not None else None)


def _validate(df: pd.DataFrame) -> pd.Series:
    """Return a Series of rejection reasons ('' means the row is valid)."""
    checks = {
        "missing_id": df["id"].isna(),
        "missing_title": df["title"].isna() | (df["title"] == ""),
        "missing_category": df["category"].isna() | (df["category"] == ""),
        "invalid_price": df["price"].isna() | (df["price"] <= 0),
        "invalid_rating": df["rating_rate"].notna()
        & ~df["rating_rate"].between(0, 5),
        "invalid_rating_count": df["rating_count"].notna() & (df["rating_count"] < 0),
    }
    reasons = pd.Series("", index=df.index, dtype="object")
    for name, mask in checks.items():
        reasons = reasons.where(~mask, reasons + np.where(reasons == "", "", ";") + name)
    return reasons


def transform(raw: pd.DataFrame) -> TransformResult:
    """Run the full cleaning / validation / enrichment step."""
    rows_in = len(raw)
    log.info("Transforming %d raw rows", rows_in)
    df = raw.copy()

    # 1. Types ------------------------------------------------------------
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    for col in ("price", "rating_rate", "rating_count"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 2. Text normalisation -----------------------------------------------
    for col in ("title", "description", "category", "image"):
        df[col] = _clean_text(df[col]) if col in df else None
    df["category"] = df["category"].map(lambda v: v.lower() if isinstance(v, str) else v)

    # 3. Validation -> quarantine ------------------------------------------
    df["reject_reason"] = _validate(df)
    bad = df["reject_reason"] != ""

    # 4. De-duplication (keep the last occurrence of each id) ---------------
    dup = (~bad) & df.duplicated(subset="id", keep="last")
    df.loc[dup, "reject_reason"] = "duplicate_id"
    bad = df["reject_reason"] != ""

    rejected = df[bad].copy()
    good = df[~bad].copy()

    # 5. Enrichment ---------------------------------------------------------
    good["id"] = good["id"].astype("int64")
    good["price"] = good["price"].round(2)
    good["price_tier"] = pd.cut(
        good["price"], bins=PRICE_BINS, labels=PRICE_LABELS
    ).astype("object")
    good["description_length"] = good["description"].fillna("").str.len().astype("int64")
    good["image_url"] = good["image"]
    good["rating_count"] = good["rating_count"].astype("Int64")
    good["popularity_score"] = (
        good["rating_rate"] * np.log10(1 + good["rating_count"].astype("float64"))
    ).round(3)
    good["is_highly_rated"] = (good["rating_rate"] >= HIGHLY_RATED_THRESHOLD).fillna(False)

    clean = good[CLEAN_COLUMNS].sort_values("id").reset_index(drop=True)

    stats = {
        "rows_in": rows_in,
        "rows_clean": len(clean),
        "rows_rejected": len(rejected),
        "reject_reasons": rejected["reject_reason"].value_counts().to_dict(),
    }
    log.info(
        "Transform complete: %d clean, %d rejected %s",
        stats["rows_clean"], stats["rows_rejected"], stats["reject_reasons"] or "",
    )
    return TransformResult(clean=clean, rejected=rejected, stats=stats)
