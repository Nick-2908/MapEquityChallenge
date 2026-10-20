# Bias Bounty Mapping Equity Challenge — Data Analysis

*Analysis date: 2026-10-20. Scope: understanding the competition and the data only. No modelling approach chosen yet.*
*All numbers are reproducible from `analysis_scripts/01–05_*.py`. Raw outputs are in `analysis_outputs/`.*

---

## 0. Key findings (TL;DR)

1. **This is a regression task scored by RMSE against hidden targets that we cannot compute.** The organisers built each tract's `coverage_gap_score` from TIGER roads, Microsoft footprints, HIFLD/USGS facilities and Census CBP. All four were **deliberately removed** from the package. Re-creating them, or fetching them elsewhere, is **explicitly prohibited**. We have to predict the target from the permitted features.
2. **Zindi scores 4 regions with 9,379 tracts.** The bucket ships a 5th region, `eastern-wa` (415 tracts), that Zindi doesn't mention ("All scored tracts fall within these four regions"). Zindi's own `SampleSubmission.csv` is **919,898 bytes**, much larger than the five per-region sample CSVs combined (~275 KB). So its format (columns, ID style, row count) is unknown and still needs checking.
3. **The regions are much bigger than their names.** "Maricopa" is 90% of Arizona's tracts, "South-Central TX" is 87% of Texas (including Houston, Dallas–Fort Worth and Austin), and "Eastern OK" is 99% of Oklahoma. **Texas is 64% of the 9,379 Zindi-scored tracts**, so it will dominate RMSE.
4. **Overture buildings already contain Microsoft ML footprints.** They make up 69% of Eastern OK buildings, 51% of Northern CA, 44% of TX, 38% of WA and 14% of Maricopa. Microsoft is the building reference the target was computed against. In rural tracts of OK, CA and TX, 73–87% of buildings come from Microsoft; in OK tribal tracts it's 80%.
5. **`carbonplan_buildings` (in strata) is essentially an Overture building count.** The ratio to our Overture count has a median of 0.998, and the Spearman correlation is 1.000. It is **not** an independent reference. `usfs_BuildingCount_sum` *is* independent and tracks Overture closely (median ratio 1.02, ρ = 0.956). Its provenance (possibly derived from footprints) should be checked against the "no equivalent copies" rule before it is used.
6. **ACS housing units are a poor building proxy.** Rural tracts have about 2 Overture buildings per housing unit and urban tracts about 1. The organisers explicitly excluded ACS from the building ratio for this reason.
7. **Overture has highway-class roads (motorway, trunk, primary, secondary) in about 98% of tracts.** Yet Zindi says 21–55% of tracts have at least one *undefined* component, mostly because TIGER has no S1100/S1200 road there. **Whether the transport component is defined can't be read off Overture directly.**
8. **Target facility POIs are sparse.** A `fire_department` POI exists in only 23–36% of tracts and an `ambulance_and_ems_services` POI in 4–9%. Per-type facility gaps are therefore near-binary or small-integer ratios. Many more EMS-like POIs sit only in `categories.alternate` than in `primary`.
9. **Edge cases exist in the scored set:** 2 Texas tracts that are 100% water with **zero** Overture features of any kind are still scored. There are also 27 zero-population tracts, 82 tracts with zero housing units, 43 tracts that are more than 50% water, and tracts ranging from under 0.5 km² to over 1,000 km².
10. **The "tribal" stratum is effectively Eastern Oklahoma.** 805 of the 874 tribal tracts (92%) are in OK, mostly in statistical OTSAs. 429 of them are *urban* (for example, the Creek OTSA includes Tulsa). Texas has a single tribal tract.

---

## 1. The competition

