# Example experiment script using CalibrationObjective from src.pcr_calibration_model.
# Copy and rename this file for each new experiment (e.g. experiment_chatly_routing.py).
# Only change the CALIBRATION_PARAMS block and the config section below.

import multiprocessing
import numpy as np
import os
from pathlib import Path
from datetime import datetime
import cma
from cma.optimization_tools import EvalParallel2

from src.constants import STATIONS_PCR
from src.paths import (
    FORCING_PCRGLOB, INI_FILES, LOAD_PCR, OUTPUT_PCRGLOB,
    PCR_GLOBAL_PARAMS, PCR_TAIL, GRDC
)
from src.pcr_calibration_model import CalibrationObjective, normalize_params, denormalize_params
import ewatercycle.observation.grdc
from ewatercycle.container import ContainerImage

script_start_time = datetime.now()
print(f"Script started at: {script_start_time:%Y-%m-%d %H:%M:%S}")

# =============================================================================
# EXPERIMENT CONFIG — edit this section for each new experiment
# =============================================================================

CALIBRATION_PARAMS = {
    'manningsN': {
        'section': 'routingOptions',
        'key': 'manningsN',
        'bounds': (0.01, 0.1),
        'initial': 0.04,
    },
    'floodplainManningsN': {
        'section': 'routingOptions',
        'key': 'floodplainManningsN',
        'bounds': (0.01, 0.1),
        'initial': 0.06,
    },
    'referenceepotFactor': {
        'section': 'meteoOptions',
        'key': 'referenceepotFactor',
        'bounds': (0.5, 2),
        'initial': 1.0,
    },
    'precipitationFactor': {
        'section': 'meteoOptions',
        'key': 'precipitationFactor',
        'bounds': (0.5, 2),
        'initial': 1.0,
    },
    'degreeDayFactor_forest': {
        'section': 'forestOptions',
        'key': 'degreeDayFactor',
        'bounds': (0.000001, 0.01),
        'initial': 0.0025,
    },
    'degreeDayFactor_grass': {
        'section': 'grasslandOptions',
        'key': 'degreeDayFactor',
        'bounds': (0.000001, 0.01),
        'initial': 0.0025,
    },
}

template_ini = INI_FILES / "test_comp_speed_basin_path.ini"
forcing_dir = FORCING_PCRGLOB / LOAD_PCR / PCR_TAIL
params_dir = PCR_GLOBAL_PARAMS
bmi_image = ContainerImage("/home/avandervee3/ewatercycle_pcr_17feb.sif")

# Support multiple independent runs — set CALIBRATION_RUN_ID env var to
# distinguish runs (e.g. CALIBRATION_RUN_ID=2 python experiment_example.py).
# Defaults to 1 so the script works unchanged when run directly.
RUN_ID = int(os.environ.get('CALIBRATION_RUN_ID', '1'))
output_dir = OUTPUT_PCRGLOB / f"calibration_runs_parallel_run{RUN_ID}"

cal_start = "1949-10-01T00:00:00Z"
cal_end = "1950-05-31T00:00:00Z"

# Add more stations here to calibrate against multiple points simultaneously.
# Use 'weight' to control how much each station contributes to the objective.
# STATIONS_GRDC maps station names to GRDC IDs — adjust to your setup.
STATIONS_GRDC = {
    "Chatly":   "2817100",
    "Garm" : "2517920",
}

tools_folder = Path("/home/avandervee3/MSc_AralSea/book/thesis_projects/MSc/2025_Q1_AndreVanDerVeen_CEG/work_in_progress/notebooks/tools")
total_area = tools_folder / "aral_basin_05min.map"

SPINUP_DAYS = 30

# CMA-ES settings
SIGMA0 = 0.2       # initial step size (20% of [0,1] range)
MAX_ITER = 5       # number of generations
N_CORES = multiprocessing.cpu_count()
N_WORKERS_DEFAULT = max(1, N_CORES - 1)
N_WORKERS = int(os.environ.get('N_WORKERS', N_WORKERS_DEFAULT))
if N_WORKERS < 1:
    raise ValueError(f"N_WORKERS must be >= 1, got {N_WORKERS}")

