"""Tests for verbringung_pricing using an in-memory SQLite engine.

The production code uses MSSQL-specific syntax for IN clauses via
bindparams(..., expanding=True) — here we replicate the same structure
with SQLite to avoid any real DB calls.
"""
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, text

from jtl2datev.core.verbringung_pricing import (
    PricingResult,
    _amzn_stem_candidates,
    extract_bware_stem,
    lookup_prices,
)

_LOOKUP_KWARGS = {
    "mapping_table": "pf_amazon_angebot_mapping",
    "artikel_table": "tArtikel",
    "beschreibung_table": "tArtikelBeschreibung",
}

_LOOKUP_KWARGS_T6 = {
    **_LOOKUP_KWARGS,
    "angebot_table": "pf_amazon_angebot",
}


@pytest.fixture(scope="module")
def sqlite_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE pf_amazon_angebot_mapping (
                cSellerSKU TEXT NOT NULL,
                kArtikel   INTEGER NOT NULL,
                kUser      INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE tArtikel (
                kArtikel  INTEGER PRIMARY KEY,
                cArtNr    TEXT NOT NULL,
                fEKNetto  REAL,
                fLetzterEK REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE tArtikelBeschreibung (
                kArtikel  INTEGER NOT NULL,
                kSprache  INTEGER NOT NULL,
                kPlattform INTEGER NOT NULL,
                cName     TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO tArtikel VALUES
                (1, 'A100',              3.50, 3.20),
                (2, 'B200',              0.0,  0.0),
                (3, 'B200-AP2',          5.00, 4.80),
                (4, 'C300',              2.10, 0.0),
                (5, 'DIRECT-ARTONLY',    7.00, 6.50),
                (6, 'MixedCase-SKU',     1.50, 1.40),
                (7, '2021451277-4',     10.00, 9.00),
                (8, 'ACA200120-AP-001', 20.00, 18.00),
                (9, 'TINY-EK',           0.05, 0.0)
        """))
        conn.execute(text("""
            INSERT INTO pf_amazon_angebot_mapping VALUES
                ('A100',              1, 1),
                ('B200',              2, 1),
                ('B200-AP2',          3, 1),
                ('B200-AP2',          3, 1),
                ('C300',              4, 1),
                ('C300-FBA',          4, 1),
                ('B200-AP2',          3, 1),
                ('Q51900100-AP6-002', 3, 1)
        """))
        conn.execute(text("""
            INSERT INTO tArtikelBeschreibung VALUES
                (1, 1, 1, 'Article A100'),
                (3, 1, 1, 'Bundle B200 AP2'),
                (4, 1, 1, 'Article C300'),
                (5, 1, 1, 'Direct Artikel Only'),
                (6, 1, 1, 'Mixed Case Article'),
                (7, 1, 1, 'Product 2021451277'),
                (8, 1, 1, 'Product ACA200120')
        """))
        conn.commit()
    return engine


def test_direct_match(sqlite_engine: Engine) -> None:
    results = lookup_prices(["A100"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["A100"]
    assert r.matched_jtl_artikel == "A100"
    assert r.matched_via == "direct"
    assert r.ek_netto == Decimal("3.5")
    assert r.description == "Article A100"


def test_direct_match_zero_ek_falls_back_to_letzter(sqlite_engine: Engine) -> None:
    """When fEKNetto == 0, _clean_decimal returns None and fLetzterEK is tried."""
    results = lookup_prices(["B200"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["B200"]
    assert r.matched_jtl_artikel == "B200"
    assert r.ek_netto is None  # both zero → None


def test_fba_suffix_stripped(sqlite_engine: Engine) -> None:
    results = lookup_prices(["C300-FBA"], sqlite_engine, **_LOOKUP_KWARGS)
    # Direct hit because C300-FBA is in the mapping table
    r = results["C300-FBA"]
    assert r.matched_jtl_artikel == "C300"
    assert r.matched_via == "direct"


def test_fba_strip_fallback(sqlite_engine: Engine) -> None:
    """SKU 'B200-AP2-FBA' is not in mapping; after stripping -FBA → 'B200-AP2' is."""
    results = lookup_prices(["B200-AP2-FBA"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["B200-AP2-FBA"]
    assert r.matched_jtl_artikel == "B200-AP2"
    assert r.matched_via == "fba"
    assert r.ek_netto == Decimal("5.0")


def test_sku_not_found(sqlite_engine: Engine) -> None:
    results = lookup_prices(["UNKNOWN-SKU-XYZ"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["UNKNOWN-SKU-XYZ"]
    assert r.matched_jtl_artikel is None
    assert r.matched_via is None
    assert r.ek_netto is None


def test_article_found_but_no_ek(sqlite_engine: Engine) -> None:
    """B200 maps to kArtikel=2 which has fEKNetto=0, fLetzterEK=0."""
    results = lookup_prices(["B200"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["B200"]
    assert r.matched_jtl_artikel == "B200"
    assert r.ek_netto is None


def test_bulk_lookup_returns_all_skus(sqlite_engine: Engine) -> None:
    skus = ["A100", "B200", "UNKNOWN", "C300-FBA"]
    results = lookup_prices(skus, sqlite_engine, **_LOOKUP_KWARGS)
    assert set(results.keys()) == set(skus)


def test_result_type(sqlite_engine: Engine) -> None:
    results = lookup_prices(["A100"], sqlite_engine, **_LOOKUP_KWARGS)
    assert isinstance(results["A100"], PricingResult)


# --- Tier 3: tArtikel-direct tests ---

def test_tartikel_direct_not_in_mapping(sqlite_engine: Engine) -> None:
    """DIRECT-ARTONLY exists in tArtikel but not in the mapping table → Tier 3."""
    results = lookup_prices(["DIRECT-ARTONLY"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["DIRECT-ARTONLY"]
    assert r.matched_jtl_artikel == "DIRECT-ARTONLY"
    assert r.matched_via == "tArtikel-direct"
    assert r.ek_netto == Decimal("7.0")
    assert r.description == "Direct Artikel Only"


def test_tartikel_direct_case_insensitive(sqlite_engine: Engine) -> None:
    """DIRECT-ARTONLY should match even if submitted lowercase."""
    results = lookup_prices(["direct-artonly"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["direct-artonly"]
    assert r.matched_jtl_artikel == "DIRECT-ARTONLY"
    assert r.matched_via == "tArtikel-direct"


def test_tartikel_direct_mixed_case(sqlite_engine: Engine) -> None:
    """MixedCase-SKU in tArtikel, matched case-insensitively."""
    results = lookup_prices(["mixedcase-sku"], sqlite_engine, **_LOOKUP_KWARGS)
    r = results["mixedcase-sku"]
    assert r.matched_jtl_artikel == "MixedCase-SKU"
    assert r.matched_via == "tArtikel-direct"


def test_tartikel_direct_does_not_shadow_mapping(sqlite_engine: Engine) -> None:
    """A100 is in both mapping and tArtikel — Tier 1 (direct) must win."""
    results = lookup_prices(["A100"], sqlite_engine, **_LOOKUP_KWARGS)
    assert results["A100"].matched_via == "direct"


def test_tartikel_direct_amzn_sku_skipped(sqlite_engine: Engine) -> None:
    """amzn.gr.* SKUs should not be tried against tArtikel (reserved for Tier 4)."""
    # amzn.gr.DIRECT-ARTONLY-HASHHASH-VG: if tArtikel-direct ran on it, it would
    # accidentally match the 'DIRECT-ARTONLY' stem. Tier 3 must skip amzn.gr. SKUs.
    results = lookup_prices(
        ["amzn.gr.DIRECT-ARTONLY-HASHHASH-VG"], sqlite_engine, **_LOOKUP_KWARGS
    )
    r = results["amzn.gr.DIRECT-ARTONLY-HASHHASH-VG"]
    # No mapping entry for the amzn stem 'DIRECT-ARTONLY-HASHHASH' either
    assert r.matched_via is None


# --- amzn stem candidate helper tests ---

def test_amzn_stem_candidates_basic() -> None:
    sku = "amzn.gr.336000080-AP3-VhWvvQDNpi75ttI-VG"
    candidates = _amzn_stem_candidates(sku)
    assert candidates[0] == "336000080-AP3-VhWvvQDNpi75ttI"
    assert candidates[1] == "336000080-AP3"
    assert candidates[2] == "336000080"


def test_amzn_stem_candidates_not_amzn() -> None:
    assert _amzn_stem_candidates("B200-AP2") == []
    assert _amzn_stem_candidates("") == []


def test_amzn_stem_candidates_short() -> None:
    """Only 2 parts after prefix → only 1 candidate."""
    sku = "amzn.gr.STEM-SUFFIX"
    candidates = _amzn_stem_candidates(sku)
    assert candidates == ["STEM"]


def test_amzn_stem_match_via_mapping(sqlite_engine: Engine) -> None:
    """amzn.gr.B200-AP2-<short-hash>-VG → hash too short for _BWARE_RE → Tier 4 (amzn).

    Uses a 9-char hash so the SKU does NOT match _BWARE_RE and falls into Tier 4
    iterative-candidate logic. The stem 'B200-AP2' is in the mapping table.
    """
    sku = "amzn.gr.B200-AP2-ABCDE1234-VG"  # 9-char hash → not B-Ware
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_jtl_artikel == "B200-AP2"
    assert r.matched_via == "amzn"
    assert r.ek_netto == Decimal("5.0")
    assert r.is_bware is False


# --- extract_bware_stem tests ---

def test_extract_bware_stem_basic() -> None:
    """Standard example from the spec."""
    assert extract_bware_stem("amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO") == "2021451277-4"


def test_extract_bware_stem_multi_dash_stem() -> None:
    """Stem contains multiple dashes."""
    assert extract_bware_stem("amzn.gr.ACA200120-AP-001-t9YSuJyv746C-LN") == "ACA200120-AP-001"


def test_extract_bware_stem_suffix_vg() -> None:
    assert extract_bware_stem("amzn.gr.Q51900100-AP6-002-vb3ygIAOCIv-VG") == "Q51900100-AP6-002"


def test_extract_bware_stem_suffix_ap3() -> None:
    assert extract_bware_stem("amzn.gr.336000080-AP3-VhWvvQDNpi75ttI-VG") == "336000080-AP3"


def test_extract_bware_stem_non_amzn_returns_none() -> None:
    assert extract_bware_stem("B200-AP2") is None
    assert extract_bware_stem("") is None
    assert extract_bware_stem("amzn.gr.tooshort-VG") is None


def test_extract_bware_stem_not_amzn_prefix() -> None:
    assert extract_bware_stem("DIRECT-ARTONLY") is None


# --- Tier 5: bware-stem via mapping table ---

def test_tier5_stem_match_via_mapping(sqlite_engine: Engine) -> None:
    """amzn.gr.Q51900100-AP6-002-<hash>-VG → stem in mapping → 10% EK, is_bware=True."""
    sku = "amzn.gr.Q51900100-AP6-002-vb3ygIAOCIv-VG"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-stem"
    assert r.is_bware is True
    assert r.matched_jtl_artikel == "B200-AP2"
    assert r.bware_pricing_basis == Decimal("5.0")
    # 10% of 5.0 = 0.5
    assert r.ek_netto == Decimal("0.5000")


# --- Tier 5: bware-stem via tArtikel direct ---

def test_tier5_stem_match_via_tartikel(sqlite_engine: Engine) -> None:
    """amzn.gr.2021451277-4-<hash>-PO → stem '2021451277-4' in tArtikel only → 10% EK."""
    sku = "amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-stem"
    assert r.is_bware is True
    assert r.matched_jtl_artikel == "2021451277-4"
    assert r.bware_pricing_basis == Decimal("10.0")
    # 10% of 10.0 = 1.0
    assert r.ek_netto == Decimal("1.0000")


def test_tier5_stem_match_via_tartikel_multidash(sqlite_engine: Engine) -> None:
    """Stem 'ACA200120-AP-001' exists in tArtikel → 10% of 20.00 = 2.00."""
    sku = "amzn.gr.ACA200120-AP-001-t9YSuJyv746C-LN"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-stem"
    assert r.is_bware is True
    assert r.bware_pricing_basis == Decimal("20.0")
    assert r.ek_netto == Decimal("2.0000")


# --- Tier 5: bware-fallback when stem not in DB ---

def test_tier5_bware_fallback_stem_not_found(sqlite_engine: Engine) -> None:
    """amzn.gr.* with stem absent from DB → fallback 0.10 EUR."""
    sku = "amzn.gr.UNKNOWN-SKU-9999-AbCdEfGhIjKl-VG"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-fallback"
    assert r.is_bware is True
    assert r.ek_netto == Decimal("0.10")
    assert r.matched_jtl_artikel is None


# --- Tier 5: 10% floor (EK so small that 10% < 0.01 EUR) ---

def test_tier5_bware_ek_floor(sqlite_engine: Engine) -> None:
    """10% of 0.05 = 0.005 → rounded to 0.01 (floor)."""
    sku = "amzn.gr.TINY-EK-AbCdEfGhIjKlMnOp-VG"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-stem"
    assert r.is_bware is True
    assert r.bware_pricing_basis == Decimal("0.05")
    assert r.ek_netto == Decimal("0.01")  # floor applied


# --- Tier 5: flat_10ct strategy ---

def test_tier5_flat_10ct_strategy_skips_lookup(sqlite_engine: Engine) -> None:
    """With bware_strategy='flat_10ct', all amzn.gr.* get 0.10 EUR, no stem lookup."""
    # 2021451277-4 exists in tArtikel and would give 1.00 EUR via ten_percent
    # but flat_10ct should always yield 0.10 EUR
    sku = "amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO"
    results = lookup_prices([sku], sqlite_engine, bware_strategy="flat_10ct", **_LOOKUP_KWARGS)
    r = results[sku]
    assert r.matched_via == "bware-fallback"
    assert r.is_bware is True
    assert r.ek_netto == Decimal("0.10")
    assert r.bware_pricing_basis is None


# --- is_bware flag is False for Tier 1-4 results ---

def test_is_bware_false_for_tier1(sqlite_engine: Engine) -> None:
    results = lookup_prices(["A100"], sqlite_engine, **_LOOKUP_KWARGS)
    assert results["A100"].is_bware is False


def test_is_bware_false_for_tier2_fba(sqlite_engine: Engine) -> None:
    results = lookup_prices(["B200-AP2-FBA"], sqlite_engine, **_LOOKUP_KWARGS)
    assert results["B200-AP2-FBA"].is_bware is False


def test_is_bware_false_for_tier3_tartikel(sqlite_engine: Engine) -> None:
    results = lookup_prices(["DIRECT-ARTONLY"], sqlite_engine, **_LOOKUP_KWARGS)
    assert results["DIRECT-ARTONLY"].is_bware is False


def test_is_bware_false_for_tier4_amzn(sqlite_engine: Engine) -> None:
    # 9-char hash → does not match _BWARE_RE → routed to Tier 4, not Tier 5
    sku = "amzn.gr.B200-AP2-ABCDE1234-VG"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    assert results[sku].is_bware is False


def test_is_bware_true_for_tier5_stem(sqlite_engine: Engine) -> None:
    sku = "amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    assert results[sku].is_bware is True


def test_is_bware_true_for_tier5_fallback(sqlite_engine: Engine) -> None:
    sku = "amzn.gr.NOPE-NOPE-NOPE-AbCdEfGhIjKl-VG"
    results = lookup_prices([sku], sqlite_engine, **_LOOKUP_KWARGS)
    assert results[sku].is_bware is True


# ---------------------------------------------------------------------------
# Tier 6: ASIN-based lookup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sqlite_engine_t6() -> Engine:
    """Engine with pf_amazon_angebot + ASIN-capable tArtikel rows."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE pf_amazon_angebot_mapping (
                cSellerSKU TEXT NOT NULL,
                kArtikel   INTEGER NOT NULL,
                kUser      INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE tArtikel (
                kArtikel   INTEGER PRIMARY KEY,
                cArtNr     TEXT NOT NULL,
                cASIN      TEXT,
                fEKNetto   REAL,
                fLetzterEK REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE tArtikelBeschreibung (
                kArtikel  INTEGER NOT NULL,
                kSprache  INTEGER NOT NULL,
                kPlattform INTEGER NOT NULL,
                cName     TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE pf_amazon_angebot (
                cSellerSKU TEXT NOT NULL,
                kUser      INTEGER NOT NULL DEFAULT 1,
                cASIN1     TEXT,
                cASIN2     TEXT,
                cASIN3     TEXT
            )
        """))
        # tArtikel: kArtikel 10 has direct cASIN, 11 only via pf_amazon_angebot
        conn.execute(text("""
            INSERT INTO tArtikel VALUES
                (10, 'SKU-WITH-ASIN',    'B0001DIRECT', 8.00, 7.50),
                (11, 'SKU-VIA-ANGEBOT',  NULL,          6.00, 5.50),
                (12, 'SKU-MFN-MAPPING',  NULL,          4.00, 3.80),
                (13, 'SKU-MULTI-MATCH',  NULL,          3.00, 2.80)
        """))
        conn.execute(text("""
            INSERT INTO pf_amazon_angebot_mapping VALUES
                ('SKU-VIA-ANGEBOT',  11, 1),
                ('SKU-VIA-ANGEBOT2', 11, 1),
                ('SKU-MFN-MAPPING',  12, 1)
        """))
        conn.execute(text("""
            INSERT INTO tArtikelBeschreibung VALUES
                (10, 1, 1, 'Direct ASIN Article'),
                (11, 1, 1, 'Via Angebot Article'),
                (12, 1, 1, 'MFN Mapping Article'),
                (13, 1, 1, 'Multi Match Article')
        """))
        # pf_amazon_angebot: maps ASINs to current seller SKUs
        conn.execute(text("""
            INSERT INTO pf_amazon_angebot (cSellerSKU, cASIN1, cASIN2, cASIN3) VALUES
                ('SKU-VIA-ANGEBOT',  'B0002ANGEBOT', '', ''),
                ('SKU-VIA-ANGEBOT2', 'B0002ANGEBOT', '', ''),
                ('SKU-MFN-MAPPING',  'B0003MFN',     '', ''),
                ('SKU-MULTI-MATCH',  'B0004MULTI',   '', ''),
                ('SKU-MULTI-MATCH2', 'B0004MULTI',   '', '')
        """))
        conn.commit()
    return engine


def test_tier6_asin_none_skips_lookup(sqlite_engine_t6: Engine) -> None:
    """asin_by_sku=None → Tier 6 skipped, old SKU stays unresolved."""
    results = lookup_prices(
        ["OLD-SKU-MISSING"],
        sqlite_engine_t6,
        asin_by_sku=None,
        **_LOOKUP_KWARGS_T6,
    )
    r = results["OLD-SKU-MISSING"]
    assert r.matched_via is None
    assert r.ek_netto is None


def test_tier6_tartikel_direct_asin(sqlite_engine_t6: Engine) -> None:
    """Old SKU with ASIN B0001DIRECT → tArtikel.cASIN hit → matched_via='asin-tartikel'."""
    results = lookup_prices(
        ["336000080-AP1"],
        sqlite_engine_t6,
        asin_by_sku={"336000080-AP1": "B0001DIRECT"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["336000080-AP1"]
    assert r.matched_via == "asin-tartikel"
    assert r.matched_jtl_artikel == "SKU-WITH-ASIN"
    assert r.ek_netto == Decimal("8.0")
    assert r.description == "Direct ASIN Article"
    assert r.is_bware is False


def test_tier6_angebot_via_mapping(sqlite_engine_t6: Engine) -> None:
    """ASIN B0002ANGEBOT → pf_amazon_angebot → SKU-VIA-ANGEBOT → mapping hit."""
    results = lookup_prices(
        ["OLD-SKU-2"],
        sqlite_engine_t6,
        asin_by_sku={"OLD-SKU-2": "B0002ANGEBOT"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["OLD-SKU-2"]
    assert r.matched_via == "asin-angebot"
    assert r.matched_jtl_artikel == "SKU-VIA-ANGEBOT"
    assert r.ek_netto == Decimal("6.0")


def test_tier6_angebot_fallback_tartikel(sqlite_engine_t6: Engine) -> None:
    """ASIN B0003MFN → pf_amazon_angebot → SKU-MFN-MAPPING → mapping then tArtikel."""
    results = lookup_prices(
        ["OLD-MFN"],
        sqlite_engine_t6,
        asin_by_sku={"OLD-MFN": "B0003MFN"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["OLD-MFN"]
    assert r.matched_via == "asin-angebot"
    assert r.matched_jtl_artikel == "SKU-MFN-MAPPING"
    assert r.ek_netto == Decimal("4.0")


def test_tier6_tartikel_preferred_over_angebot(sqlite_engine_t6: Engine) -> None:
    """When tArtikel.cASIN matches, it wins before pf_amazon_angebot is tried."""
    # B0001DIRECT is in tArtikel.cASIN — pf_amazon_angebot has no entry for it
    # → asin-tartikel is the result (not asin-angebot)
    results = lookup_prices(
        ["OLD-SKU-PREF"],
        sqlite_engine_t6,
        asin_by_sku={"OLD-SKU-PREF": "B0001DIRECT"},
        **_LOOKUP_KWARGS_T6,
    )
    assert results["OLD-SKU-PREF"].matched_via == "asin-tartikel"


def test_tier6_asin_not_in_db_returns_none(sqlite_engine_t6: Engine) -> None:
    """ASIN exists in asin_by_sku but not in tArtikel or pf_amazon_angebot → unresolved."""
    results = lookup_prices(
        ["OLD-SKU-NOASIN"],
        sqlite_engine_t6,
        asin_by_sku={"OLD-SKU-NOASIN": "B9999UNKNOWN"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["OLD-SKU-NOASIN"]
    assert r.matched_via is None
    assert r.ek_netto is None


def test_tier6_multiple_asins_via_angebot_first_match_wins(sqlite_engine_t6: Engine) -> None:
    """ASIN B0004MULTI has 2 seller SKUs; first with a mapping entry wins."""
    results = lookup_prices(
        ["OLD-MULTI"],
        sqlite_engine_t6,
        asin_by_sku={"OLD-MULTI": "B0004MULTI"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["OLD-MULTI"]
    # SKU-MULTI-MATCH and SKU-MULTI-MATCH2 are in pf_amazon_angebot for B0004MULTI.
    # Neither is in pf_amazon_angebot_mapping, but SKU-MULTI-MATCH is in tArtikel → 6b-ii
    assert r.matched_via == "asin-angebot"
    assert r.matched_jtl_artikel == "SKU-MULTI-MATCH"


def test_tier6_bware_sku_gets_asin_hit_before_fallback(sqlite_engine_t6: Engine) -> None:
    """amzn.gr.* SKU with unknown stem but known ASIN → Tier 6 before bware-fallback.

    The SKU matches _BWARE_RE (B-Ware pattern) so it goes through Tier 5,
    but its stem is not in the DB → would normally fall through to bware-fallback.
    With asin_by_sku provided, Tier 6 kicks in first and finds the article.
    is_bware is True because the SKU is still a B-Ware SKU.
    """
    bware_sku = "amzn.gr.UNKNOWN-STEM-AbCdEfGhIjKlMnOp-VG"
    results = lookup_prices(
        [bware_sku],
        sqlite_engine_t6,
        bware_strategy="ten_percent",
        asin_by_sku={bware_sku: "B0001DIRECT"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results[bware_sku]
    assert r.matched_via == "asin-tartikel"
    assert r.is_bware is True
    assert r.matched_jtl_artikel == "SKU-WITH-ASIN"


def test_tier6_flat_10ct_skips_tier6_for_bware(sqlite_engine_t6: Engine) -> None:
    """With flat_10ct strategy, amzn.gr.* SKUs skip Tier 6 → get bware-fallback."""
    bware_sku = "amzn.gr.UNKNOWN-STEM-AbCdEfGhIjKlMnOp-VG"
    results = lookup_prices(
        [bware_sku],
        sqlite_engine_t6,
        bware_strategy="flat_10ct",
        asin_by_sku={bware_sku: "B0001DIRECT"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results[bware_sku]
    assert r.matched_via == "bware-fallback"
    assert r.ek_netto == Decimal("0.10")


def test_tier6_flat_10ct_still_applies_tier6_for_non_bware(sqlite_engine_t6: Engine) -> None:
    """flat_10ct skips Tier 6 only for amzn.gr.* — normal SKUs still get Tier 6."""
    results = lookup_prices(
        ["NORMAL-OLD-SKU"],
        sqlite_engine_t6,
        bware_strategy="flat_10ct",
        asin_by_sku={"NORMAL-OLD-SKU": "B0001DIRECT"},
        **_LOOKUP_KWARGS_T6,
    )
    r = results["NORMAL-OLD-SKU"]
    assert r.matched_via == "asin-tartikel"
    assert r.ek_netto == Decimal("8.0")