| Item | Detail |
|---|---|
| Name | Bias Bounty Mapping Equity Challenge (Humane Intelligence × Zindi; geospatial support from Radiant Earth) |
| Question | "Are the communities most vulnerable to climate risk also the least well-mapped?" |
| Unit | 2020 US Census tract (`GEOID`, 11-character **string**) |
| Target | `coverage_gap_score` ∈ [0, 1]: 0 = full Overture coverage, 1 = no coverage |
| Metric | **RMSE** against organiser-computed reference scores. Public LB ≈ 30% of tracts, private ≈ 70%. |
| Submission | CSV with `GEOID` + `coverage_gap_score`. Component columns are optional, but **no blank cells** in any included column. 10/day, 300 total. Pick 2 for the private LB. |
| Deadline | Submissions close **2026-10-31 23:29 UTC** (11 days from today). Leaderboard sealed 2026-11-21. |
| Prizes | $4,500 / $2,500 / $1,500 (leaderboard). **Best Bias Discovery $1,000** and **Best Documentation $500** are judged from a methodology write-up, no leaderboard rank needed. |
| Participation | ~1,300 registered, 302 on the leaderboard. Teams of up to 4. |
| Bias scorecard | Every submission gets an automatic Bias Score with 5 metrics: Coverage Disparity Ratio, POI Desert Index, Emergency Access Gap, Road Network Equity Ratio and Climate-Justice Composite. They're broken down by urban/rural, SVI, CVI, tribal and hazard exposure. **It does not affect ranking.** |

### 1.1 How the hidden target was built (from Zindi Evaluation page + bucket README)

Three components, each of the form `1 − min(1, overture / reference)` per tract. This form is explicit in the README for POIs; for the other two it is implied by "compare … per tract". Component definitions:

| Component | Overture side | Reference side (REMOVED from package) | Undefined when |
|---|---|---|---|
| `transport_gap` | Road **length**, classes `motorway`, `trunk`, `primary`, `secondary` | TIGER/Line roads, MTFCC **S1100 + S1200** | Tract has no TIGER S1100/S1200 road |
| `building_gap` | Building **count** | Microsoft US Building Footprints count (ACS is *not* used) | No Microsoft footprint in tract |
| `poi_gap` | Mean of 2 halves. **Facilities half:** mean over the defined types fire (`fire_department`), EMS (`ambulance_and_ems_services`) and schools (`elementary_school`, `middle_school`, `high_school`, `school`, `private_school`, `public_school`), each against HIFLD/USGS National Map counts. **Establishments half:** *all* Overture places vs CBP establishments. Hospitals are excluded because Overture has about 12× HIFLD's count. | HIFLD/USGS facilities, CBP | No facility of a type, or no establishments |

- **`coverage_gap_score` = mean of the *defined* components only.** The divisor is 1–3. Tracts with all three undefined are dropped from the scored list.
- Share of tracts with **≥ 1 undefined component** (Zindi): Eastern OK 21%, Northern CA 37%, South-Central TX 28%, **Maricopa 55%**. That last one is mostly "no named-highway road".
- The Overture/TIGER highway length ratio ranges from **0.71 to 1.59 across regions**. Transport gaps are explicitly *not comparable across regions*.
- Per the README, the fire-station term "carries" the facility half: EMS is close to 1:1 and rarely binds, and hospitals were removed.
- CBP is not published at tract level, so the organisers must have allocated it somehow (ZIP or county). **The method is not documented.**

### 1.2 Rules that constrain the work

- **Prohibited target reconstruction.** No use of TIGER, Microsoft Buildings, HIFLD or CBP, "or equivalent copies obtained elsewhere", to reproduce or approximate the targets.
- The scored submission may use **only the datasets provided**. External public data is allowed **only** for the Best Bias Discovery write-up, and must be documented.
- Only open-source tools. **AutoML is not permitted.** Seeds must be fixed and the code reproducible, because the top 10 are code-reviewed within 48 h. LLM coding assistants are OK as long as they aren't needed to *run* the solution.
- Must use the Overture release **2026-08-19.0**, which is the one shipped.

---

## 2. Data acquisition & integrity