POP_MULTIPLIER = int(os.environ.get('POP_MULTIPLIER', '2'))
POP_SIZE_DEFAULT = N_WORKERS * POP_MULTIPLIER
POP_SIZE = int(os.environ.get('POP_SIZE', POP_SIZE_DEFAULT))
if POP_SIZE < 1:
    raise ValueError(f"POP_SIZE must be >= 1, got {POP_SIZE}")

# =============================================================================
# RUN
# =============================================================================

print(f"Calibrating {len(CALIBRATION_PARAMS)} parameters against {len(STATIONS_GRDC)} station(s), run ID={RUN_ID}")
for name, info in CALIBRATION_PARAMS.items():
    print(f"  {name}: {info['bounds']} (initial: {info['initial']})")
print(f"Stations: {list(STATIONS_GRDC.keys())} | Period: {cal_start} to {cal_end}")
print("Loading observations...")

# Load observations for all stations
stations = []
for name, station_id in STATIONS_GRDC.items():
    obs = ewatercycle.observation.grdc.get_grdc_data(
        data_home=GRDC / "Daily",
        station_id=station_id,
        start_time=cal_start,
        end_time=cal_end,
    )
    stations.append({
        'name': name,
        'coords': STATIONS_PCR[name],
        'obs_data': obs,
        'weight': 1.0,  # equal weighting; adjust per station if needed
    })

obj = CalibrationObjective(
    stations=stations,
    calibration_params=CALIBRATION_PARAMS,
    output_dir=output_dir,
    template_ini=template_ini,
    params_dir=params_dir,
    forcing_dir=forcing_dir,
    bmi_image=bmi_image,
    clone_map=total_area,
    landmask=total_area,
    cal_start=cal_start,
    cal_end=cal_end,
    spinup_days=SPINUP_DAYS,
)

param_names = list(CALIBRATION_PARAMS.keys())
x0_original = [CALIBRATION_PARAMS[p]['initial'] for p in param_names]
x0_normalized = normalize_params(np.array(x0_original), CALIBRATION_PARAMS)

# Perturb the starting point so independent runs explore different regions.
# The seed is deterministic per RUN_ID so results are reproducible.
np.random.seed(RUN_ID * 42)
perturbation = np.random.uniform(-0.05, 0.05, size=len(x0_normalized))
x0_run = np.clip(x0_normalized + perturbation, 0.0, 1.0)
print(f"Run {RUN_ID} starting point (perturbed): {x0_run.tolist()}")

lower_bounds = [0.0] * len(param_names)
upper_bounds = [1.0] * len(param_names)

options = {
    'maxiter': MAX_ITER,
    'popsize': POP_SIZE,
    'bounds': [lower_bounds, upper_bounds],
    'verb_disp': 1,
    'verb_log': 0,
    'tolfun': 1e-6,
    'seed': RUN_ID * 1000,  # different CMA-ES internal seed per run
}

print(f"\nStarting CMA-ES: {len(param_names)} params, sigma0={SIGMA0}, "
    f"maxiter={MAX_ITER}, popsize={POP_SIZE}, workers={N_WORKERS}, cores={N_CORES}")

es = cma.CMAEvolutionStrategy(x0_run.tolist(), SIGMA0, options)

# Run candidates in parallel with N_WORKERS processes.
# If POP_SIZE > N_WORKERS, evaluations are done in batches each generation.
# EvalParallel2 uses multiprocessing.Pool internally; obj must be picklable.
# (bound instance methods are not — but a __call__ on a picklable class is fine)
with EvalParallel2(obj, N_WORKERS) as eval_all:
    while not es.stop():
        X = es.ask()
        es.tell(X, eval_all(X))
        es.disp()

result = es.result
best_params_original = denormalize_params(np.array(result.xbest), CALIBRATION_PARAMS)

print("\n" + "=" * 60)
print("CMA-ES CALIBRATION COMPLETE")
print("=" * 60)
print(f"Best objective: {result.fbest:.4f}")
print(f"Total function evaluations: {result.evaluations}")
print("Best parameters (original scale):")
for i, name in enumerate(param_names):
    print(f"  {name}: {best_params_original[i]:.6f}")

script_end_time = datetime.now()
print(f"\nScript ended at: {script_end_time:%Y-%m-%d %H:%M:%S}")
print(f"Total runtime: {script_end_time - script_start_time}")
