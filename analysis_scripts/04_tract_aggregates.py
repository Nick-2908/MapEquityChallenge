"""Per-tract aggregates of every Overture layer for the scored tracts (spatial joins in DuckDB).

Output: analysis_outputs/tract_overture_aggregates.parquet (one row per scored GEOID).
Buildings/POIs/infrastructure are assigned by point (centroid / the point itself); scored roads and
rail by exact line-polygon intersection length; unfiltered roads by a representative on-line point
(approximation).
"""
import pathlib
import sys
import time

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis_outputs"
REGIONS = sys.argv[1:] or ["northern-ca", "eastern-wa", "eastern-ok", "maricopa-az", "south-central-tx"]

con = duckdb.connect()
con.sql("LOAD spatial; SET memory_limit='7GB'; SET threads=12; SET preserve_insertion_order=false;")
con.sql(f"SET temp_directory='{(OUT / 'duckdb_tmp').as_posix()}'")

M = "ST_Transform({g}, 'EPSG:4326', 'EPSG:5070', always_xy := true)"
SCHOOLS = "['elementary_school','middle_school','high_school','school','private_school','public_school']"
HWY = "('motorway','trunk','primary','secondary')"


def f(r, layer):
    return (DATA / f"reference/{r}/{r}-overture-{layer}.parquet").as_posix()


def timed(label, sql):
    t = time.time()
    con.sql(sql)
    print(f"   {label}: {time.time() - t:.1f}s", flush=True)


