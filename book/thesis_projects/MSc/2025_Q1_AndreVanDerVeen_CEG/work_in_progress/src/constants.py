"""Constants for the Aral Sea thesis project.

Includes:
- HBV model parameter bounds and defaults
- CMA-ES calibration settings
- CMIP6 model configurations
- PCR-GLOBWB grid settings
- Aral Sea model constants
"""

import numpy as np

# ==============================================================================
# HBV MODEL PARAMETERS
# ==============================================================================
# --------------------------
# Dummy parameters placeholder

DUMMY_HBV_PARAMS = [
    7.085,  # Imax
    0.837,  # Ce
    76.373,  # Sumax
    1.112,  # Beta
    0.245,  # Pmax
    7.801,  # Tlag
    0.096,  # Kf
    0.003,  # Ks
    0.226,  # FM
]

# Initial conditions placeholder
DUMMY_HBV_INITIAL = np.array(
    [
        0,  # Si
        100,  # Su
        0,  # Sf
        5,  # Ss
        0,  # Sp
    ]
)

PARAMETER_NAMES = [
    "Imax",  # 0
    "Ce",  # 1
    "Sumax",  # 2
    "Beta",  # 3
    "Pmax",  # 4
    "Tlag",  # 5
    "Kf",  # 6
    "Ks",  # 7
    "FM",  # 8
]

INITIAL_CONDITION_NAMES = [
    "Si",  # 0
    "Su",  # 1
    "Sf",  # 2
    "Ss",  # 3
    "Sp",  # 4
]

HBV_PARAM_BOUNDS = {
    "min": np.array([0, 0.2, 40, 0.5, 0.001, 1, 0.01, 0.0001, 0.01]),
    "max": np.array([25, 1, 800, 4, 0.3, 15, 0.02, 0.01, 0.8]),
}

# Parameter names for the model (descriptive)
PARAMETER_NAMES_LONG = [
    "Imax_interception_max_storage",  # 0: Maximum interception storage (mm)
    "Ce_effective_precipitation_coeff",  # 1: Effective precipitation coefficient (-)
    "Sumax_max_soil_moisture",  # 2: Maximum soil moisture storage (mm)
    "Beta_shape_coefficient",  # 3: Shape coefficient (-)
    "Pmax_max_percolation_rate",  # 4: Maximum percolation rate (mm/day)
    "Tlag_lag_time",  # 5: Lag time for response (days)
    "Kf_fast_flow_recession",  # 6: Fast flow recession coefficient (1/day)
    "Ks_slow_flow_recession",  # 7: Slow flow recession coefficient (1/day)
    "FM_fraction_melt",  # 8: Fraction of snowmelt contributing to flow (-)
]

# Initial condition names for the model (descriptive)
INITIAL_CONDITION_NAMES_LONG = [
    "Si_initial_interception_storage",  # 0: Initial interception storage (mm)
    "Su_initial_upper_zone_storage",  # 1: Initial upper zone storage (mm)
    "Sf_initial_fast_flow_storage",  # 2: Initial fast flow storage (mm)
    "Ss_initial_slow_flow_storage",  # 3: Initial slow flow storage (mm)
    "Sp_initial_percolation_storage",  # 4: Initial percolation storage (mm)
]

TYUMEN_ARYK_HBV_PARAMS_CMAES = [
    0.222612,  # Imax
    0.473759,  # Ce
    721.898890,  # Sumax
    1.939276,  # Beta
    0.283583,  # Pmax
    7.902570,  # Tlag
    0.010001,  # Kf
    0.005879,  # Ks
    0.790641,  # FM
]


# ==============================================================================
# CMA-ES CALIBRATION SETTINGS
# ==============================================================================
CMAES_DEFAULT_POPSIZE = 15
CMAES_DEFAULT_MAXFEVALS = 500
CMAES_DEFAULT_SIGMA = 0.1  # Initial step size (normalized space)


# Objective function weights
OBJECTIVE_WEIGHTS = {
    "nse": 0.3,
    "kge": 0.3,
    "volume_error": 0.4,
}

# ==============================================================================
# CLIMATE MODEL SETTINGS
# ==============================================================================
# Default CMIP6 models
DEFAULT_CMIP6_MODELS = {
    "historical": "MPI-ESM1-2-HR",
    "future": "MPI-ESM1-2-HR",  # , EC-Earth3
}

# SSP scenarios
SSP_SCENARIOS = ["ssp126", "ssp245", "ssp585"]  # these have the best data coverage