| Item | Status |
|---|---|
| `data/bulk-downloads_reference.zip` | 4,517,510,250 B. Matches the server size. **It was truncated (4.41 GB) after the previous session and has been resumed and completed.** Extracts cleanly to `data/reference/`. |
| `data/bulk-downloads_strata.zip` | 1,694,666,582 B. Matches the server size. Extracted to `data/strata/` (266 files). |
| `data/boundaries/` | Not in either zip. Downloaded separately: region AOIs, `all-aois.geojson`, `original-rings.geojson`, `<region>-tract-geoids.csv`. |
| `data/README.md` | Bucket README (dated 2026-09-25). |
| Not available anywhere | The `<region>-coverage-gap.csv` reference files mentioned in the README (these are the targets), the Zindi `SampleSubmission.csv` (needs a Zindi login), and the "data dictionary" mentioned on the Zindi data page. |

**Stale documentation to be aware of:** the Zindi data page still lists the reference layers as present in `reference/` and quotes old sizes (`reference.zip` 6.39 GB). Both were changed on 2026-09-25, when those layers were removed and `eastern-wa` was added.

Environment: a project venv at `.venv` (Python 3.13) with pandas 3.0, pyarrow 26, DuckDB 1.5.6 + spatial, and geopandas 1.2. The machine has 16 GB RAM and 16 threads.

---

## 3. What's in the package

### 3.1 Reference layers (per region, `data/reference/<region>/`)

| Region | Tracts scored | Buildings | Road segments (scored) | Road segs (unfiltered) | Rail segs | Infrastructure | POIs |
|---|---:|---:|---:|---:|---:|---:|---:|
| maricopa-az | 1,593 | 2,908,224 | 494,492 | 1,170,165 | 3,830 | 9,482 | 300,046 |
| northern-ca | 591 | 1,164,724 | 191,836 | 479,596 | 2,006 | 3,318 | 116,897 |
| eastern-ok | 1,192 | 2,551,694 | 520,550 | 1,037,555 | 5,066 | 2,726 | 207,369 |
| south-central-tx | 6,003 | 11,463,801 | 1,937,009 | 4,122,701 | 17,895 | 13,622 | 1,300,334 |
| eastern-wa | 415 | 1,081,346 | 142,649 | 383,136 | 3,473 | 4,131 | 76,491 |
| **Total** | **9,794** | **19,169,789** | **3,286,536** | 7,193,153 | 32,270 | 33,279 | **2,001,137** |

Each region also has `census-acs-housing` (`GEOID`, `housing_units` from ACS B25001 2020–24, tract polygon) and a `sample-submission.csv`. The sample CSV has columns `GEOID, transport_gap, building_gap, poi_gap, coverage_gap_score`, with every value 0.0.

Format: GeoParquet 1.1, CRS `OGC:CRS84` (lon/lat), with a `bbox` struct column. Every feature is clipped at the region boundary, and that boundary follows whole tracts.

### 3.2 Strata (`data/strata/national/` = 85,396 tracts; `data/strata/<region>/` = the same tables subset)

- `national-strata-tract-table` (**232 columns**) joins every source. Column groups by prefix: census spine (pop, `ur_class`, `pct_urban`, ALAND/AWATER), `svi_` (9), `cvi_` (13), `ruca_` (6), `rucc_` (5), `nchs_` (4), `tribal_`/`aiannh_` (9), `usdm_` (9), `usfs_` (23), `epht_` (8), `carbonplan_` (10), `usgs_` (13), `mtbs_` (11), `nifc_` (12), `fod_` (16), `ghcn_` (11), `cdcw_`/`hwd_` (19), `gehe_` (13), `uhe_` (7), `pmdi_` (7), `spi*` (10), `drought_gov_` (2).
- Per-source tables carry more detail (for example 174 cols for NASA heat, 161 for drought.gov, 124 for CDC WONDER, 98 for USFS).
- **Region strata tables have 227 columns.** They **drop `AWATER`, `INTPTLAT/LON`, `state_*` and `tract_vintage`**, so water share has to come from the national table.
- Tribal geometry layers (AIANNH, tribal tracts and subdivisions) keep whole features, so they extend beyond the regions.

