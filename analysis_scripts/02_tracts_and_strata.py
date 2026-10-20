"""Tract-set consistency across files + strata profile of the scored tracts per region."""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis_outputs"
REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx", "eastern-wa"]
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 500)

lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


# ---------- A. tract-set consistency ----------
log("=" * 30, "A. TRACT SET CONSISTENCY", "=" * 30)
sets = {}
for r in REGIONS:
    sub = pd.read_csv(DATA / f"reference/{r}/{r}-sample-submission.csv", dtype={"GEOID": str})
    bnd = pd.read_csv(DATA / f"boundaries/{r}-tract-geoids.csv", dtype={"GEOID": str})
    trc = pd.read_parquet(DATA / f"strata/{r}/{r}-census-tracts.parquet", columns=["GEOID", "frac_inside_aoi"])
    acs = pd.read_parquet(DATA / f"reference/{r}/{r}-census-acs-housing.parquet", columns=["GEOID", "housing_units"])
    stt = pd.read_parquet(DATA / f"strata/{r}/{r}-strata-tract-table.parquet", columns=["GEOID"])
    s_sub, s_bnd, s_trc, s_acs, s_stt = (set(x.GEOID) for x in (sub, bnd, trc, acs, stt))
    sets[r] = s_sub
    log(f"\n[{r}] sub={len(sub)} (unique {len(s_sub)}) boundaries={len(s_bnd)} census-tracts={len(s_trc)} "
        f"acs={len(s_acs)} strata={len(s_stt)}")
    log(f"  GEOID lengths in sub: {sub.GEOID.str.len().value_counts().to_dict()}  "
        f"state FIPS: {sub.GEOID.str[:2].value_counts().to_dict()}  counties: {sub.GEOID.str[:5].nunique()}")
    log(f"  sub columns: {list(sub.columns)}; all-zero values: {bool((sub.drop(columns='GEOID') == 0).all().all())}")
    log(f"  boundaries - sub: {sorted(s_bnd - s_sub)}")
    log(f"  sub - boundaries: {sorted(s_sub - s_bnd)};  sub == census-tracts: {s_sub == s_trc};  "
        f"sub == strata: {s_sub == s_stt};  acs - sub: {sorted(s_acs - s_sub)}; sub - acs: {sorted(s_sub - s_acs)}")
    log(f"  frac_inside_aoi range: {trc.frac_inside_aoi.min()} .. {trc.frac_inside_aoi.max()}")
all_ids = [g for s in sets.values() for g in s]
log(f"\nTotal scored tracts (5 regions): {len(all_ids)}; unique: {len(set(all_ids))}; "
    f"4 Zindi regions (excl. eastern-wa): {sum(len(sets[r]) for r in REGIONS if r != 'eastern-wa')}")

# ---------- B. strata profile ----------
log("\n" + "=" * 30, "B. STRATA PROFILE (scored tracts, national strata table)", "=" * 30)
nat = pd.read_parquet(DATA / "strata/national/national-strata-tract-table.parquet")
reg_of = {g: r for r, s in sets.items() for g in s}
df = nat[nat.GEOID.isin(reg_of)].copy()
df["region"] = df.GEOID.map(reg_of)
df.to_parquet(OUT / "scored_tracts_strata.parquet")
log(f"rows matched: {len(df)} / {len(reg_of)}")

df["water_share"] = df.AWATER / (df.ALAND + df.AWATER)
df["aland_km2"] = df.ALAND / 1e6
df["pop_density_km2"] = df.pop_total / df.aland_km2.replace(0, np.nan)


def q(s):
    s = s.dropna()
    if s.empty:
        return "all null"
    return (f"n={len(s)} min={s.min():.3g} p10={s.quantile(.1):.3g} p50={s.median():.3g} "
            f"mean={s.mean():.3g} p90={s.quantile(.9):.3g} max={s.max():.3g}")


