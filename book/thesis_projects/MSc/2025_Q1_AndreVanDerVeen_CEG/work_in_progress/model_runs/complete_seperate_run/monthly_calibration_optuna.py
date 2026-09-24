import yaml
import shutil
from pathlib import Path
import numpy as np
from datetime import datetime
import json
import platform
import subprocess
from ewatercycle.container import ContainerImage
import optuna
from optuna.samplers import TPESampler
from src.pcr_calibration_model_monthly import CalibrationObjective, normalize_params, denormalize_params
import io
from contextlib import redirect_stdout, redirect_stderr


def _to_dt_utc(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _get_git_commit_hash():
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def validate_config(config_dict):
    sim_start = _to_dt_utc(config_dict['model']['simulation_period']["start"])
    sim_end = _to_dt_utc(config_dict['model']['simulation_period']["end"])
    cal_start_dt = _to_dt_utc(config_dict['model']['calibration_period']["start"])
    cal_end_dt = _to_dt_utc(config_dict['model']['calibration_period']["end"])

    if sim_start > sim_end:
        raise ValueError("simulation_period.start must be <= simulation_period.end")
    if cal_start_dt > cal_end_dt:
        raise ValueError("calibration_period.start must be <= calibration_period.end")
    if cal_start_dt < sim_start or cal_end_dt > sim_end:
        raise ValueError("calibration period must be inside simulation period")

    stations_cfg = config_dict.get("stations", [])
    if not stations_cfg:
        raise ValueError("No stations configured in YAML")

    total_weight = 0.0
    for station in stations_cfg:
        weight = station.get("weight")
        if weight is None:
            weight = 1.0
        if float(weight) <= 0:
            raise ValueError(f"Station '{station.get('name', 'unknown')}' has non-positive weight: {weight}")
        total_weight += float(weight)
    if total_weight <= 0:
        raise ValueError("Total station weight must be > 0")

    cal_params = config_dict.get("calibration_parameters", {})
    if not cal_params:
        raise ValueError("No calibration_parameters configured in YAML")
    for name, param in cal_params.items():
        if "bounds" not in param or len(param["bounds"]) != 2:
            raise ValueError(f"Parameter '{name}' must define two-element bounds")
        lower, upper = float(param["bounds"][0]), float(param["bounds"][1])
        if lower >= upper:
            raise ValueError(f"Parameter '{name}' has invalid bounds: {param['bounds']}")
        initial = float(param.get("initial", lower))
        if not (lower <= initial <= upper):
            raise ValueError(f"Parameter '{name}' initial {initial} is outside bounds {param['bounds']}")

script_start_time = datetime.now()
print(f"Script started at: {script_start_time:%Y-%m-%d %H:%M:%S}")

config_path = Path("data/configs/template_monthly.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

validate_config(config)
print("Config preflight validation passed")

config_dir = config_path.parent

cal_start = config['model']['simulation_period']["start"]
cal_end = config['model']['simulation_period']["end"]
calibration_start = config['model']['calibration_period']["start"]
calibration_end = config['model']['calibration_period']["end"]

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
MODEL_VERSION = config["model"]["version"]

grdc_monthly_dir = (
    config_dir
    / config["paths"].get("grdc_monthly_dir", config["paths"]["grdc_daily_dir"])
).resolve()


FORCE_GC_AFTER_RUN = True
REMOVE_RUN_DIR_AFTER_EVAL = False

runtime_cfg = config.get("runtime", {})
objective_cfg = config.get("objective", {})
metric_weights_cfg = objective_cfg.get("station_metric_weights", {})

FORCE_GC_AFTER_RUN = runtime_cfg.get("force_gc_after_run", FORCE_GC_AFTER_RUN)
REMOVE_RUN_DIR_AFTER_EVAL = runtime_cfg.get("remove_run_dir_after_eval", REMOVE_RUN_DIR_AFTER_EVAL)
FAIL_OBJECTIVE_PENALTY = runtime_cfg.get("fail_objective_penalty", 999.0)
WRITE_RUN_MANIFEST = runtime_cfg.get("write_run_manifest", True)
WRITE_CANDIDATE_ROWS = runtime_cfg.get("write_candidate_rows", True)
RUNS_SUBDIR = runtime_cfg.get("runs_subdir", "runs")

NSE_WEIGHT = metric_weights_cfg.get("nse", 0.5)
KGE_WEIGHT = metric_weights_cfg.get("kge", 0.5)

MAX_ITER = config["optimizer"]["maxiter"]
POP_SIZE = config["optimizer"]["popsize"]
N_WORKERS = config["optimizer"]["n_workers"]
RUN_ID = config["experiment"]["run_id"]


# load stations
stations = []
for station in config["stations"]:
    weight = station.get("weight")
    if weight is None:
        weight = 1.0

    stations.append({
        "name": station["name"],
        "coords": {"lat": station["lat"], "lon": station["lon"]},
        "station_id": station["grdc_id"],
        "grdc_data_dir": grdc_monthly_dir,
        "weight": weight,
    })

print(f"Loaded {len(stations)} stations: {[s['name'] for s in stations]}")

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
    model_version=MODEL_VERSION,
    force_gc_after_run=FORCE_GC_AFTER_RUN,
    remove_run_dir_after_eval=REMOVE_RUN_DIR_AFTER_EVAL,
    frequency="monthly",
    calibration_start=calibration_start,
    calibration_end=calibration_end,
    fail_objective_penalty=FAIL_OBJECTIVE_PENALTY,
    nse_weight=NSE_WEIGHT,
    kge_weight=KGE_WEIGHT,
    runs_subdir=RUNS_SUBDIR,
    write_candidate_rows=WRITE_CANDIDATE_ROWS,
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
print(f"\nStarting Optuna: {len(param_names)} params, "
    f"maxiter={MAX_ITER}, popsize={POP_SIZE}, workers={N_WORKERS}")

# Enable verbose Optuna logging
optuna.logging.set_verbosity(optuna.logging.DEBUG)

# Create sampler and study with descriptive name
study_name = f"calibration_run_optuna_{RUN_ID}"
sampler = TPESampler(seed=RUN_ID * 1000)
storage_path = output_dir / f"{study_name}.db"
storage_name = f"sqlite:///{storage_path}"
study = optuna.create_study(
    sampler=sampler,
    direction='minimize',
    study_name=study_name,
    storage=storage_name,
    load_if_exists=True,
)

# Attach minimal metadata for reproducibility and provenance.
study.set_user_attr("run_id", int(RUN_ID))
study.set_user_attr("config_path", str(config_path.resolve()))
study.set_user_attr("output_dir", str(output_dir))
study.set_user_attr("script_start_time", script_start_time.isoformat())
study.set_user_attr("python_version", platform.python_version())
study.set_user_attr("numpy_version", np.__version__)
study.set_user_attr("optuna_version", optuna.__version__)

# Ensure the first candidate is deterministic per RUN_ID when starting a fresh study.
if len(study.trials) == 0:
    x0_trial = {name: float(value) for name, value in zip(param_names, x0_run)}
    study.enqueue_trial(x0_trial)

# Wrapper function for Optuna
def objective_optuna(trial):
    # Suggest parameters in [0, 1] using the real calibration names.
    x = np.array([
        trial.suggest_float(name, 0, 1)
        for name in param_names
    ])

    # Suppress CalibrationObjective's progress bar output.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        loss = obj(x)

    params_original = denormalize_params(x, CALIBRATION_PARAMS)
    params_original_dict = {
        name: float(value)
        for name, value in zip(param_names, params_original)
    }
    print(f"Trial {trial.number} finished with loss={loss:.6f}, parameters={params_original_dict}")
    return loss

# Run optimization with parallel workers
# Total trials = MAX_ITER * POP_SIZE
# Disable progress bar since parallel workers create messy output
study.optimize(objective_optuna, n_trials=MAX_ITER * POP_SIZE, 
               n_jobs=N_WORKERS, show_progress_bar=False)

# Extract results
best_params_normalized = np.array([study.best_params[name]
                                    for name in param_names])
best_params_original = denormalize_params(best_params_normalized, CALIBRATION_PARAMS)

print("\n" + "=" * 60)
print("OPTUNA CALIBRATION COMPLETE")
print("=" * 60)
print(f"Best objective: {study.best_value:.4f}")
print(f"Total function evaluations: {len(study.trials)}")
print("Best parameters (original scale):")
for i, name in enumerate(param_names):
    print(f"  {name}: {best_params_original[i]:.6f}")
print("Best parameters (normalized scale):")
for name in param_names:
    print(f"  {name}: {study.best_params[name]:.6f}")

trials_df = study.trials_dataframe(attrs=("number", "value", "params", "state"))
trials_csv = output_dir / f"{study.study_name}_trials.csv"
trials_df.to_csv(trials_csv, index=False)
print(f"Saved trials dataframe: {trials_csv}")

complete_trials = trials_df[trials_df["state"] == "COMPLETE"].copy()
if not complete_trials.empty:
    top_trials = complete_trials.nsmallest(min(10, len(complete_trials)), "value")
    top_trials_csv = output_dir / f"{study.study_name}_top_trials.csv"
    top_trials.to_csv(top_trials_csv, index=False)
    print(f"Saved top trials dataframe: {top_trials_csv}")

if WRITE_RUN_MANIFEST:
    manifest = {
        "script": str(Path(__file__).resolve()),
        "config_path": str(config_path.resolve()),
        "git_commit": _get_git_commit_hash(),
        "study_name": study.study_name,
        "storage": storage_name,
        "run_id": int(RUN_ID),
        "start_time": script_start_time.isoformat(),
        "n_trials_completed": len(study.trials),
        "n_workers": int(N_WORKERS),
        "max_iter": int(MAX_ITER),
        "pop_size": int(POP_SIZE),
        "objective_weights": {"nse": float(NSE_WEIGHT), "kge": float(KGE_WEIGHT)},
        "fail_objective_penalty": float(FAIL_OBJECTIVE_PENALTY),
        "runs_subdir": RUNS_SUBDIR,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "optuna_version": optuna.__version__,
    }
    manifest_path = output_dir / "run_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved run manifest: {manifest_path}")

script_end_time = datetime.now()
print(f"\nScript ended at: {script_end_time:%Y-%m-%d %H:%M:%S}")
print(f"Total runtime: {script_end_time - script_start_time}")
