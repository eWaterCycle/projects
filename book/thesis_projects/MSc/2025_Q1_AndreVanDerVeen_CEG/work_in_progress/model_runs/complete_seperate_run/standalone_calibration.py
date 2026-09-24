import yaml
import shutil
from pathlib import Path
import numpy as np
from datetime import datetime
from ewatercycle.container import ContainerImage
import cma
from cma.optimization_tools import EvalParallel2
from src.pcr_calibration_model import CalibrationObjective, normalize_params, denormalize_params
import ewatercycle.observation.grdc

script_start_time = datetime.now()
print(f"Script started at: {script_start_time:%Y-%m-%d %H:%M:%S}")

config_path = Path("data/configs/template.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

config_dir = config_path.parent

cal_start = config['model']['calibration_period']["start"]
cal_end = config['model']['calibration_period']["end"]


CALIBRATION_PARAMS = config['calibration_parameters']

output_root = (config_dir / config["experiment"]["output_root"]).resolve()
output_tail = config["experiment"]["name"]
output_dir = output_root / output_tail
output_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(config_path, output_dir / config_path.name)
print(f"Copied config to output: {output_dir / config_path.name}")


template_ini = (config_dir / config["paths"]["template_ini"]).resolve()
params_dir = config["paths"]["params_dir"]
forcing_dir = (config_dir / config["paths"]["forcing_dir"]).resolve()
bmi_image = ContainerImage(config["model"]["bmi_image"])
study_area  = (config_dir / config["paths"]["clone_map"]).resolve()
SPINUP_DAYS = config['model']['spinup_days']
MODEL_VERSION = config["model"]["version"]


FORCE_GC_AFTER_RUN = True
REMOVE_RUN_DIR_AFTER_EVAL = False

MAX_ITER = config["optimizer"]["maxiter"]
POP_SIZE = config["optimizer"]["popsize"]
SIGMA0 = config["optimizer"]["sigma0"]
N_WORKERS = config["optimizer"]["n_workers"]
RUN_ID = config["experiment"]["run_id"]
N_CORES = N_WORKERS  # CMA-ES will use this many cores for parallel evaluation


# load stations
stations = []
for station in config["stations"]:
    obs = ewatercycle.observation.grdc.get_grdc_data(
        data_home=(config_dir / config["paths"]["grdc_daily_dir"]).resolve(),
        station_id=station["grdc_id"],
        start_time=cal_start,
        end_time=cal_end,
    )
    stations.append({
        "name": station["name"],
        "coords": {"lat": station["lat"], "lon": station["lon"]},
        "obs_data": obs,
        "weight": station.get("weight", 1.0),
    })

len(stations), [s["name"] for s in stations]

obj = CalibrationObjective(
    stations=stations,
    calibration_params=CALIBRATION_PARAMS,
    output_dir=output_dir,
    template_ini=template_ini,
    params_dir=params_dir,
    forcing_dir=forcing_dir,
    bmi_image=bmi_image,
    clone_map=study_area,
    landmask=study_area,
    cal_start=cal_start,
    cal_end=cal_end,
    spinup_days=SPINUP_DAYS,
    model_version=MODEL_VERSION,
    force_gc_after_run=FORCE_GC_AFTER_RUN,
    remove_run_dir_after_eval=REMOVE_RUN_DIR_AFTER_EVAL,
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