for r in REGIONS:
    print(f"[{r}]", flush=True)
    sub = (DATA / f"reference/{r}/{r}-sample-submission.csv").as_posix()
    timed("tracts", f"""
        CREATE OR REPLACE TABLE tr AS
        SELECT t.GEOID, t.geometry
        FROM '{(DATA / f"strata/{r}/{r}-census-tracts.parquet").as_posix()}' t
        WHERE t.GEOID IN (SELECT GEOID FROM read_csv('{sub}', types={{'GEOID':'VARCHAR'}}))""")

    timed("buildings", f"""
        CREATE OR REPLACE TABLE b AS
        WITH pts AS (
            SELECT ST_Centroid(geometry) pt, sources[1].dataset ds,
                   ST_Area({M.format(g='geometry')}) area_m2,
                   height IS NOT NULL OR num_floors IS NOT NULL has_h
            FROM '{f(r, 'buildings')}')
        SELECT tr.GEOID,
               count(*) bldg_n,
               sum(area_m2) bldg_area_m2,
               median(area_m2) bldg_area_median_m2,
               count(*) FILTER (WHERE area_m2 < 30) bldg_n_lt30m2,
               count(*) FILTER (WHERE ds = 'OpenStreetMap') bldg_n_osm,
               count(*) FILTER (WHERE ds = 'Microsoft ML Buildings') bldg_n_msft,
               count(*) FILTER (WHERE ds = 'Google Open Buildings') bldg_n_google,
               count(*) FILTER (WHERE ds ILIKE '%esri%') bldg_n_esri,
               count(*) FILTER (WHERE ds NOT IN ('OpenStreetMap','Microsoft ML Buildings','Google Open Buildings')
                                AND ds NOT ILIKE '%esri%') bldg_n_other,
               count(*) FILTER (WHERE has_h) bldg_n_with_height
        FROM pts JOIN tr ON ST_Contains(tr.geometry, pts.pt)
        GROUP BY 1""")

    timed("roads (exact intersection)", f"""
        CREATE OR REPLACE TABLE rd AS
        WITH x AS (
            SELECT tr.GEOID, s."class" cls,
                   ST_Length({M.format(g='ST_Intersection(tr.geometry, s.geometry)')})/1000 km
            FROM '{f(r, 'roads')}' s JOIN tr ON ST_Intersects(tr.geometry, s.geometry))
        SELECT GEOID,
               sum(km) road_km_all,
               sum(km) FILTER (WHERE cls IN {HWY}) road_km_hwy,
               sum(km) FILTER (WHERE cls='motorway') road_km_motorway,
               sum(km) FILTER (WHERE cls='trunk') road_km_trunk,
               sum(km) FILTER (WHERE cls='primary') road_km_primary,
               sum(km) FILTER (WHERE cls='secondary') road_km_secondary,
               sum(km) FILTER (WHERE cls='tertiary') road_km_tertiary,
               sum(km) FILTER (WHERE cls='residential') road_km_residential,
               sum(km) FILTER (WHERE cls='unclassified') road_km_unclassified,
               count(*) road_n_pieces
        FROM x GROUP BY 1""")

    timed("roads-unfiltered (midpoint)", f"""
        CREATE OR REPLACE TABLE ru AS
        WITH s AS (
            SELECT "class" cls, ST_PointOnSurface(geometry) pt,
                   ST_Length({M.format(g='geometry')})/1000 km
            FROM '{f(r, 'roads-unfiltered')}')
        SELECT tr.GEOID,
               sum(km) ru_km_all,
               sum(km) FILTER (WHERE cls='service') ru_km_service,
               sum(km) FILTER (WHERE cls='track') ru_km_track,
               sum(km) FILTER (WHERE cls IN ('footway','path','cycleway','pedestrian','steps','bridleway')) ru_km_nonmotor,
               sum(km) FILTER (WHERE cls IS NULL OR cls='unknown') ru_km_unknown
        FROM s JOIN tr ON ST_Contains(tr.geometry, s.pt)
        GROUP BY 1""")

    timed("rail", f"""
        CREATE OR REPLACE TABLE rl AS
        SELECT tr.GEOID, sum(ST_Length({M.format(g='ST_Intersection(tr.geometry, s.geometry)')})/1000) rail_km
        FROM '{f(r, 'rail')}' s JOIN tr ON ST_Intersects(tr.geometry, s.geometry)
        GROUP BY 1""")

    timed("infrastructure", f"""
        CREATE OR REPLACE TABLE inf AS
        WITH p AS (SELECT subtype, "class" cls, ST_PointOnSurface(geometry) pt FROM '{f(r, 'infrastructure')}')
        SELECT tr.GEOID, count(*) infra_n,
               count(*) FILTER (WHERE subtype='transit') infra_n_transit,
               count(*) FILTER (WHERE subtype='airport') infra_n_airport
        FROM p JOIN tr ON ST_Contains(tr.geometry, p.pt) GROUP BY 1""")

    timed("pois", f"""
        CREATE OR REPLACE TABLE po AS
        WITH p AS (
            SELECT geometry pt, categories.primary cat, categories.alternate alt, confidence conf,
                   basic_category, operating_status
            FROM '{f(r, 'pois')}')
        SELECT tr.GEOID,
               count(*) poi_n,
               count(*) FILTER (WHERE conf >= 0.5) poi_n_conf05,
               count(*) FILTER (WHERE conf >= 0.8) poi_n_conf08,
               count(*) FILTER (WHERE operating_status IS NULL OR operating_status = 'open') poi_n_open,
               count(*) FILTER (WHERE cat = 'fire_department') poi_n_fire,
               count(*) FILTER (WHERE cat = 'ambulance_and_ems_services') poi_n_ems,
               count(*) FILTER (WHERE list_contains({SCHOOLS}, cat)) poi_n_school,
               count(*) FILTER (WHERE cat = 'hospital') poi_n_hospital,
               count(*) FILTER (WHERE cat <> 'fire_department' AND list_contains(alt, 'fire_department')) poi_n_fire_alt,
               count(*) FILTER (WHERE cat IS NULL) poi_n_nocat,
               count(DISTINCT cat) poi_n_distinct_cat
        FROM p JOIN tr ON ST_Contains(tr.geometry, p.pt) GROUP BY 1""")

    con.sql(f"""
        COPY (
          SELECT '{r}' region, tr.GEOID,
                 ST_Area({M.format(g='tr.geometry')})/1e6 tract_area_km2,
                 b.* EXCLUDE (GEOID), rd.* EXCLUDE (GEOID), ru.* EXCLUDE (GEOID),
                 rl.* EXCLUDE (GEOID), inf.* EXCLUDE (GEOID), po.* EXCLUDE (GEOID)
          FROM tr
          LEFT JOIN b USING (GEOID) LEFT JOIN rd USING (GEOID) LEFT JOIN ru USING (GEOID)
          LEFT JOIN rl USING (GEOID) LEFT JOIN inf USING (GEOID) LEFT JOIN po USING (GEOID)
        ) TO '{(OUT / f"agg_{r}.parquet").as_posix()}' (FORMAT parquet)""")
    print(f"   wrote agg_{r}.parquet", flush=True)

con.sql(f"""COPY (SELECT * FROM '{(OUT / "agg_*.parquet").as_posix()}')
            TO '{(OUT / "tract_overture_aggregates.parquet").as_posix()}' (FORMAT parquet)""")
print("done")
