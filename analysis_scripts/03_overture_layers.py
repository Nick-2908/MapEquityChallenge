"""Layer-level profile of each Overture extract per region (no tract join)."""
import pathlib

import duckdb
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis_outputs"
REGIONS = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx", "eastern-wa"]
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 500)

con = duckdb.connect()
con.sql("LOAD spatial; SET memory_limit='6GB'; SET threads=8; SET preserve_insertion_order=false;")
con.sql(f"SET temp_directory='{(OUT / 'duckdb_tmp').as_posix()}'")

lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def f(r, layer):
    return (DATA / f"reference/{r}/{r}-overture-{layer}.parquet").as_posix()


def df(sql):
    return con.sql(sql).df()


LEN_KM = "ST_Length(ST_Transform(geometry, 'EPSG:4326', 'EPSG:5070', always_xy := true))/1000"

# sanity check on length method: 5070 vs spheroid
r0 = "northern-ca"
chk = df(f"""SELECT sum({LEN_KM}) km_5070,
                    sum(ST_Length_Spheroid(ST_FlipCoordinates(geometry)))/1000 km_sph
             FROM (SELECT geometry FROM '{f(r0, 'roads')}' LIMIT 20000)""")
log("Length sanity (northern-ca, 20k segments):", chk.to_dict("records"))

# ---------------- BUILDINGS ----------------
log("\n" + "=" * 30, "BUILDINGS", "=" * 30)
for r in REGIONS:
    p = f(r, "buildings")
    log(f"\n[{r}]")
    log(df(f"""SELECT count(*) n, count(DISTINCT id) n_ids,
                  round(avg(len(sources)),3) avg_n_sources,
                  round(100*avg((subtype IS NOT NULL)::INT),2) pct_subtype,
                  round(100*avg(("class" IS NOT NULL)::INT),2) pct_class,
                  round(100*avg((height IS NOT NULL)::INT),2) pct_height,
                  round(100*avg((num_floors IS NOT NULL)::INT),2) pct_floors,
                  round(100*avg((names.primary IS NOT NULL)::INT),2) pct_named,
                  round(100*avg(has_parts::INT),2) pct_has_parts,
                  round(100*avg(coalesce(is_underground,false)::INT),3) pct_underground
               FROM '{p}'""").to_string(index=False))
    log("  first-source dataset (sources[1].dataset) x confidence availability:")
    log(df(f"""SELECT sources[1].dataset AS dataset, count(*) n,
                  round(100.0*count(*)/sum(count(*)) OVER (),2) pct,
                  round(100*avg((sources[1].confidence IS NOT NULL)::INT),1) pct_conf,
                  round(avg(sources[1].confidence),3) avg_conf,
                  min(substr(sources[1].update_time,1,4)) min_year, max(substr(sources[1].update_time,1,4)) max_year
               FROM '{p}' GROUP BY 1 ORDER BY n DESC""").to_string(index=False))
    log("  all source datasets (unnested; a building can list several):")
    log(df(f"""SELECT s.dataset, s.property, count(*) n FROM '{p}', unnest(sources) t(s)
               GROUP BY 1,2 ORDER BY n DESC LIMIT 12""").to_string(index=False))
    log("  subtype distribution:")
    log(df(f"""SELECT subtype, count(*) n, round(100.0*count(*)/sum(count(*)) OVER (),2) pct
               FROM '{p}' GROUP BY 1 ORDER BY n DESC LIMIT 12""").to_string(index=False))
    log("  footprint area (m2, EPSG:5070) quantiles:")
    log(df(f"""SELECT quantile_cont(a,[0.01,0.1,0.5,0.9,0.99]) q, avg(a) mean,
                  round(100*avg((a<20)::INT),2) pct_lt20m2
               FROM (SELECT ST_Area(ST_Transform(geometry,'EPSG:4326','EPSG:5070',always_xy:=true)) a
                     FROM '{p}' USING SAMPLE 200000)""").to_string(index=False))

# ---------------- ROADS ----------------
log("\n" + "=" * 30, "ROADS (scored layer)", "=" * 30)
for r in REGIONS:
    p = f(r, "roads")
    log(f"\n[{r}]")
    log(df(f"""SELECT "class", count(*) n_segments, round(sum({LEN_KM}),1) km,
                  round(100*avg((names.primary IS NOT NULL)::INT),1) pct_named,
                  round(100*avg((len(routes)>0)::INT),1) pct_with_route_ref
               FROM '{p}' GROUP BY 1 ORDER BY km DESC""").to_string(index=False))
    log("  first-source dataset:")
    log(df(f"""SELECT sources[1].dataset dataset, count(*) n FROM '{p}' GROUP BY 1 ORDER BY n DESC""").to_string(index=False))
    log("  subtype / geometry type:")
    log(df(f"""SELECT subtype, ST_GeometryType(geometry) gt, count(*) n FROM '{p}' GROUP BY 1,2 ORDER BY n DESC""").to_string(index=False))

