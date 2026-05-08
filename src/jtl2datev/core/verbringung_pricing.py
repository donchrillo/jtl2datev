"""EK-Preis-Lookup für Amazon-SKUs via JTL-Datenbank.

Lookup-Strategie (in Reihenfolge):
1. Direct:       pf_amazon_angebot_mapping.cSellerSKU == seller_sku
2. FBA/MFN:      strip trailing -FBA / -MFN suffix, retry platform-table
3. tArtikel:     direct match on tArtikel.cArtNr (case-insensitive)
4. amzn-stem:    amzn.gr.<STEM>-... → iterative stem candidates (1-3 trailing
                 dash-segments removed), match against pf_amazon_angebot_mapping
5. bware-stem:   amzn.gr.* with structured regex → exact stem extraction,
                 match against pf_amazon_angebot_mapping (5a) then tArtikel (5b),
                 EK = 10% of found fEKNetto (floor 0.01 EUR).
6. ASIN-Lookup:  for SKUs with known ASIN (from movement report):
                 6a. tArtikel.cASIN = asin → matched_via="asin-tartikel"
                 6b. pf_amazon_angebot.cASIN1 = asin → cSellerSKU →
                     pf_amazon_angebot_mapping or tArtikel → matched_via="asin-angebot"
                 Skipped if asin_by_sku=None or bware_strategy="flat_10ct" for amzn.gr.* SKUs.
   bware-fallback: amzn.gr.* with no match → flat 0.10 EUR.

Alle Strategien lesen nur aus dbo.pf_amazon_angebot_mapping + dbo.tArtikel
+ dbo.tArtikelBeschreibung + dbo.pf_amazon_angebot — keine Schreibzugriffe.

Schema-Findings (2026-05-08):
- pf_amazon_angebot_fba: hat keine cASIN-Spalte → nicht für ASIN-Lookup verwendbar
- pf_amazon_angebot: cASIN1/cASIN2/cASIN3 (nur cASIN1 wird praktisch befüllt)
- tArtikel: hat direkte cASIN-Spalte (beste Quelle für ASIN→kArtikel)
"""
import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel
from sqlalchemy import Engine, bindparam, text

logger = logging.getLogger(__name__)

# FBA/fba/mfn suffix: -FBA, -fba, -mfn, -MFN
_FBA_RE = re.compile(r"^(.+?)-(?:[Ff][Bb][Aa]|[Mm][Ff][Nn])$")

# amzn.gr. prefix marker
_AMZN_PREFIX = "amzn.gr."

# B-Ware pattern: amzn.gr.<STEM>-<HASH(10-20 alnum)>-<SUFFIX(2 alnum uppercase)>
# The stem itself may contain dashes (e.g. ACA200120-AP-001).
_BWARE_RE = re.compile(r"^amzn\.gr\.(.+)-([A-Za-z0-9]{10,20})-([A-Z0-9]{2})$")

_BWARE_FLOOR = Decimal("0.01")
_BWARE_FALLBACK_PRICE = Decimal("0.10")
_BWARE_PERCENTAGE = Decimal("0.10")

# Table/schema prefix is injected at call time so the same query works
# against both MSSQL (dbo. prefix) and SQLite (no prefix, used in tests).
_SQL_MAPPING_TEMPLATE = """
SELECT
    m.cSellerSKU,
    a.cArtNr,
    a.fEKNetto,
    a.fLetzterEK,
    b.cName
FROM {mapping} m
JOIN {artikel} a ON a.kArtikel = m.kArtikel
LEFT JOIN {beschreibung} b
    ON b.kArtikel = a.kArtikel AND b.kSprache = 1 AND b.kPlattform = 1
WHERE m.cSellerSKU IN :skus
"""

_SQL_ARTIKEL_DIRECT_TEMPLATE = """
SELECT
    a.cArtNr,
    a.fEKNetto,
    a.fLetzterEK,
    b.cName
FROM {artikel} a
LEFT JOIN {beschreibung} b
    ON b.kArtikel = a.kArtikel AND b.kSprache = 1 AND b.kPlattform = 1
WHERE LOWER(a.cArtNr) IN :skus
"""

