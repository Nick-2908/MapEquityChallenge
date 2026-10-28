"""Aggregate the raw Overture layers to one row per scored tract.

    python eda/build_tract_table.py [region ...]      # default: all five regions

Writes eda_outputs/_cache/<region>.parquet per region and eda_outputs/tract_overture.parquet (all regions).
Per-region files are reused if present; delete them to rebuild.

Definitions
    tract set         the region's sample-submission GEOIDs (the authoritative scored list)
    tract_area_km2    geodesic area of the tract polygon
    buildings         a footprint belongs to the tract that contains its centroid; areas are geodesic (m2)
    roads, rail       clipped to the tract in lon/lat, then measured in EPSG:5070 (km)
    roads-unfiltered  same, all classes (ru_*)
    infrastructure    features intersecting the tract
    POIs              point-in-tract
A tract with no feature of a kind is left NaN here; notebook 03 turns counts into zeros on purpose.
"""
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REF, STR, OUT = ROOT / "data" / "reference", ROOT / "data" / "strata", ROOT / "eda_outputs"
CACHE = OUT / "_cache"
REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx", "eastern-wa"]
SCHOOL = ("school", "elementary_school", "middle_school", "high_school", "private_school", "public_school")
SRC = {"Microsoft ML Buildings": "msft", "OpenStreetMap": "osm", "Esri Community Maps": "esri", "Google Open Buildings": "google"}
CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified"]
HWY = ["motorway", "trunk", "primary", "secondary"]
NONMOTOR = ("footway", "path", "cycleway", "bridleway", "pedestrian", "steps")