---

## 4. The scored tract set

- In every region: sample-submission GEOIDs = boundary tract list = `census-tracts` = region strata = ACS. **The exception is Texas**, where 7 water tracts (`48xxx990000`) appear in boundaries/ACS/strata but **not** in the sample submission.
- All GEOIDs are 11 characters with no duplicates and no overlap between regions. `frac_inside_aoi` = 1.0 for every tract.
- Maricopa includes one New Mexico tract, `35023970000`.

| Region | Tracts | % of its state's tracts | Counties | Population | % Rural (`ur_class`) | Tribal tracts |
|---|---:|---:|---:|---:|---:|---:|
| maricopa-az | 1,593 | 90% of AZ | 16 (15 AZ + 1 NM) | 6.61 M | 10.3% | 37 (2.3%) |
| northern-ca | 591 | 6% of CA | 24 | 2.46 M | 24.9% | 15 (2.5%) |
| eastern-ok | 1,192 | 99% of OK | 73 | 3.93 M | 34.5% | **805 (67.5%)** |
| south-central-tx | 6,003 | 87% of TX | 185 | 25.76 M | 16.5% | 1 |
| eastern-wa | 415 | 23% of WA | 27 | 1.68 M | 34.1% | 16 (3.9%) |

The largest Texas counties by tract count are Harris (1,094), Dallas (645), Tarrant (449), Bexar (375), Travis (290), Collin (220), Hidalgo (212) and Denton (193).

---

## 5. Strata profile of the scored tracts

**Urban/rural.** By `ur_class`: 7,914 Urban, 1,853 Rural, 27 null. By RUCA primary: 7,012 tracts are code 1 (metro core) and 664 are code 10 (rural). `pct_urban` is bimodal: most tracts are exactly 0 or 1. NCHS and RUCC are county-level and coarser.

**Tribal (`tribal_any`).**
- **eastern-ok: 805 tracts**, almost all *statistical* OTSAs: Creek 256, Cherokee 152, Chickasaw 93, Choctaw 67, Kiowa-Comanche-Apache 63 and others. **429 of these are Urban** (the Creek OTSA includes Tulsa).
- **maricopa-az: 37** legal reservations, for example Navajo, Tohono O'odham, Fort Apache and Gila River.
- **eastern-wa: 16**, mainly Yakama. **northern-ca: 15**, many with tiny overlap (median `tribal_pct` 0.04). **south-central-tx: 1** (Kickapoo, 2.75% overlap).

**SVI / CVI.** Both are 100% covered. `svi_overall` is null in 0–1.8% of tracts (tracts with zero or low population). CVI ranges 0.33–0.74.

**Hazards (median per region):**

| Region | Summer drought DSCI | Wildfire hazard (USFS WHP) | WBGT ≥ 28 days/yr (NASA GEHE) | Summer EPHT heat days |
|---|---:|---:|---:|---:|
| maricopa-az | 176 | 66 | 82.6 | 15.1 |
| northern-ca | **216** | **108** | 7.3 | 11.0 |
| eastern-ok | 63 | 13 | 33.8 | 11.3 |
| south-central-tx | 85 | 19 | 59.6 | 15.2 |
| eastern-wa | 114 | 51 | 0.06 | 11.3 |

**Missingness.** 79 of 232 columns have nulls in the scored set, but most are **structural** rather than random:
- `usgs_*`, `mtbs_*_year` and `nifc_*_year` are null for tracts that have never burned (49–96% of tracts).
- `fod_*` shares are null with no ignitions (3–63%).
- `uhe_*` is null outside urban heat-extreme cities (31–62%).
- `aiannh_*` is null for non-tribal tracts.
- `spi_calibration` is entirely null.

Every `*_covered` flag is 100% except `uhe_covered`.

---

## 6. Overture layer profiles

### 6.1 Buildings: who supplied them (first entry of `sources`)