# ==============================================================================
# PCR-GLOBWB SETTINGS
# ==============================================================================
# Grid resolution requirements
PCRGLOBWB_RESOLUTION_MULTIPLE = 3  # degrees, for get_integer_multiple_bounds
PCRGLOBWB_ESMVALTOOL_PADDING = 2  # degrees, padding for forcing extraction

STATIONS_PCR = {
    "Chatly": {"lat": 42.2, "lon": 60.2},
    "Kazalinsk": {"lat": 45.7, "lon": 62.12},
    "Kerki": {"lat": 37.83, "lon": 65.30},
    "Tyumen-Aryk": {"lat": 43.95, "lon": 67.05},
    #"Karaozek": {"lat": 44.95, "lon": 65.27},
    "Uch-Kurgan": {"lat": 41.12, "lon": 72.10},
    "Garm": {"lat": 39.05, "lon": 70.33},
}


# ==============================================================================
# Aral Sea Model Constants
# ==============================================================================
MAKKINK_FACTOR = (
    1.00 # Makkink correction factor (dimensionless) for open water evaporation estimation
    # add source for this: range is 1.0 to 1.2? Might be open pan vs dynamic surface water?
)
GROUNDWATER_INFLOW = 1 / 365

# ==============================================================================
# Koppen-Geiger
# ==============================================================================
KOPPEN_CLASSES = [
    "Af",
    "Am",
    "Aw",
    "BWh",
    "BWk",
    "BSh",
    "BSk",
    "Csa",
    "Csb",
    "Csc",
    "Cwa",
    "Cwb",
    "Cwc",
    "Cfa",
    "Cfb",
    "Cfc",
    "Dsa",
    "Dsb",
    "Dsc",
    "Dsd",
    "Dwa",
    "Dwb",
    "Dwc",
    "Dwd",
    "Dfa",
    "Dfb",
    "Dfc",
    "Dfd",
    "ET",
    "EF",
]

KOPPEN_RGB_COLORS = (
    np.array(
        [
            [0, 0, 255],
            [0, 120, 255],
            [70, 170, 250],
            [255, 0, 0],
            [255, 150, 150],
            [245, 165, 0],
            [255, 220, 100],
            [255, 255, 0],
            [200, 200, 0],
            [150, 150, 0],
            [150, 255, 150],
            [100, 200, 100],
            [50, 150, 50],
            [200, 255, 80],
            [100, 255, 80],
            [50, 200, 0],
            [255, 0, 255],
            [200, 0, 200],
            [150, 50, 150],
            [150, 100, 150],
            [170, 175, 255],
            [90, 120, 220],
            [75, 80, 180],
            [50, 0, 135],
            [0, 255, 255],
            [55, 200, 255],
            [0, 125, 125],
            [0, 70, 95],
            [178, 178, 178],
            [102, 102, 102],
        ],
        dtype=float,
    )
    / 255
)

KOPPEN_DESCRIPTION = {
    "Af": "Tropical rainforest",
    "Am": "Tropical monsoon",
    "Aw": "Tropical savanna",
    "BWh": "Hot desert",
    "BWk": "Cold desert",
    "BSh": "Hot steppe",
    "BSk": "Cold steppe",
    "Csa": "Mediterranean, hot summer",
    "Csb": "Mediterranean, warm summer",
    "Csc": "Mediterranean, cold summer",
    "Cwa": "Temperate, dry winter, hot summer",
    "Cwb": "Temperate, dry winter, warm summer",
    "Cwc": "Temperate, dry winter, cold summer",
    "Cfa": "Temperate, no dry season, hot summer",
    "Cfb": "Temperate, no dry season, warm summer",
    "Cfc": "Temperate, no dry season, cold summer",
    "Dsa": "Snow, dry summer, hot summer",
    "Dsb": "Snow, dry summer, warm summer",
    "Dsc": "Snow, dry summer, cold summer",
    "Dsd": "Snow, dry summer, very cold summer",
    "Dwa": "Snow, dry winter, hot summer",
    "Dwb": "Snow, dry winter, warm summer",
    "Dwc": "Snow, dry winter, cold summer",
    "Dwd": "Snow, dry winter, very cold winter",
    "Dfa": "Snow, no dry season, hot summer",
    "Dfb": "Snow, no dry season, warm summer",
    "Dfc": "Snow, no dry season, cold summer",
    "Dfd": "Snow, no dry season, very cold winter",
    "ET": "Tundra",
    "EF": "Ice cap",
}