log("\n" + "=" * 30, "ROADS-UNFILTERED (class mix; km)", "=" * 30)
parts = []
for r in REGIONS:
    d = df(f"""SELECT "class", round(sum({LEN_KM}),0) km, count(*) n FROM '{f(r, 'roads-unfiltered')}' GROUP BY 1""")
    d["region"] = r
    parts.append(d)
u = pd.concat(parts)
log(u.pivot_table(index="class", columns="region", values="km", aggfunc="sum").fillna(0)
    .sort_values("south-central-tx", ascending=False).to_string())

# ---------------- RAIL ----------------
log("\n" + "=" * 30, "RAIL", "=" * 30)
parts = []
for r in REGIONS:
    d = df(f"""SELECT "class", round(sum({LEN_KM}),0) km, count(*) n FROM '{f(r, 'rail')}' GROUP BY 1""")
    d["region"] = r
    parts.append(d)
log(pd.concat(parts).pivot_table(index="class", columns="region", values="km", aggfunc="sum").fillna(0).to_string())

# ---------------- INFRASTRUCTURE ----------------
log("\n" + "=" * 30, "INFRASTRUCTURE", "=" * 30)
parts = []
for r in REGIONS:
    d = df(f"""SELECT subtype, "class", count(*) n FROM '{f(r, 'infrastructure')}' GROUP BY 1,2""")
    d["region"] = r
    parts.append(d)
log(pd.concat(parts).pivot_table(index=["subtype", "class"], columns="region", values="n", aggfunc="sum")
    .fillna(0).astype(int).to_string())

# ---------------- POIS ----------------
log("\n" + "=" * 30, "POIS", "=" * 30)
TARGET_CATS = {
    "fire": ["fire_department"],
    "ems": ["ambulance_and_ems_services"],
    "schools": ["elementary_school", "middle_school", "high_school", "school", "private_school", "public_school"],
    "hospital": ["hospital"],
}
for r in REGIONS:
    p = f(r, "pois")
    log(f"\n[{r}]")
    log(df(f"""SELECT count(*) n, count(DISTINCT id) n_ids,
                  round(100*avg((categories.primary IS NULL)::INT),2) pct_no_category,
                  round(100*avg((basic_category IS NULL)::INT),2) pct_no_basic_cat,
                  quantile_cont(confidence,[0.1,0.25,0.5,0.75,0.9]) conf_q,
                  round(100*avg((confidence>=0.5)::INT),1) pct_conf_ge_05,
                  round(100*avg((confidence>=0.8)::INT),1) pct_conf_ge_08,
                  round(100*avg((len(websites)>0)::INT),1) pct_web,
                  round(100*avg((len(phones)>0)::INT),1) pct_phone,
                  round(100*avg((brand.wikidata IS NOT NULL OR brand.names.primary IS NOT NULL)::INT),1) pct_brand
               FROM '{p}'""").to_string(index=False))
    log("  operating_status:", df(f"SELECT operating_status, count(*) n FROM '{p}' GROUP BY 1 ORDER BY n DESC").to_dict("records"))
    log("  source datasets (unnested):",
        df(f"SELECT s.dataset, count(*) n FROM '{p}', unnest(sources) t(s) GROUP BY 1 ORDER BY n DESC").to_dict("records"))
    log("  n sources per POI:", df(f"SELECT len(sources) k, count(*) n FROM '{p}' GROUP BY 1 ORDER BY 1").to_dict("records"))
    log("  top 25 categories.primary:")
    log(df(f"""SELECT categories.primary cat, count(*) n FROM '{p}' GROUP BY 1 ORDER BY n DESC LIMIT 25""").to_string(index=False))
    for k, cats in TARGET_CATS.items():
        lst = ",".join(f"'{c}'" for c in cats)
        d = df(f"""SELECT categories.primary cat, count(*) n, round(avg(confidence),3) avg_conf,
                     sum((confidence>=0.5)::INT) n_conf05
                   FROM '{p}' WHERE categories.primary IN ({lst}) GROUP BY 1 ORDER BY n DESC""")
        alt = df(f"""SELECT count(*) n FROM '{p}'
                     WHERE categories.primary NOT IN ({lst})
                       AND list_has_any(categories.alternate, [{lst}])""").n[0]
        log(f"  [{k}] primary-category matches: {d.to_dict('records')} | alternate-only matches: {alt}")
    log("  basic_category top 15:")
    log(df(f"SELECT basic_category, count(*) n FROM '{p}' GROUP BY 1 ORDER BY n DESC LIMIT 15").to_string(index=False))

(OUT / "03_overture_layers.txt").write_text("\n".join(lines), encoding="utf-8")