| Region | OpenStreetMap | **Microsoft ML** | Esri Community Maps | Google Open Buildings |
|---|---:|---:|---:|---:|
| maricopa-az | 79.7% | 14.3% | 4.7% | 1.3% |
| northern-ca | 46.6% | **50.8%** | 2.6% | — |
| eastern-ok | 16.7% | **69.4%** | 14.0% | — |
| south-central-tx | 51.0% | 44.3% | 2.4% | 2.2% |
| eastern-wa | 55.9% | 38.1% | 6.0% | — |

- Microsoft rows carry `update_time` from 2000 to 2024. `confidence` is present on only 0.7–30% of Microsoft rows (mean about 0.97) and on 100% of Google rows (about 0.79). OSM and Esri rows never have confidence. Esri rows are all dated 2025.
- **By stratum (mean tract share from Microsoft):**
  - Rural ≫ Urban everywhere, for example OK 0.87 vs 0.52, NorCal 0.73 vs 0.36, TX 0.73 vs 0.32.
  - Tribal > non-tribal: OK 0.80 vs 0.30 and Maricopa 0.46 vs 0.12.
  - RUCA 7–10 tracts in OK and TX are about 0.80–0.91 Microsoft.
  - In OK, *urban tribal* tracts (Tulsa area) are 74% Microsoft, compared with 25% in urban non-tribal tracts (Oklahoma City area). OKC is instead heavy in Esri Community Maps: Esri averages 42% of buildings in non-tribal OK tracts.
- Height is present on 70–82% of buildings (from USGS Lidar or Microsoft). `subtype`/`class` are mostly null (62–94%). Under 1% of buildings are named.
- Median footprint is 144–219 m². 1.6–4.6% of footprints are under 20 m².

### 6.2 Roads (scored layer: drivable classes only)

- 99.9% of segments come from OpenStreetMap; about 0.1% from TomTom. Around 0.1% are MultiLineStrings.
- Total km: Maricopa 123k, NorCal 76k, OK 210k, TX 571k, WA 79k.
- **Highway classes (motorway/trunk/primary/secondary), km and share of road length:** Maricopa 22.1k (17.9%), NorCal 11.7k (15.4%), OK 27.7k (13.2%), TX 115.7k (20.3%), WA 12.0k (15.2%).
- Motorways are often unnamed in `names.primary` (only 11–39% have a name).
- The `roads-unfiltered` layer adds large amounts of `service` road (driveways, parking aisles) and `track`. For example Maricopa has 99.8k km of track, more than its whole scored network. Service km per housing unit is about 4–8× higher in rural tracts than urban ones.
- Length check: EPSG:5070 planar length and spheroidal length agree to within 0.015% (on 20k NorCal segments).

### 6.3 Rail & infrastructure

- Rail is mostly `standard_gauge`, plus a large `unknown` class. Light rail exists in Maricopa, NorCal and TX. 38–76% of tracts have no rail.
- Infrastructure is mostly `bus_stop`. **Transit coverage is very uneven:** OK has only 1,979 bus stops and TX only 10,516 bus stops for 25.8M people. **81% of OK tracts and 77% of TX tracts have no transit feature**, compared with about 40% in AZ, CA and WA. Airport and helipad points are also present.

### 6.4 POIs (places)

- 4–6% of POIs have no `categories.primary`. Median `confidence` is 0.92; 10–12% are below 0.5. 2.0–2.7% are `permanently_closed`, and about 30% have a null `operating_status`.
- Every POI lists source `Overture` plus 1–2 upstream sources, mainly meta, Microsoft, BrightQuery and Foursquare.
- **Target facility categories (`categories.primary` counts):**

| Region | fire_department | ambulance_and_ems_services | schools (6 cats) | hospital | Fire POIs per 100k pop |
|---|---:|---:|---:|---:|---:|
| maricopa-az | 462 | 73 | 3,501 | 758 | **7.0** |
| northern-ca | 289 | 38 | 1,724 | 350 | 11.8 |
| eastern-ok | 576 | 123 | 3,069 | 733 | 14.7 |
| south-central-tx | 2,135 | 559 | 15,429 | 3,524 | 8.3 |
| eastern-wa | 179 | 44 | 1,131 | 196 | 10.7 |