def log(msg):
    OUT.mkdir(exist_ok=True)
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(OUT / "build_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_region(reg: str) -> pd.DataFrame:
    p = lambda layer: f"read_parquet('{(REF / reg / f'{reg}-overture-{layer}.parquet').as_posix()}')"
    t0 = time.time()
    ids = pd.read_csv(REF / reg / f"{reg}-sample-submission.csv", dtype={"GEOID": str})[["GEOID"]]
    c = duckdb.connect()
    c.sql("load spatial")
    c.sql("set geometry_always_xy = true")
    c.register("ids", ids)
    c.sql(f"""create table tr as select GEOID, geometry g, ST_Area_Spheroid(geometry)/1e6 tract_area_km2
              from read_parquet('{(STR / reg / f'{reg}-census-tracts.parquet').as_posix()}') where GEOID in (select GEOID from ids)""")
    assert c.sql("select count(*) from tr").fetchall()[0][0] == len(ids), "tract polygons do not cover the scored list"

    ds = " ".join(f"when '{k}' then '{v}'" for k, v in SRC.items())
    c.sql(f"""create table b as select t.GEOID, ST_Area_Spheroid(b.geometry) a, b.height, b.num_floors, b.class, b.subtype, b.names."primary" nm,
              case b.sources[1].dataset {ds} else 'other' end src, b.sources[1].dataset dset,
              try_cast(substr(b.sources[1].update_time, 1, 4) as integer) yr
              from {p('buildings')} b join tr t on ST_Intersects(ST_Centroid(b.geometry), t.g)""")
    bld = c.sql("""select GEOID, count(*) bldg_n, sum(a) bldg_area_m2, median(a) bldg_area_median_m2,
                   count(*) filter (where a < 30) bldg_n_lt30m2, count(*) filter (where a >= 300) bldg_n_ge300m2,
                   count(height) bldg_n_height, count(num_floors) bldg_n_floors, count(class) bldg_n_class,
                   count(subtype) bldg_n_subtype, count(nm) bldg_n_name,
                   count(*) filter (where src='osm') bldg_n_osm, count(*) filter (where src='msft') bldg_n_msft,
                   count(*) filter (where src='google') bldg_n_google, count(*) filter (where src='esri') bldg_n_esri,
                   count(*) filter (where src='other') bldg_n_other, count(distinct dset) bldg_src_n,
                   median(yr) bldg_year_median, count(*) filter (where yr >= 2024) bldg_n_upd_ge2024 from b group by 1""").df()
    log(f"[{reg}] buildings {len(bld)} tracts ({time.time()-t0:.0f}s)")

    c.sql(f"""create table rc as select t.GEOID, r.class cls,
              ST_Length(ST_Transform(ST_Intersection(r.geometry, t.g), 'EPSG:5070'))/1000 km
              from {p('roads')} r join tr t on ST_Intersects(r.geometry, t.g)""")
    rd = c.sql("select GEOID, cls, sum(km) km, count(*) n from rc group by 1,2").df()
    road = rd.pivot(index="GEOID", columns="cls", values="km").reindex(columns=CLASSES)
    road.columns = [f"road_km_{k}" for k in road.columns]
    road["road_km_all"] = rd.groupby("GEOID").km.sum()
    road["road_km_hwy"] = road[[f"road_km_{k}" for k in HWY]].sum(axis=1, min_count=1)
    road["road_n_pieces"] = rd.groupby("GEOID").n.sum()
    road["road_n_hwy_pieces"] = rd[rd.cls.isin(HWY)].groupby("GEOID").n.sum()
    road = road.reset_index()
    log(f"[{reg}] roads {len(road)} tracts ({time.time()-t0:.0f}s)")

    nm = ",".join(f"'{x}'" for x in NONMOTOR)
    ru = c.sql(f"""select GEOID, sum(km) ru_km_all, sum(km) filter (where cls='service') ru_km_service,
                   sum(km) filter (where cls='track') ru_km_track, sum(km) filter (where cls in ({nm})) ru_km_nonmotor,
                   sum(km) filter (where cls='unknown') ru_km_unknown, count(*) ru_n_pieces
                   from (select t.GEOID, u.class cls, ST_Length(ST_Transform(ST_Intersection(u.geometry, t.g), 'EPSG:5070'))/1000 km
                         from {p('roads-unfiltered')} u join tr t on ST_Intersects(u.geometry, t.g)) group by 1""").df()
    log(f"[{reg}] unfiltered roads {len(ru)} tracts ({time.time()-t0:.0f}s)")

    rail = c.sql(f"""select t.GEOID, sum(ST_Length(ST_Transform(ST_Intersection(r.geometry, t.g), 'EPSG:5070')))/1000 rail_km, count(*) rail_n_pieces
                     from {p('rail')} r join tr t on ST_Intersects(r.geometry, t.g) group by 1""").df()
    inf = c.sql(f"""select t.GEOID, count(*) infra_n, count(*) filter (where i.subtype='transit') infra_n_transit,
                    count(*) filter (where i.subtype='airport') infra_n_airport, count(*) filter (where i.class='bus_stop') infra_n_busstop
                    from {p('infrastructure')} i join tr t on ST_Intersects(i.geometry, t.g) group by 1""").df()

    sch = ",".join(f"'{s}'" for s in SCHOOL)
    poi = c.sql(f"""select t.GEOID, count(*) poi_n, count(*) filter (where confidence >= 0.5) poi_n_conf05,
                    count(*) filter (where confidence >= 0.8) poi_n_conf08, avg(confidence) poi_conf_mean,
                    count(*) filter (where operating_status = 'open') poi_n_open,
                    count(*) filter (where operating_status = 'permanently_closed') poi_n_closed,
                    count(*) filter (where categories."primary" is null) poi_n_nocat,
                    count(distinct categories."primary") poi_n_distinct_cat, count(distinct x.sources[1].dataset) poi_src_n,
                    count(*) filter (where categories."primary" = 'fire_department') poi_n_fire,
                    count(*) filter (where categories."primary" = 'ambulance_and_ems_services') poi_n_ems,
                    count(*) filter (where categories."primary" in ({sch})) poi_n_school,
                    count(*) filter (where categories."primary" = 'hospital') poi_n_hospital,
                    count(*) filter (where list_contains(categories.alternate, 'fire_department')) poi_n_fire_alt,
                    count(*) filter (where list_contains(categories.alternate, 'ambulance_and_ems_services')) poi_n_ems_alt,
                    count(*) filter (where categories."primary" <> 'fire_department' and list_contains(categories.alternate, 'fire_department')) poi_n_fire_altonly
                    from {p('pois')} x join tr t on ST_Intersects(x.geometry, t.g) group by 1""").df()
    log(f"[{reg}] pois {len(poi)} tracts ({time.time()-t0:.0f}s)")

    out = c.sql("select GEOID, tract_area_km2 from tr").df()
    for part in (bld, road, ru, rail, inf, poi):
        out = out.merge(part, on="GEOID", how="left")
    out.insert(0, "region", reg)
    return out.sort_values("GEOID").reset_index(drop=True)


if __name__ == "__main__":
    regs = sys.argv[1:] or REGIONS
    CACHE.mkdir(parents=True, exist_ok=True)
    parts = []
    for r in regs:
        f = CACHE / f"{r}.parquet"
        if not f.exists():
            build_region(r).to_parquet(f, index=False)
        parts.append(pd.read_parquet(f))
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(OUT / "tract_overture.parquet", index=False)
    log(f"written {df.shape}")
