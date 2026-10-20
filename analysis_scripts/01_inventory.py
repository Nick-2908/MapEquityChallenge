"""Inventory every parquet/csv in data/: size, rows, columns, geometry type."""
import json
import pathlib

import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis_outputs"
OUT.mkdir(exist_ok=True)

rows = []
for p in sorted(DATA.rglob("*")):
    if p.suffix not in (".parquet", ".csv", ".geojson") or "bulk" in p.name:
        continue
    rel = p.relative_to(DATA).as_posix()
    rec = {"path": rel, "size_mb": round(p.stat().st_size / 1e6, 2)}
    if p.suffix == ".parquet":
        f = pq.ParquetFile(p)
        md = f.metadata
        rec["rows"] = md.num_rows
        rec["n_cols"] = len(f.schema_arrow.names)
        rec["row_groups"] = md.num_row_groups
        rec["columns"] = [f"{fld.name}:{fld.type}" for fld in f.schema_arrow]
        geo = f.schema_arrow.metadata.get(b"geo") if f.schema_arrow.metadata else None
        if geo:
            g = json.loads(geo)
            col = g.get("primary_column")
            rec["geometry_types"] = g["columns"][col].get("geometry_types")
            crs = g["columns"][col].get("crs")
            rec["crs"] = crs.get("id") if isinstance(crs, dict) else crs
    elif p.suffix == ".csv":
        with open(p, encoding="utf-8") as fh:
            header = fh.readline().strip()
            n = sum(1 for _ in fh)
        rec["rows"] = n
        rec["n_cols"] = len(header.split(","))
    rows.append(rec)

with open(OUT / "inventory.json", "w", encoding="utf-8") as fh:
    json.dump(rows, fh, indent=1)

for r in rows:
    if r["path"].endswith(".csv") and r["path"].replace(".csv", ".parquet") in {x["path"] for x in rows}:
        continue
    print(f'{r["path"]:<75} {r["size_mb"]:>9.1f}MB rows={r.get("rows","?"):>9} cols={r.get("n_cols","?"):>4} '
          f'{r.get("geometry_types","")}')