- **Many relevant POIs are only in `categories.alternate`.** For EMS, alternate-only matches outnumber primary ones by 2–4× (for example TX 1,228 vs 559). For fire the ratio is 0.2–0.4×. The organiser's target uses `categories.primary` only.
- Top primary categories are generic: `real_estate_agent`, `health_and_medical`, `church_cathedral`, `automotive_repair`, `beauty_salon`, and so on.

---

## 7. Tract-level coverage proxies (Overture spatially joined to tracts)

Method: buildings are assigned by centroid. Scored roads and rail use exact line-in-polygon intersection length (EPSG:5070). Unfiltered roads use a representative point on the line. POIs use point-in-polygon. Our tract areas match ALAND+AWATER exactly (median ratio 1.0000). Output: `analysis_outputs/tract_analysis_table.parquet`, with 9,794 rows and Overture aggregates, ACS and strata joined.

### 7.1 How often a tract has *none* of a feature in Overture

| Region | No buildings | No hwy-class road | No motorway/trunk | No fire POI | No EMS POI | No school POI | No fire+EMS+school | No transit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| maricopa-az | 0% | 2.1% | 63.0% | 76.6% | 95.9% | 26.1% | 20.3% | 39.2% |
| northern-ca | 0% | 1.2% | 49.7% | 64.1% | 94.9% | 15.2% | 12.7% | 39.3% |
| eastern-ok | 0% | 2.5% | 44.1% | 63.8% | 91.4% | 19.5% | 14.2% | 80.7% |
| south-central-tx | 0.03% (2) | 1.1% | 45.4% | 71.2% | 92.0% | 21.5% | 16.5% | 76.5% |
| eastern-wa | 0% | 1.2% | 48.9% | 67.2% | 90.8% | 17.1% | 13.5% | 40.2% |

Every tract has some POIs and drivable roads; the only exceptions are the two all-water Texas tracts. Tracts with no motorway/trunk/primary road: 13.7–21.2%.

### 7.2 Building counts vs the independent counts available in the package

| Ratio (Overture `bldg_n` / X), median [p10–p90] | maricopa-az | northern-ca | eastern-ok | south-central-tx | eastern-wa |
|---|---|---|---|---|---|
| / ACS housing units | 0.98 [0.59–1.58] | 1.06 [0.64–1.98] | 1.34 [0.76–2.53] | 1.04 [0.38–2.01] | 1.41 [0.85–2.69] |
| / `usfs_BuildingCount_sum` | 1.01 [0.94–1.21] | 1.02 [0.93–1.16] | 1.02 [0.93–1.42] | 1.02 [0.91–1.34] | 1.14 [1.05–1.31] |
| / `carbonplan_buildings` | 0.999 [0.991–1.007] | 0.997 [0.987–1.009] | 0.998 [0.989–1.002] | 0.998 [0.987–1.005] | 0.998 [0.991–1.007] |

- **`carbonplan_buildings` duplicates Overture's own count.** Spearman ρ = 1.000 and the log-correlation is 0.999–1.000 in every region. CarbonPlan v1.1.0 evidently counted Overture buildings from a nearby release, so it is not independent. The small ratio differences reflect release-to-release churn.
- **`usfs_BuildingCount_sum` is genuinely different but highly correlated** (ρ = 0.956; log r = 0.96–0.99). Overture/USFS < 0.9 occurs in only 0.2–9% of tracts. It deserves a provenance check before use (see §9).
- **ACS housing units are only loosely related** (ρ = 0.48). The buildings-per-housing-unit ratio is strongly driven by urbanity (ρ = −0.68 with `pct_urban`, +0.60 with RUCA). Rural tracts have about 2 buildings per housing unit (outbuildings and barns); dense urban tracts have fewer than 1 (apartments). 491 TX tracts have fewer than 0.3 buildings per housing unit.
- Microsoft-sourced building counts are *negatively* correlated with OSM-sourced counts (ρ = −0.41). The two substitute for each other in Overture's conflation.

