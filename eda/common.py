"""Shared paths, region labels and plot style for the EDA notebooks (run notebooks from eda/)."""
import pathlib
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = next(p for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents] if (p / "data").exists())
DATA, REF, STR, BND, OUT = ROOT / "data", ROOT / "data" / "reference", ROOT / "data" / "strata", ROOT / "data" / "boundaries", ROOT / "eda_outputs"
REG = ["maricopa-az", "northern-ca", "eastern-ok", "south-central-tx", "eastern-wa"]
SCORED = REG[:4]  # the four regions the challenge names; eastern-wa ships in the package but is not scored
NAME = {"maricopa-az": "Maricopa AZ", "northern-ca": "Northern CA", "eastern-ok": "Eastern OK", "south-central-tx": "S-C Texas", "eastern-wa": "Eastern WA"}
COL = dict(zip(REG, ["#e07b39", "#c0504d", "#6a9e4f", "#3b6fb6", "#8e6bbf"]))
plt.rcParams.update({"figure.dpi": 100, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": .25, "axes.titlesize": 11, "axes.labelsize": 9, "figure.autolayout": True})
pd.set_option("display.width", 200, "display.max_columns", 60, "display.max_rows", 80, "display.float_format", "{:,.3f}".format)


def tracts_parquet(name, region=None):
    """Path of a strata file: national table or one region."""
    return STR / (region or "national") / f"{region or 'national'}-{name}.parquet"
