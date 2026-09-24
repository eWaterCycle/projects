"""Module defining paths used throughout the project."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ------------------------------
# Project Root
# ------------------------------
ROOT = Path(__file__).resolve().parents[1]  # work_in_progress

# ------------------------------
# Data folders
# ------------------------------
DATA = ROOT / "data"
GRDC = DATA / "grdc"
BATHYMETRY = DATA / "bathymetry"
SHAPEFILES = DATA / "shapefiles"
KOPPEN_GEIGER = DATA / "koppen_geiger_tif"

DAHITI = DATA / "dahiti"
# ------------------------------
# Forcing
# ------------------------------
FORCING_FOLDER = ROOT / "forcing"
FORCING_OUTPUT = FORCING_FOLDER / "output"

FORCING_ERA5 = FORCING_OUTPUT / "ERA5"
FORCING_CMIP_HIST = FORCING_OUTPUT / "CMIP_HIST"
FORCING_CMIP_FUT = FORCING_OUTPUT / "CMIP_FUT"
FORCING_PCRGLOB = FORCING_OUTPUT / "PCRGLOBWB"


PCR_GLOBAL_PARAMS = Path("/data/shared/parameter-sets/pcrglobwb_global")
if not PCR_GLOBAL_PARAMS.exists():
    logger.warning(
        f"PCR_GLOBAL_PARAMS not found at {PCR_GLOBAL_PARAMS}. "
        "This code requires eWaterCycle server access."
    )
# ------------------------------
# Outputs
# ------------------------------
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
KOPPEN_FIGURES = FIGURES / "koppen_geiger"

TABLES = OUTPUTS / "tables"
MODEL_OUTPUT = OUTPUTS / "model_runs"
OUTPUT_HBV = MODEL_OUTPUT / "HBV"
OUTPUT_PCRGLOB = MODEL_OUTPUT / "pcr-globwb"


# ------------------------------
# Notebooks
# ------------------------------
NOTEBOOKS = ROOT / "notebooks"

# ------------------------------
# Model Runs (intermediate folders)
# ------------------------------
MODEL_RUNS = ROOT / "model_runs"
RUNS_HBV = MODEL_RUNS / "HBV"
RUNS_LB = MODEL_RUNS / "leakybucket"
RUNS_PCR = MODEL_RUNS / "pcrglobwb"
INI_FILES = RUNS_PCR / "ini_files"
INI_COMPARISON = INI_FILES / "comparison_files"

PCR_TAIL = Path("work/diagnostic/script")
LOAD_PCR = Path("ERA5_1940-1960/AralSea_basin")


# ------------------------------
# Specific Model Runs
# ------------------------------

PCR_TEST_ARAL = (
    RUNS_PCR / "aral_sea_water_levels/pcrglobwb_20260210_112853/netcdf/discharge_dailyTot_output.nc"
)