### 7.3 Proxies by stratum (medians)

- **Road density** (km per km² of land) is the strongest strata-linked signal: ρ = +0.81 with `pct_urban`, −0.66 with RUCA and −0.64 with wildfire hazard (WHP). Rural is about 0.6–1.4 km/km² and urban about 9–11.
- **Highway share of road km** is lower in rural tracts (0.12–0.18 vs 0.16–0.23).
- **POIs per 1k population** are flat across urban and rural (30–47). They *rise* with SVI: in OK, Q1 has 30 and Q4 has 55. **POIs per 100 buildings** are about 2–3× lower in rural tracts and fall with wildfire hazard (ρ = −0.39).
- **Fire-station POI presence is higher in rural tracts** (46–62% of rural tracts vs 21–28% of urban). Rural tracts are larger, so they are more likely to contain a station.
- **Tribal vs non-tribal (OK):** POIs per 100 buildings 5.7 vs 8.5; road density 3.0 vs 9.6 km/km².

### 7.4 Edge cases in the scored set

| | maricopa-az | northern-ca | eastern-ok | south-central-tx | eastern-wa |
|---|---:|---:|---:|---:|---:|
| Zero population | 11 | 0 | 1 | 14 | 1 |
| Zero ACS housing units | 27 | 0 | 10 | 43 | 2 |
| Water > 50% of area | 0 | 2 | 1 | 40 | 0 |
| Land < 0.5 km² | 8 | 9 | 10 | 140 | 0 |
| Land > 1,000 km² | 61 | 36 | 28 | 94 | 49 |
| Zero Overture buildings | 0 | 0 | 0 | 2 | 0 |

- **`48039990000` and `48057990000`** are 100% water and have 0 buildings, 0 road km and 0 POIs in Overture, yet they *are* scored. The organisers drop tracts with all components undefined, so these two must have at least one reference feature (for example a TIGER highway or bridge, or a CBP allocation).
- Zero-population tracts other than the two water tracts (mostly `…98xxxx` special-use tracts such as parks, airports and bases) still have 2–1,112 buildings and some POIs.

---

## 8. What the definitions + data imply about the target (observations, not an approach)

- **The target is clipped at 0.** Each component is `1 − min(1, ratio)`, so wherever Overture ≥ reference the component is exactly 0. Expect a large mass at or near 0 plus a tail. RMSE will be dominated by the tail and by Texas.
- **The per-tract divisor (1–3 components) varies and isn't observable.** It depends on whether TIGER, Microsoft, HIFLD or CBP had *any* feature in the tract. Overture's highway classes exist in about 98% of tracts, so they don't reveal transport-definedness. Motorway/trunk/primary presence (79–86% of tracts) is closer but still doesn't match Zindi's figures.
- **Building component:** Overture *contains* Microsoft footprints wherever OSM/Esri/Google didn't cover a building. In Microsoft-dominated tracts (rural, tribal, most of OK), Overture's count should be at or above the Microsoft count, which would make the gap about 0. Gaps are more plausible where OSM or Esri footprints *replaced* Microsoft ones with fewer polygons, or where Microsoft footprints were dropped in conflation. This is a hypothesis we can't test directly with the available data.
- **Facility half of the POI component:** with 0–6 fire stations per tract, values are discrete (0, ⅓, ½, ⅔, 1, …), and the fire term is defined only where the reference has a station.
- **Establishments half:** all Overture places (median 120–151 per tract) are compared with allocated CBP counts. The allocation method is unknown.
- **Transport values differ systematically by region** because of different class conventions (ratio 0.71–1.59). Region is likely an important effect.

---

## 9. Risks, gotchas and open questions