g = df.groupby("region")
log("\n-- Size / population --")
for r, d in g:
    log(f"[{r}] tracts={len(d)} pop_total_sum={d.pop_total.sum():,} zero-pop tracts={int((d.pop_total == 0).sum())} "
        f"pop<100={int((d.pop_total < 100).sum())}")
    log(f"    pop_total: {q(d.pop_total)}")
    log(f"    ALAND km2: {q(d.aland_km2)}")
    log(f"    pop density /km2: {q(d.pop_density_km2)}")
    log(f"    water_share: {q(d.water_share)}  tracts water_share>0.5: {int((d.water_share > .5).sum())}")

log("\n-- Urban/rural (ur_class, census 2020) --")
log(pd.crosstab(df.region, df.ur_class, margins=True).to_string())
log("\npct_urban buckets:")
log(pd.crosstab(df.region, pd.cut(df.pct_urban, [-0.01, 0, 0.5, 0.99, 1.0],
                                  labels=["0", "(0,.5]", "(.5,.99]", "1"])).to_string())
log("\n-- RUCA primary (1=metro core .. 10=rural) --")
log(pd.crosstab(df.region, df.ruca_primary.fillna(-1).astype(int), margins=True).to_string())
log("\n-- RUCC 2023 (county) --")
log(pd.crosstab(df.region, df.rucc_2023.fillna(-1).astype(int)).to_string())
log("\n-- NCHS 2013 (1=large central metro .. 6=noncore) --")
log(pd.crosstab(df.region, df.nchs_2013.fillna(-1).astype(int)).to_string())

log("\n-- Tribal --")
log(pd.crosstab(df.region, df.tribal_any, margins=True).to_string())
log(pd.crosstab(df.region, [df.tribal_legal, df.tribal_statistical]).to_string())
for r, d in g:
    t = d[d.tribal_any == True]
    log(f"[{r}] tribal tracts={len(t)} tribal_pct: {q(t.tribal_pct)}")
    log(f"    aiannh_kind: {t.aiannh_kind.value_counts().to_dict()}")
    log(f"    top aiannh: {t.aiannh_name.value_counts().head(8).to_dict()}")

log("\n-- SVI / CVI --")
for r, d in g:
    log(f"[{r}] svi_covered={d.svi_covered.mean():.3f} svi_overall: {q(d.svi_overall)}  svi<0 count={int((d.svi_overall < 0).sum())}")
    log(f"    cvi_covered={d.cvi_covered.mean():.3f} cvi_overall: {q(d.cvi_overall)}")

log("\n-- Hazards (headline) --")
haz = ["usdm_summer_dsci", "usdm_winter_dsci", "usfs_WHP_mean", "usfs_RPS_mean", "usfs_BP_mean",
       "epht_heat_days_summer", "gehe_wbgt28_days_mean", "hwd_heatindex_mean", "mtbs_wildfire_burned_pct_land",
       "nifc_wildfire_ever", "fod_fires", "carbonplan_rps_2011_mean", "pmdi_mean", "spi12_mean"]
for c in haz:
    log(f"{c}:")
    for r, d in g:
        s = d[c].astype(float) if d[c].dtype == bool else d[c]
        log(f"   [{r:<16}] {q(s)}")

log("\n-- *_covered flags (share True) --")
cov = [c for c in df.columns if c.endswith("_covered")]
log(df.groupby("region")[cov].mean().round(3).T.to_string())

log("\n-- Missingness: columns with any nulls, share null per region --")
na = df.drop(columns=["region"]).isna().groupby(df.region).mean()
na = na.loc[:, na.max() > 0].T.round(3)
log(f"{len(na)} of {df.shape[1]-1} columns have nulls somewhere")
log(na.to_string())

log("\n-- Independent building / housing counts carried in strata --")
for c in ["usfs_BuildingCount_sum", "usfs_HUCount_sum", "usfs_PopCount_sum", "carbonplan_buildings",
          "usfs_BuildingDensity_mean", "usfs_BuildingCover_mean"]:
    log(f"{c}:")
    for r, d in g:
        log(f"   [{r:<16}] {q(d[c])}  nulls={int(d[c].isna().sum())}")

(OUT / "02_tracts_and_strata.txt").write_text("\n".join(lines), encoding="utf-8")