# Tier 6a: ASIN → tArtikel.cASIN (batch)
_SQL_ASIN_TARTIKEL_TEMPLATE = """
SELECT
    a.cASIN,
    a.cArtNr,
    a.fEKNetto,
    a.fLetzterEK,
    b.cName
FROM {artikel} a
LEFT JOIN {beschreibung} b
    ON b.kArtikel = a.kArtikel AND b.kSprache = 1 AND b.kPlattform = 1
WHERE a.cASIN IN :asins
"""

# Tier 6b step 1: ASIN → pf_amazon_angebot.cASIN1 → cSellerSKU candidates (batch)
_SQL_ASIN_ANGEBOT_TEMPLATE = """
SELECT DISTINCT
    cASIN1 AS cASIN,
    cSellerSKU
FROM {angebot}
WHERE cASIN1 IN :asins
  AND cSellerSKU IS NOT NULL
  AND cSellerSKU <> ''
"""


class PricingResult(BaseModel):
    seller_sku: str
    matched_jtl_artikel: str | None
    matched_via: str | None  # "direct"|"fba"|"tArtikel-direct"|"amzn"|"bware-stem"|"bware-fallback"|"asin-tartikel"|"asin-angebot"|None
    ek_netto: Decimal | None
    description: str | None
    is_bware: bool = False
    bware_pricing_basis: Decimal | None = None  # full EK of the stem article (audit)


def _strip_fba(sku: str) -> str | None:
    m = _FBA_RE.match(sku)
    return m.group(1) if m else None


def _amzn_stem_candidates(sku: str) -> list[str]:
    """Generate stem candidates for an amzn.gr.* SKU.

    Amazon wraps original SKUs as: amzn.gr.<OriginalSKU>-<HASH>-<2-CHAR-MARKETPLACE>
    The original SKU and hash both may contain dashes, making exact parsing
    impossible without knowing the original. We generate candidates by
    progressively removing 1, 2 or 3 trailing dash-segments.
    """
    if not sku.startswith(_AMZN_PREFIX):
        return []
    rest = sku[len(_AMZN_PREFIX):]
    parts = rest.split("-")
    candidates: list[str] = []
    for n in range(1, min(4, len(parts))):
        stem = "-".join(parts[:-n])
        if stem:
            candidates.append(stem)
    return candidates


def extract_bware_stem(sku: str) -> str | None:
    """Returns the inner stem of an amzn.gr.* B-Ware SKU.

    'amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO' → '2021451277-4'

    Returns None if the SKU does not match the B-Ware pattern.
    """
    if not sku.startswith(_AMZN_PREFIX):
        return None
    m = _BWARE_RE.match(sku)
    if m:
        return m.group(1)
    return None


def _bware_ek(full_ek: Decimal) -> Decimal:
    """Compute B-Ware EK as 10% of full EK, with floor of 0.01 EUR."""
    raw = (full_ek * _BWARE_PERCENTAGE).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return max(raw, _BWARE_FLOOR)


def _clean_decimal(val: object) -> Decimal | None:
    if val is None:
        return None
    d = Decimal(str(val))
    return d if d != Decimal("0") else None


