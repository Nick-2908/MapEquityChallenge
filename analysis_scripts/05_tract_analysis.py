"""Tract-level analysis: Overture aggregates x ACS housing x strata."""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis_outputs"
REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx", "eastern-wa"]
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 500)
pd.set_option("display.float_format", lambda v: f"{v:.3f}")

lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


agg = pd.read_parquet(OUT / "tract_overture_aggregates.parquet")
st = pd.read_parquet(OUT / "scored_tracts_strata.parquet")
acs = pd.concat([pd.read_parquet(DATA / f"reference/{r}/{r}-census-acs-housing.parquet", columns=["GEOID", "housing_units"])
                 for r in REGIONS])
df = agg.merge(acs, on="GEOID", how="left").merge(st.drop(columns=["region"]), on="GEOID", how="left")
cnt_cols = [c for c in agg.columns if c.startswith(("bldg_n", "road_", "ru_", "rail_", "infra_", "poi_n", "bldg_area"))]
df[cnt_cols] = df[cnt_cols].fillna(0)
df["aland_km2"] = df.ALAND / 1e6
df["water_share"] = df.AWATER / (df.ALAND + df.AWATER)
df["tribal"] = df.tribal_any.fillna(False)
df["rural"] = df.ur_class.eq("Rural")
df["svi_q"] = pd.qcut(df.svi_overall, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
df["ruca_grp"] = pd.cut(df.ruca_primary, [0, 3, 6, 9, 10, 100], labels=["metro 1-3", "micro 4-6", "small 7-9", "rural 10", "99"])
df.to_parquet(OUT / "tract_analysis_table.parquet")
log(f"rows={len(df)}  regions={df.region.value_counts().to_dict()}")
log(f"tract area check (ours vs ALAND+AWATER, median ratio): "
    f"{(df.tract_area_km2 / ((df.ALAND + df.AWATER) / 1e6)).median():.4f}")

g = df.groupby("region")

log("\n" + "=" * 25, "1. ZERO-COVERAGE RATES (share of scored tracts with none of X in Overture)", "=" * 25)
zero = pd.DataFrame({
    "no_buildings": g.bldg_n.apply(lambda s: (s == 0).mean()),
    "no_roads(any scored class)": g.road_km_all.apply(lambda s: (s == 0).mean()),
    "no_hwy(motorway/trunk/primary/secondary)": g.road_km_hwy.apply(lambda s: (s < 0.01).mean()),
    "no_motorway_trunk": g.apply(lambda d: ((d.road_km_motorway + d.road_km_trunk) < 0.01).mean()),
    "no_pois": g.poi_n.apply(lambda s: (s == 0).mean()),
    "no_fire_station": g.poi_n_fire.apply(lambda s: (s == 0).mean()),
    "no_ems": g.poi_n_ems.apply(lambda s: (s == 0).mean()),
    "no_school": g.poi_n_school.apply(lambda s: (s == 0).mean()),
    "no_fire_ems_school": g.apply(lambda d: ((d.poi_n_fire + d.poi_n_ems + d.poi_n_school) == 0).mean()),
    "no_rail": g.rail_km.apply(lambda s: (s == 0).mean()),
    "no_transit_stop": g.infra_n_transit.apply(lambda s: (s == 0).mean()),
})
log(zero.T.round(3).to_string())
log("\nZindi-stated share of tracts with >=1 undefined component: eastern-ok 21%, northern-ca 37%, "
    "south-central-tx 28%, maricopa-az 55% (driven by 'no named-highway road').")

log("\n" + "=" * 25, "2. PER-TRACT DISTRIBUTIONS", "=" * 25)
for c in ["bldg_n", "housing_units", "usfs_BuildingCount_sum", "carbonplan_buildings", "usfs_HUCount_sum",
          "road_km_all", "road_km_hwy", "poi_n", "poi_n_fire", "poi_n_ems", "poi_n_school", "poi_n_hospital", "rail_km",
          "infra_n_transit"]:
    log(f"\n{c}:")
    log(g[c].describe(percentiles=[.05, .25, .5, .75, .95]).round(2).to_string())

log("\n" + "=" * 25, "3. BUILDING COUNT RATIOS vs INDEPENDENT COUNTS", "=" * 25)
for den in ["housing_units", "usfs_BuildingCount_sum", "carbonplan_buildings", "usfs_HUCount_sum"]:
    ratio = df.bldg_n / df[den].replace(0, np.nan)
    df[f"ratio_bldg_{den}"] = ratio
    log(f"\nOverture bldg_n / {den}:")
    log(df.groupby("region")[f"ratio_bldg_{den}"].describe(percentiles=[.05, .1, .25, .5, .75, .9, .95]).round(3).to_string())
    log("  share of tracts with ratio < 1 / < 0.9 / < 0.75 / < 0.5:")
    log(df.groupby("region")[f"ratio_bldg_{den}"].apply(
        lambda s: pd.Series({k: (s.dropna() < k).mean() for k in (1, .9, .75, .5)})).unstack().round(3).to_string())

log("\nSpearman correlation of counts (all scored tracts):")
log(df[["bldg_n", "bldg_n_msft", "bldg_n_osm", "housing_units", "usfs_BuildingCount_sum", "carbonplan_buildings",
        "usfs_HUCount_sum", "pop_total", "poi_n"]].corr(method="spearman").round(3).to_string())
log("\nPearson log1p correlation per region, bldg_n vs usfs_BuildingCount_sum / carbonplan_buildings / housing_units:")
for r, d in g:
    lb = np.log1p(d.bldg_n)
    log(f"  [{r:<16}] usfs={np.corrcoef(lb, np.log1p(d.usfs_BuildingCount_sum))[0, 1]:.3f} "
        f"carbonplan={np.corrcoef(lb, np.log1p(d.carbonplan_buildings.fillna(0)))[0, 1]:.3f} "
        f"acs_hu={np.corrcoef(lb, np.log1p(d.housing_units))[0, 1]:.3f}")

log("\n" + "=" * 25, "4. BUILDING SOURCE MIX BY STRATA (share of tract buildings by first source)", "=" * 25)
for c in ["osm", "msft", "esri", "google"]:
    df[f"share_{c}"] = df[f"bldg_n_{c}"] / df.bldg_n.replace(0, np.nan)
mix = ["share_osm", "share_msft", "share_esri", "share_google"]
log("By region (mean of tract shares):")
log(g[mix].mean().round(3).to_string())
for strat in ["ur_class", "tribal", "svi_q", "ruca_grp"]:
    log(f"\nBy region x {strat}:")
    log(df.groupby(["region", strat], observed=True)[mix].mean().round(3).to_string())
log("\nShare of tracts where Microsoft ML is >80% of buildings:")
log(g.share_msft.apply(lambda s: (s > .8).mean()).round(3).to_string())

log("\n" + "=" * 25, "5. COVERAGE PROXIES BY STRATA (medians)", "=" * 25)
df["bldg_per_hu"] = df.bldg_n / df.housing_units.replace(0, np.nan)
df["poi_per_1k_pop"] = 1000 * df.poi_n / df.pop_total.replace(0, np.nan)
df["poi_per_100_bldg"] = 100 * df.poi_n / df.bldg_n.replace(0, np.nan)
df["road_km_per_km2"] = df.road_km_all / df.aland_km2.replace(0, np.nan)
df["hwy_share_of_road_km"] = df.road_km_hwy / df.road_km_all.replace(0, np.nan)
df["service_km_per_hu"] = df.ru_km_service / df.housing_units.replace(0, np.nan)
prox = ["bldg_per_hu", "ratio_bldg_usfs_BuildingCount_sum", "ratio_bldg_carbonplan_buildings", "poi_per_1k_pop",
        "poi_per_100_bldg", "road_km_per_km2", "hwy_share_of_road_km", "service_km_per_hu"]
for strat in ["ur_class", "tribal", "svi_q", "ruca_grp"]:
    log(f"\nBy region x {strat}:")
    log(df.groupby(["region", strat], observed=True)[prox].median().round(3).to_string())
    log(df.groupby(["region", strat], observed=True).size().rename("n").to_frame().T.to_string())

log("\n" + "=" * 25, "6. FACILITY POIs (target facility categories)", "=" * 25)
for strat in ["ur_class", "tribal"]:
    log(f"\nShare of tracts with >=1 fire_department / ems / school POI, by region x {strat}:")
    log(df.groupby(["region", strat], observed=True)
        .agg(fire=("poi_n_fire", lambda s: (s > 0).mean()), ems=("poi_n_ems", lambda s: (s > 0).mean()),
             school=("poi_n_school", lambda s: (s > 0).mean()), hospital=("poi_n_hospital", lambda s: (s > 0).mean()),
             n=("GEOID", "size")).round(3).to_string())
log("\nRegion totals: fire / ems / school / hospital POIs, and per 100k pop:")
tot = g[["poi_n_fire", "poi_n_ems", "poi_n_school", "poi_n_hospital", "pop_total"]].sum()
for c in ["poi_n_fire", "poi_n_ems", "poi_n_school", "poi_n_hospital"]:
    tot[c + "_per100k"] = 1e5 * tot[c] / tot.pop_total
log(tot.round(2).to_string())

log("\n" + "=" * 25, "7. EDGE CASES", "=" * 25)
ec = pd.DataFrame({
    "zero_pop": g.pop_total.apply(lambda s: (s == 0).sum()),
    "zero_hu": g.housing_units.apply(lambda s: (s == 0).sum()),
    "null_hu": g.housing_units.apply(lambda s: s.isna().sum()),
    "water>50%": g.water_share.apply(lambda s: (s > .5).sum()),
    "aland<0.5km2": g.aland_km2.apply(lambda s: (s < .5).sum()),
    "aland>1000km2": g.aland_km2.apply(lambda s: (s > 1000).sum()),
    "bldg_n==0": g.bldg_n.apply(lambda s: (s == 0).sum()),
    "bldg>hu*3": g.apply(lambda d: (d.bldg_n > 3 * d.housing_units).sum()),
    "bldg<hu*0.3": g.apply(lambda d: (d.bldg_n < 0.3 * d.housing_units).sum()),
    "usfs_bldg<10": g.usfs_BuildingCount_sum.apply(lambda s: (s < 10).sum()),
})
log(ec.T.to_string())
log("\nZero-population tracts (GEOID, NAMELSAD-ish, aland km2, water_share, bldg_n, housing_units, poi_n):")
z = df[df.pop_total == 0][["region", "GEOID", "aland_km2", "water_share", "bldg_n", "housing_units", "poi_n",
                           "road_km_all", "usfs_BuildingCount_sum"]]
log(z.round(3).to_string(index=False))
log("\nWater-dominated (>50% water) scored tracts:")
w = df[df.water_share > .5][["region", "GEOID", "aland_km2", "water_share", "pop_total", "bldg_n", "housing_units",
                             "road_km_all", "poi_n"]]
log(w.round(3).to_string(index=False))

log("\n" + "=" * 25, "8. SPEARMAN: coverage proxies vs strata (pooled, and per region)", "=" * 25)
strata_vars = ["pct_urban", "ruca_primary", "svi_overall", "cvi_overall", "tribal_pct", "pop_total",
               "usfs_WHP_mean", "usdm_summer_dsci", "gehe_wbgt28_days_mean", "epht_heat_days_summer"]
cm = df[prox + strata_vars].corr(method="spearman").loc[prox, strata_vars]
log(cm.round(3).to_string())
for r, d in g:
    log(f"\n[{r}]")
    log(d[prox + strata_vars].corr(method="spearman").loc[prox, strata_vars].round(2).to_string())

(OUT / "05_tract_analysis.txt").write_text("\n".join(lines), encoding="utf-8")
df.to_parquet(OUT / "tract_analysis_table.parquet")