**Rules / compliance**
- Don't use TIGER, Microsoft Buildings, HIFLD or CBP from anywhere, including indirect "equivalent copies".
- **`usfs_BuildingCount_sum` / `usfs_HUCount_sum`** come from USFS Wildfire Risk to Communities rasters, which are built from building-footprint and housing data. They are provided *by the organisers* as strata, but if they were derived from Microsoft footprints, using them as a building-gap denominator could be read as approximating the reference. **This needs a provenance check, or a question to the organisers, before relying on it.**
- `carbonplan_buildings` is effectively Overture's own count from a nearby release, so it adds no independent information.

**Data gotchas (all verified)**
- Read `GEOID` as a string from CSVs (Maricopa is FIPS `04`).
- DuckDB: use `always_xy := true` in `ST_Transform` and `ST_FlipCoordinates` before `*_Spheroid`. Otherwise the results are silently inf or NaN.
- Region strata tables omit `AWATER`; use `strata/national/` for water share.
- Overture `bbox` was regenerated in GeoParquet order (`xmin, ymin, xmax, ymax`).
- A struct or list `len()` returning NULL can silently skew `avg()`. The "% with web/phone/route" figures in `03_overture_layers.txt` are invalid for this reason and are excluded here.

**Open questions (for you / the organisers)**
1. **Is `eastern-wa` scored?** Zindi says four regions; the bucket has five.
2. **What exactly does Zindi's `SampleSubmission.csv` (919,898 B) contain?** Column names, ID format and row count (9,379 or 9,794). It needs to be downloaded from the Zindi Data page while logged in, so the submission writer can match it exactly.
3. How was CBP allocated to tracts? Is there a "data dictionary" (mentioned on the Zindi page but not in the package)?
4. Are the USFS building/housing counts acceptable features under the reconstruction rule?

---

## 10. Reproducibility

The analysis scripts were replaced by Jupyter notebooks in `notebooks/` (run top to bottom from that folder; they read the data straight out of `data/*.zip` where possible).

| Notebook | Produces / covers |
|---|---|
| `01_inventory` | `inventory_parquet_footers.csv`: every parquet's size, rows and columns, read from the zip footers |
| `02_tracts_and_strata` | `02_tracts_and_strata.txt`, `scored_tracts_strata.parquet` |
| `03_overture_layers` | `03_overture_layers.txt` (needs `duckdb`; extracts the Overture layers from the zip first) |
| `04_tract_aggregates` | `tract_overture_aggregates.parquet` and `agg_<region>.parquet` (DuckDB spatial joins, about 20 min; needs `duckdb`) |
| `05_tract_analysis` | `05_tract_analysis.txt`, `tract_analysis_table.parquet` |
| `06_glm_framework` | correlation / ANOVA / regression / ANCOVA as one GLM; ML case study; builds `model_frame.parquet` |
| `07_data_preparation` | statistical tests, imputation, transformations, feature selection, before/after case study |
| `08_generalized_linear_models` | logistic vs Poisson vs negative binomial |
| `09_time_series` | monthly series of Overture building update times: smoothing, regression, ADF/KPSS, ARIMA/SARIMA/SARIMAX (`building_update_monthly.parquet`) |
| `10_monte_carlo_mcmc` | Monte Carlo convergence, permutation/bootstrap, target-construction simulation, Metropolis-Hastings |
| `11_causal_basics` | Simpson's paradox, potential outcomes, DAGs, adjustment, front-door, assumptions |
| `12_causal_classical` | PSM, stratification, IPW, doubly robust, RDD, DID (simulated) |
| `13_causal_ml` | meta-learners, DML, DML-IV, uplift, causal trees/forests, PC discovery, predictive vs causal case study |

Notebooks 06-13 use *proxy* outcomes (POIs per building, presence of a fire POI, a USFS-based building gap), not the hidden competition target, and need only the committed parquet files in `analysis_outputs/`. Notebooks 02 and 05 were re-run after conversion; 03 and 04 were converted but not re-run (their committed outputs come from the original scripts).