def lookup_prices(
    skus: list[str],
    engine: Engine,
    *,
    mapping_table: str = "dbo.pf_amazon_angebot_mapping",
    artikel_table: str = "dbo.tArtikel",
    beschreibung_table: str = "dbo.tArtikelBeschreibung",
    angebot_table: str = "dbo.pf_amazon_angebot",
    bware_strategy: str = "ten_percent",
    asin_by_sku: dict[str, str] | None = None,
) -> dict[str, PricingResult]:
    """Return PricingResult for each SKU in *skus*.

    Unknown SKUs get matched_jtl_artikel=None, ek_netto=None.
    Uses a single round-trip per lookup tier to stay efficient.

    bware_strategy:
      "ten_percent" (default) — Tier 5: stem lookup → 10% EK, fallback 0.10 EUR.
                                 Tier 6 (ASIN-lookup) attempted before B-Ware-fallback.
      "flat_10ct"             — Tier 5: skip stem lookup, always 0.10 EUR for amzn.gr.*.
                                 Tier 6 skipped for amzn.gr.* SKUs.

    asin_by_sku: optional dict {seller_sku: asin}. When provided, unresolved SKUs
      with a known ASIN are tried via Tier 6 (tArtikel.cASIN then pf_amazon_angebot).
      When None (default), Tier 6 is skipped entirely (backward-compatible).
    """
    sql_mapping = text(
        _SQL_MAPPING_TEMPLATE.format(
            mapping=mapping_table,
            artikel=artikel_table,
            beschreibung=beschreibung_table,
        )
    ).bindparams(bindparam("skus", expanding=True))

    sql_artikel_direct = text(
        _SQL_ARTIKEL_DIRECT_TEMPLATE.format(
            artikel=artikel_table,
            beschreibung=beschreibung_table,
        )
    ).bindparams(bindparam("skus", expanding=True))

    sql_asin_tartikel = text(
        _SQL_ASIN_TARTIKEL_TEMPLATE.format(
            artikel=artikel_table,
            beschreibung=beschreibung_table,
        )
    ).bindparams(bindparam("asins", expanding=True))

    sql_asin_angebot = text(
        _SQL_ASIN_ANGEBOT_TEMPLATE.format(
            angebot=angebot_table,
        )
    ).bindparams(bindparam("asins", expanding=True))

    results: dict[str, PricingResult] = {}
    remaining: set[str] = set(skus)

    def _fetch_mapping_tier(probe_map: dict[str, str], tier: str) -> None:
        """probe_map: {probe_key -> original_sku}. Fetches via mapping table."""
        nonlocal remaining
        if not probe_map:
            return
        unique_probes = list(set(probe_map.keys()))
        with engine.connect() as conn:
            result = conn.execute(sql_mapping, {"skus": unique_probes})
            for row in result.mappings():
                probe = row["cSellerSKU"]
                orig_sku = probe_map.get(probe)
                if orig_sku is None or orig_sku not in remaining:
                    continue
                ek_raw = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                results[orig_sku] = PricingResult(
                    seller_sku=orig_sku,
                    matched_jtl_artikel=row["cArtNr"],
                    matched_via=tier,
                    ek_netto=ek_raw,
                    description=row["cName"] or None,
                )
                remaining.discard(orig_sku)

    def _fetch_artikel_direct(orig_skus: list[str]) -> None:
        """Case-insensitive direct match on tArtikel.cArtNr."""
        nonlocal remaining
        if not orig_skus:
            return
        lower_to_orig = {s.lower(): s for s in orig_skus}
        with engine.connect() as conn:
            result = conn.execute(sql_artikel_direct, {"skus": list(lower_to_orig.keys())})
            for row in result.mappings():
                orig_sku = lower_to_orig.get(row["cArtNr"].lower())
                if orig_sku is None or orig_sku not in remaining:
                    continue
                ek_raw = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                results[orig_sku] = PricingResult(
                    seller_sku=orig_sku,
                    matched_jtl_artikel=row["cArtNr"],
                    matched_via="tArtikel-direct",
                    ek_netto=ek_raw,
                    description=row["cName"] or None,
                )
                remaining.discard(orig_sku)

    def _run_tier6(is_bware: bool) -> None:
        """Tier 6: ASIN-based lookup for still-unresolved SKUs with known ASIN.

        is_bware=True  → called inside the bware branch for amzn.gr.* SKUs.
        is_bware=False → called after bware branch for non-amzn.gr.* SKUs.

        Skipped entirely when asin_by_sku is None.
        """
        nonlocal remaining
        if asin_by_sku is None:
            return

        # Select candidate SKUs for this call
        if is_bware:
            candidates = [s for s in remaining if s.startswith(_AMZN_PREFIX)]
        else:
            candidates = [s for s in remaining if not s.startswith(_AMZN_PREFIX)]

        if not candidates:
            return

        # Build asin → [skus] map (only for candidates with known ASIN)
        asin_to_skus: dict[str, list[str]] = {}
        for sku in candidates:
            asin = asin_by_sku.get(sku)
            if asin:
                asin_to_skus.setdefault(asin, []).append(sku)

        if not asin_to_skus:
            return

        unique_asins = list(asin_to_skus.keys())

        # 6a: tArtikel.cASIN → direct EK (best source, no extra join needed)
        with engine.connect() as conn:
            result = conn.execute(sql_asin_tartikel, {"asins": unique_asins})
            for row in result.mappings():
                asin = row["cASIN"]
                for orig_sku in list(asin_to_skus.get(asin, [])):
                    if orig_sku not in remaining:
                        continue
                    ek_raw = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                    results[orig_sku] = PricingResult(
                        seller_sku=orig_sku,
                        matched_jtl_artikel=row["cArtNr"],
                        matched_via="asin-tartikel",
                        ek_netto=ek_raw,
                        description=row["cName"] or None,
                        is_bware=is_bware,
                    )
                    remaining.discard(orig_sku)

        # 6b: pf_amazon_angebot.cASIN1 → cSellerSKU → mapping or tArtikel
        still_candidates = [s for s in candidates if s in remaining]
        if not still_candidates:
            return

        still_asins = list({asin_by_sku[s] for s in still_candidates if asin_by_sku.get(s)})
        if not still_asins:
            return

        # Collect seller SKUs per ASIN from pf_amazon_angebot
        asin_to_seller_skus: dict[str, list[str]] = {}
        with engine.connect() as conn:
            result = conn.execute(sql_asin_angebot, {"asins": still_asins})
            for row in result.mappings():
                asin = row["cASIN"]
                seller_sku = row["cSellerSKU"]
                asin_to_seller_skus.setdefault(asin, []).append(seller_sku)

        if not asin_to_seller_skus:
            return

        # For each original SKU still unresolved, try each candidate seller SKU
        # via mapping table (Tier-1 style) then via tArtikel direct (Tier-3 style)
        # Build probe_map: seller_sku_candidate → original_sku (one-to-one, first wins)
        probe_to_orig: dict[str, str] = {}
        for orig_sku in still_candidates:
            if orig_sku not in remaining:
                continue
            asin = asin_by_sku.get(orig_sku)
            if not asin:
                continue
            for seller_sku_candidate in asin_to_seller_skus.get(asin, []):
                if seller_sku_candidate not in probe_to_orig:
                    probe_to_orig[seller_sku_candidate] = orig_sku

        if not probe_to_orig:
            return

        unique_probes = list(probe_to_orig.keys())

        # 6b-i: mapping table lookup
        with engine.connect() as conn:
            result = conn.execute(sql_mapping, {"skus": unique_probes})
            for row in result.mappings():
                probe = row["cSellerSKU"]
                orig_sku_opt: str | None = probe_to_orig.get(probe)
                if orig_sku_opt is None or orig_sku_opt not in remaining:
                    continue
                orig_sku_i = orig_sku_opt
                ek_raw = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                results[orig_sku_i] = PricingResult(
                    seller_sku=orig_sku_i,
                    matched_jtl_artikel=row["cArtNr"],
                    matched_via="asin-angebot",
                    ek_netto=ek_raw,
                    description=row["cName"] or None,
                    is_bware=is_bware,
                )
                remaining.discard(orig_sku_i)

        # 6b-ii: tArtikel direct for remaining
        still_probes_lower = {p.lower(): p for p in unique_probes if probe_to_orig.get(p) in remaining}
        if still_probes_lower:
            with engine.connect() as conn:
                result = conn.execute(sql_artikel_direct, {"skus": list(still_probes_lower.keys())})
                for row in result.mappings():
                    lower_art = row["cArtNr"].lower()
                    probe = still_probes_lower.get(lower_art)
                    if probe is None:
                        continue
                    orig_sku_opt2: str | None = probe_to_orig.get(probe)
                    if orig_sku_opt2 is None or orig_sku_opt2 not in remaining:
                        continue
                    orig_sku_ii = orig_sku_opt2
                    ek_raw = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                    results[orig_sku_ii] = PricingResult(
                        seller_sku=orig_sku_ii,
                        matched_jtl_artikel=row["cArtNr"],
                        matched_via="asin-angebot",
                        ek_netto=ek_raw,
                        description=row["cName"] or None,
                        is_bware=is_bware,
                    )
                    remaining.discard(orig_sku_ii)

    # Tier 1: direct match via mapping table
    _fetch_mapping_tier({sku: sku for sku in remaining}, "direct")

    # Tier 2: FBA/MFN suffix stripping → mapping table
    fba_map: dict[str, str] = {}
    for sku in list(remaining):
        stem = _strip_fba(sku)
        if stem:
            fba_map[stem] = sku
    _fetch_mapping_tier(fba_map, "fba")

    # Tier 3: direct match on tArtikel.cArtNr (case-insensitive)
    non_amzn_remaining = [sku for sku in remaining if not sku.startswith(_AMZN_PREFIX)]
    _fetch_artikel_direct(non_amzn_remaining)

    # Separate amzn.gr.* SKUs: B-Ware (match _BWARE_RE) go to Tier 5,
    # non-B-Ware (e.g. too short / unusual structure) go to Tier 4.
    amzn_tier4: list[str] = []
    amzn_tier5: list[str] = []
    for sku in remaining:
        if not sku.startswith(_AMZN_PREFIX):
            continue
        if extract_bware_stem(sku) is not None:
            amzn_tier5.append(sku)
        else:
            amzn_tier4.append(sku)

    # Tier 4: non-B-Ware amzn.gr.* → iterative stem candidates → mapping table
    # Generate up to 3 stem candidates per SKU (remove 1-3 trailing dash-segments).
    # First match (fewest segments removed) wins.
    if amzn_tier4:
        max_depth = 3
        for depth in range(1, max_depth + 1):
            depth_map: dict[str, str] = {}
            for sku in list(remaining):
                if sku not in amzn_tier4 or sku not in remaining:
                    continue
                candidates = _amzn_stem_candidates(sku)
                if len(candidates) >= depth:
                    candidate = candidates[depth - 1]
                    if candidate not in depth_map:
                        depth_map[candidate] = sku
            _fetch_mapping_tier(depth_map, "amzn")

    # Tier 5: B-Ware structured regex stem → mapping (5a) then tArtikel (5b)
    bware_remaining = [sku for sku in amzn_tier5 if sku in remaining]
    bware_stem_match = 0
    bware_fallback = 0

    if bware_remaining:
        if bware_strategy == "flat_10ct":
            # Skip stem lookup entirely — flat price for all remaining amzn.gr.* SKUs
            for sku in bware_remaining:
                results[sku] = PricingResult(
                    seller_sku=sku,
                    matched_jtl_artikel=None,
                    matched_via="bware-fallback",
                    ek_netto=_BWARE_FALLBACK_PRICE,
                    description=None,
                    is_bware=True,
                    bware_pricing_basis=None,
                )
                remaining.discard(sku)
                bware_fallback += 1
        else:
            # "ten_percent": structured regex to extract exact stem
            # 5a: stem → mapping table
            stem_to_sku: dict[str, str] = {}
            for sku in bware_remaining:
                stem = extract_bware_stem(sku)
                if stem and stem not in stem_to_sku:
                    stem_to_sku[stem] = sku

            if stem_to_sku:
                unique_stems = list(stem_to_sku.keys())
                with engine.connect() as conn:
                    result = conn.execute(sql_mapping, {"skus": unique_stems})
                    for row in result.mappings():
                        stem_hit = row["cSellerSKU"]
                        orig_sku = stem_to_sku.get(stem_hit)
                        if orig_sku is None or orig_sku not in remaining:
                            continue
                        full_ek = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                        ek_used = _bware_ek(full_ek) if full_ek is not None else None
                        results[orig_sku] = PricingResult(
                            seller_sku=orig_sku,
                            matched_jtl_artikel=row["cArtNr"],
                            matched_via="bware-stem",
                            ek_netto=ek_used,
                            description=row["cName"] or None,
                            is_bware=True,
                            bware_pricing_basis=full_ek,
                        )
                        remaining.discard(orig_sku)
                        bware_stem_match += 1

            # 5b: stems still unresolved → tArtikel direct
            still_bware = [sku for sku in remaining if sku.startswith(_AMZN_PREFIX)]
            if still_bware:
                stem_to_sku_b: dict[str, str] = {}
                for sku in still_bware:
                    stem = extract_bware_stem(sku)
                    if stem:
                        lower_stem = stem.lower()
                        if lower_stem not in stem_to_sku_b:
                            stem_to_sku_b[lower_stem] = sku

                if stem_to_sku_b:
                    with engine.connect() as conn:
                        result = conn.execute(
                            sql_artikel_direct,
                            {"skus": list(stem_to_sku_b.keys())},
                        )
                        for row in result.mappings():
                            lower_art = row["cArtNr"].lower()
                            orig_sku = stem_to_sku_b.get(lower_art)
                            if orig_sku is None or orig_sku not in remaining:
                                continue
                            full_ek = _clean_decimal(row["fEKNetto"]) or _clean_decimal(row["fLetzterEK"])
                            ek_used = _bware_ek(full_ek) if full_ek is not None else None
                            results[orig_sku] = PricingResult(
                                seller_sku=orig_sku,
                                matched_jtl_artikel=row["cArtNr"],
                                matched_via="bware-stem",
                                ek_netto=ek_used,
                                description=row["cName"] or None,
                                is_bware=True,
                                bware_pricing_basis=full_ek,
                            )
                            remaining.discard(orig_sku)
                            bware_stem_match += 1

            # Tier 6 for amzn.gr.* before fallback (only with ten_percent strategy)
            _run_tier6(is_bware=True)

            # Remaining amzn.gr.* with no stem match → fallback 0.10 EUR
            for sku in list(remaining):
                if sku.startswith(_AMZN_PREFIX):
                    results[sku] = PricingResult(
                        seller_sku=sku,
                        matched_jtl_artikel=None,
                        matched_via="bware-fallback",
                        ek_netto=_BWARE_FALLBACK_PRICE,
                        description=None,
                        is_bware=True,
                        bware_pricing_basis=None,
                    )
                    remaining.discard(sku)
                    bware_fallback += 1

    # Tier 6: ASIN-based lookup for all still-remaining SKUs with known ASIN
    # (for non-amzn.gr.* SKUs that slipped through Tiers 1-3, and amzn.gr.* already
    # handled above inside the ten_percent branch)
    _run_tier6(is_bware=False)

    # Fill not-found
    for sku in remaining:
        results[sku] = PricingResult(
            seller_sku=sku,
            matched_jtl_artikel=None,
            matched_via=None,
            ek_netto=None,
            description=None,
        )

    tier_counts: dict[str | None, int] = {
        "direct": 0, "fba": 0, "tArtikel-direct": 0, "amzn": 0,
        "bware-stem": 0, "asin-tartikel": 0, "asin-angebot": 0,
        "bware-fallback": 0, None: 0,
    }
    for r in results.values():
        tier_counts[r.matched_via] = tier_counts.get(r.matched_via, 0) + 1

    logger.info(
        "lookup_prices: %d skus in | direct=%d fba=%d tArtikel=%d amzn=%d "
        "bware_stem=%d asin_fba=%d asin_mfn=%d bware_fallback=%d | unresolved=%d",
        len(skus),
        tier_counts["direct"],
        tier_counts["fba"],
        tier_counts["tArtikel-direct"],
        tier_counts["amzn"],
        bware_stem_match,
        tier_counts["asin-tartikel"],
        tier_counts["asin-angebot"],
        bware_fallback,
        tier_counts[None],
    )
    return results
