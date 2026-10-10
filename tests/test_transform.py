from etl.transform import transform


def test_clean_sample_has_no_rejections(raw_df):
    res = transform(raw_df)
    assert res.stats["rows_clean"] == 20 and res.stats["rows_rejected"] == 0


def test_price_tiers(raw_df):
    clean = transform(raw_df).clean.set_index("id")
    assert clean.loc[19, "price_tier"] == "budget"      # 7.95
    assert clean.loc[3, "price_tier"] == "mid"          # 55.99
    assert clean.loc[14, "price_tier"] == "premium"     # 999.99


def test_derived_columns(raw_df):
    clean = transform(raw_df).clean
    assert clean["popularity_score"].gt(0).all()
    assert clean.loc[clean.id == 3, "is_highly_rated"].iloc[0]
    assert not clean.loc[clean.id == 4, "is_highly_rated"].iloc[0]


def test_dirty_rows_are_quarantined_with_reasons(dirty_df):
    res = transform(dirty_df)
    reasons = dict(zip(res.rejected["id"], res.rejected["reject_reason"]))
    assert "invalid_price" in reasons[101]
    assert {"missing_title", "missing_category", "invalid_price", "invalid_rating"} <= set(reasons[102].split(";"))
    assert "duplicate_id" in res.rejected["reject_reason"].values


def test_duplicate_keeps_latest_record(dirty_df):
    clean = transform(dirty_df).clean.set_index("id")
    assert clean.loc[103, "title"] == "Dup new"


def test_text_normalisation(dirty_df):
    clean = transform(dirty_df).clean.set_index("id")
    assert clean.loc[100, "title"] == "Good product"
    assert clean.loc[100, "category"] == "electronics"
    assert clean.loc[100, "price"] == 19.99      # string coerced to number
