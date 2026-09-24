"""Complete PCR-GLOBWB calibration pipeline.

This script expands the six high-level calibration steps into a runnable flow:
1. Load YAML settings.
2. Validate settings.
3. Resolve and check required files.
4. Load or verify forcing data.
5. Load observations.
6. Run CMA-ES calibration.

The script reuses existing project utilities in src.pcr_calibration_model.
"""

from __future__ import annotations

import argparse
import ast
import multiprocessing
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml


# Ensure project root is importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from src.constants import STATIONS_PCR


@dataclass(frozen=True)
class CalibrationPaths:
	"""Resolved paths required for a calibration run."""

	template_ini: Path
	forcing_dir: Path
	params_dir: Path
	clone_map: Path
	landmask: Path
	grdc_daily_dir: Path
	bmi_image: Path
	output_dir: Path


def log_step(step_number: int, message: str) -> None:
	"""Print a consistent step message."""
	print(f"\nStep {step_number}/6 - {message}")


def load_settings(config_path: Path) -> dict[str, Any]:
	"""Load run settings from YAML."""
	if not config_path.exists():
		raise FileNotFoundError(f"Configuration file not found: {config_path}")

	with config_path.open("r", encoding="utf-8") as handle:
		data = yaml.safe_load(handle)

	if not isinstance(data, dict):
		raise ValueError("Configuration root must be a YAML mapping.")

	return data


def _get_nested(mapping: dict[str, Any], keys: list[str]) -> Any:
	"""Get a nested value, returning None if a key path is missing."""
	current: Any = mapping
	for key in keys:
		if not isinstance(current, dict) or key not in current:
			return None
		current = current[key]
	return current


def validate_settings(settings: dict[str, Any]) -> None:
	"""Validate required settings and their basic types/constraints."""
	errors: list[str] = []

	required_top_level = [
		"version",
		"experiment",
		"model",
		"paths",
		"stations",
		"optimizer",
		"runtime",
		"objective",
		"calibration_parameters",
	]
	for key in required_top_level:
		if key not in settings:
			errors.append(f"Missing top-level key: '{key}'")

	if errors:
		raise ValueError("Invalid configuration:\n- " + "\n- ".join(errors))

	checks = [
		(["experiment", "name"], str),
		(["experiment", "run_id"], int),
		(["experiment", "output_root"], str),
		(["model", "version"], str),
		(["model", "bmi_image"], str),
		(["model", "calibration_period", "start"], str),
		(["model", "calibration_period", "end"], str),
		(["model", "spinup_days"], int),
		(["paths", "template_ini"], str),
		(["paths", "forcing_dir"], str),
		(["paths", "params_dir"], str),
		(["paths", "clone_map"], str),
		(["paths", "landmask"], str),
		(["paths", "grdc_daily_dir"], str),
		(["optimizer", "algorithm"], str),
		(["optimizer", "sigma0"], (int, float)),
		(["optimizer", "maxiter"], int),
		(["optimizer", "tolfun"], (int, float)),
		(["calibration_parameters"], dict),
	]

	for path, expected_type in checks:
		value = _get_nested(settings, path)
		if value is None:
			errors.append(f"Missing setting: {'.'.join(path)}")
			continue
		if not isinstance(value, expected_type):
			errors.append(
				f"Setting {'.'.join(path)} must be of type {expected_type}, got {type(value)}"
			)

	if settings.get("optimizer", {}).get("algorithm", "").lower() != "cmaes":
		errors.append("optimizer.algorithm must be 'cmaes'.")

	stations = settings.get("stations", [])
	if not isinstance(stations, list) or not stations:
		errors.append("stations must be a non-empty list.")
	else:
		for idx, station in enumerate(stations):
			if not isinstance(station, dict):
				errors.append(f"stations[{idx}] must be a mapping.")
				continue
			for required in ["name", "grdc_id"]:
				if required not in station:
					errors.append(f"stations[{idx}] is missing '{required}'.")

	cal_params = settings.get("calibration_parameters", {})
	if not cal_params:
		errors.append("calibration_parameters cannot be empty.")
	else:
		for name, cfg in cal_params.items():
			if not isinstance(cfg, dict):
				errors.append(f"calibration_parameters.{name} must be a mapping.")
				continue

			ini_section = cfg.get("ini_section", cfg.get("section"))
			ini_key = cfg.get("ini_key", cfg.get("key"))
			bounds = cfg.get("bounds")
			initial = cfg.get("initial")

			if not isinstance(ini_section, str) or not ini_section:
				errors.append(f"calibration_parameters.{name}.ini_section is required.")
			if not isinstance(ini_key, str) or not ini_key:
				errors.append(f"calibration_parameters.{name}.ini_key is required.")
			if not isinstance(bounds, list) or len(bounds) != 2:
				errors.append(f"calibration_parameters.{name}.bounds must be [min, max].")
			else:
				lower, upper = bounds
				if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
					errors.append(f"calibration_parameters.{name}.bounds must be numeric.")
				elif lower >= upper:
					errors.append(
						f"calibration_parameters.{name}.bounds must satisfy min < max."
					)
			if not isinstance(initial, (int, float)):
				errors.append(f"calibration_parameters.{name}.initial must be numeric.")

	objective_weights = _get_nested(settings, ["objective", "station_metric_weights"])
	if isinstance(objective_weights, dict):
		for key in ["nse", "kge"]:
			if key not in objective_weights:
				errors.append(f"objective.station_metric_weights missing '{key}'.")
			elif not isinstance(objective_weights[key], (int, float)):
				errors.append(f"objective.station_metric_weights.{key} must be numeric.")

	if errors:
		raise ValueError("Invalid configuration:\n- " + "\n- ".join(errors))


def _unique_paths(paths: list[Path]) -> list[Path]:
	"""Deduplicate paths while preserving order."""
	unique: list[Path] = []
	seen: set[str] = set()
	for path in paths:
		normalized = str(path)
		if normalized in seen:
			continue
		seen.add(normalized)
		unique.append(path)
	return unique


def _candidate_paths(raw: Path, key: str, config_dir: Path) -> list[Path]:
	"""Build path candidates for a configured value, including project fallbacks."""
	candidates: list[Path] = []

	if raw.is_absolute():
		candidates.append(raw)
	else:
		candidates.extend(
			[
				(config_dir / raw),
				(config_dir.parent / raw),
				(config_dir.parent.parent / raw),
				(PROJECT_ROOT / raw),
				(Path.cwd() / raw),
			]
		)

	try:
		from src import paths as thesis_paths

		if key == "template_ini":
			candidates.append(thesis_paths.INI_FILES / raw.name)
		elif key == "forcing_dir":
			candidates.append(
				thesis_paths.FORCING_PCRGLOB / thesis_paths.LOAD_PCR / thesis_paths.PCR_TAIL
			)
		elif key == "params_dir":
			candidates.append(Path(thesis_paths.PCR_GLOBAL_PARAMS))
		elif key in {"clone_map", "landmask"}:
			candidates.append(PROJECT_ROOT / "notebooks" / "tools" / raw.name)
		elif key == "grdc_daily_dir":
			candidates.append(thesis_paths.GRDC / "Daily")
	except Exception:
		# Fall back to only explicit configured candidates.
		pass

	resolved_candidates: list[Path] = []
	for path in candidates:
		path = path.expanduser()
		try:
			resolved_candidates.append(path.resolve())
		except Exception:
			resolved_candidates.append(path)

	return _unique_paths(resolved_candidates)


def resolve_path(config_value: str, key: str, config_dir: Path) -> Path:
	"""Resolve a path value; prefer the first candidate that exists."""
	raw = Path(config_value)
	candidates = _candidate_paths(raw=raw, key=key, config_dir=config_dir)
	for candidate in candidates:
		if candidate.exists():
			return candidate
	return candidates[0]


def build_output_dir(experiment_cfg: dict[str, Any]) -> tuple[Path, int]:
	"""Build and create output directory from experiment configuration."""
	run_id = int(os.environ.get("CALIBRATION_RUN_ID", experiment_cfg["run_id"]))
	output_root = Path(experiment_cfg["output_root"])
	if not output_root.is_absolute():
		output_root = PROJECT_ROOT / output_root

	timestamp = datetime.now().strftime(experiment_cfg.get("timestamp_format", "%Y%m%d_%H%M%S"))
	output_naming = experiment_cfg.get("output_naming", "{name}/run_{run_id}_{timestamp}")
	output_tail = output_naming.format(
		name=experiment_cfg["name"],
		run_id=run_id,
		timestamp=timestamp,
	)

	output_dir = (output_root / output_tail).resolve()
	output_dir.mkdir(parents=True, exist_ok=True)
	return output_dir, run_id


def resolve_calibration_paths(settings: dict[str, Any], config_path: Path) -> tuple[CalibrationPaths, int]:
	"""Resolve all runtime file paths from the configuration."""
	config_dir = config_path.parent
	paths_cfg = settings["paths"]

	output_dir, run_id = build_output_dir(settings["experiment"])

	resolved = CalibrationPaths(
		template_ini=resolve_path(paths_cfg["template_ini"], "template_ini", config_dir),
		forcing_dir=resolve_path(paths_cfg["forcing_dir"], "forcing_dir", config_dir),
		params_dir=resolve_path(paths_cfg["params_dir"], "params_dir", config_dir),
		clone_map=resolve_path(paths_cfg["clone_map"], "clone_map", config_dir),
		landmask=resolve_path(paths_cfg["landmask"], "landmask", config_dir),
		grdc_daily_dir=resolve_path(paths_cfg["grdc_daily_dir"], "grdc_daily_dir", config_dir),
		bmi_image=resolve_path(settings["model"]["bmi_image"], "bmi_image", config_dir),
		output_dir=output_dir,
	)
	return resolved, run_id


def check_required_files(paths: CalibrationPaths) -> None:
	"""Check presence of required files and directories."""
	missing: list[str] = []

	required_files = {
		"template_ini": paths.template_ini,
		"clone_map": paths.clone_map,
		"landmask": paths.landmask,
		"bmi_image": paths.bmi_image,
	}
	required_dirs = {
		"forcing_dir": paths.forcing_dir,
		"params_dir": paths.params_dir,
		"grdc_daily_dir": paths.grdc_daily_dir,
	}

	for key, path in required_files.items():
		if not path.is_file():
			missing.append(f"{key}: expected file, found missing path -> {path}")

	for key, path in required_dirs.items():
		if not path.is_dir():
			missing.append(f"{key}: expected directory, found missing path -> {path}")

	if missing:
		raise FileNotFoundError("Required inputs are missing:\n- " + "\n- ".join(missing))


def prepare_forcing(forcing_dir: Path, skip_eager_load: bool = False) -> None:
	"""Step 4: Load forcing object or do a lightweight forcing directory check."""
	if skip_eager_load:
		nc_count = sum(1 for _ in forcing_dir.rglob("*.nc"))
		if nc_count == 0:
			raise FileNotFoundError(
				f"No NetCDF files found in forcing directory: {forcing_dir}"
			)
		print(f"Forcing check passed: found {nc_count} NetCDF file(s) in {forcing_dir}")
		return

	try:
		import ewatercycle.forcing
	except ImportError as exc:
		raise RuntimeError(
			"Unable to import ewatercycle.forcing. Install eWaterCycle packages first."
		) from exc

	_ = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(directory=forcing_dir)
	print(f"Forcing loaded successfully from {forcing_dir}")


def resolve_station_coordinates(station_cfg: dict[str, Any]) -> dict[str, float]:
	"""Resolve station coordinates from config or STATIONS_PCR lookup."""
	if "lat" in station_cfg and "lon" in station_cfg:
		return {"lat": float(station_cfg["lat"]), "lon": float(station_cfg["lon"])}

	station_key = station_cfg.get("station_key", station_cfg["name"])
	if station_key not in STATIONS_PCR:
		raise KeyError(
			f"No coordinates found for station_key='{station_key}'. "
			f"Add lat/lon in YAML or use one of: {sorted(STATIONS_PCR.keys())}"
		)
	return STATIONS_PCR[station_key]


def load_observations(
	station_configs: list[dict[str, Any]],
	grdc_daily_dir: Path,
	start_time: str,
	end_time: str,
) -> list[dict[str, Any]]:
	"""Step 5: Load GRDC observations for configured stations."""
	try:
		import ewatercycle.observation.grdc
	except ImportError as exc:
		raise RuntimeError(
			"Unable to import ewatercycle.observation.grdc. Install eWaterCycle packages first."
		) from exc

	stations: list[dict[str, Any]] = []
	for station_cfg in station_configs:
		station_name = station_cfg["name"]
		station_id = str(station_cfg["grdc_id"])
		coords = resolve_station_coordinates(station_cfg)

		print(f"Loading observations for {station_name} (GRDC {station_id})")
		obs = ewatercycle.observation.grdc.get_grdc_data(
			data_home=grdc_daily_dir,
			station_id=station_id,
			start_time=start_time,
			end_time=end_time,
		)

		if "streamflow" not in obs:
			raise ValueError(
				f"Observation dataset for station {station_name} does not contain 'streamflow'."
			)

		stations.append(
			{
				"name": station_name,
				"coords": coords,
				"obs_data": obs,
				"weight": float(station_cfg.get("weight", 1.0)),
			}
		)

	return stations


def normalize_calibration_parameters(raw_params: dict[str, Any]) -> dict[str, dict[str, Any]]:
	"""Normalize calibration parameter schema to the format expected by objective class."""
	normalized: dict[str, dict[str, Any]] = {}
	for name, cfg in raw_params.items():
		section = cfg.get("section", cfg.get("ini_section"))
		key = cfg.get("key", cfg.get("ini_key"))
		lower, upper = cfg["bounds"]
		normalized[name] = {
			"section": str(section),
			"key": str(key),
			"bounds": (float(lower), float(upper)),
			"initial": float(cfg["initial"]),
		}
	return normalized


def evaluate_int_formula(expression: Any, run_id: int) -> int:
	"""Safely evaluate a simple integer expression with run_id as variable."""
	if isinstance(expression, (int, float)):
		return int(expression)

	expr = str(expression).strip()
	tree = ast.parse(expr, mode="eval")
	allowed_nodes = (
		ast.Expression,
		ast.BinOp,
		ast.UnaryOp,
		ast.Add,
		ast.Sub,
		ast.Mult,
		ast.Div,
		ast.FloorDiv,
		ast.Mod,
		ast.Pow,
		ast.UAdd,
		ast.USub,
		ast.Constant,
		ast.Name,
		ast.Load,
	)

	for node in ast.walk(tree):
		if not isinstance(node, allowed_nodes):
			raise ValueError(f"Unsupported expression in formula: {expression}")
		if isinstance(node, ast.Name) and node.id != "run_id":
			raise ValueError(f"Unsupported variable '{node.id}' in formula: {expression}")

	value = eval(compile(tree, filename="<formula>", mode="eval"), {"__builtins__": {}}, {"run_id": run_id})
	if not isinstance(value, (int, float)):
		raise ValueError(f"Formula did not produce a numeric value: {expression}")
	return int(value)


def determine_workers_and_population(optimizer_cfg: dict[str, Any]) -> tuple[int, int, int]:
	"""Determine number of workers and population size."""
	n_cores = multiprocessing.cpu_count()

	workers_cfg = optimizer_cfg.get("workers", {})
	worker_mode = workers_cfg.get("mode", "auto")
	explicit_workers = workers_cfg.get("explicit_n_workers")
	reserve_cores = int(workers_cfg.get("reserve_cores", 1))

	if worker_mode == "auto" or explicit_workers is None:
		n_workers = max(1, n_cores - reserve_cores)
	else:
		n_workers = int(explicit_workers)

	if "N_WORKERS" in os.environ:
		n_workers = int(os.environ["N_WORKERS"])
	if n_workers < 1:
		raise ValueError(f"N_WORKERS must be >= 1, got {n_workers}")

	pop_cfg = optimizer_cfg.get("population", {})
	pop_mode = pop_cfg.get("mode", "auto")
	explicit_pop_size = pop_cfg.get("explicit_pop_size")
	multiplier = int(os.environ.get("POP_MULTIPLIER", pop_cfg.get("multiplier", 2)))

	if pop_mode == "auto" or explicit_pop_size is None:
		pop_size = n_workers * multiplier
	else:
		pop_size = int(explicit_pop_size)

	if "POP_SIZE" in os.environ:
		pop_size = int(os.environ["POP_SIZE"])
	if pop_size < 1:
		raise ValueError(f"POP_SIZE must be >= 1, got {pop_size}")

	return n_workers, pop_size, n_cores


def run_cmaes_optimization(
	settings: dict[str, Any],
	paths: CalibrationPaths,
	stations: list[dict[str, Any]],
	calibration_params: dict[str, dict[str, Any]],
	run_id: int,
) -> None:
	"""Step 6: run CMA-ES calibration loop."""
	try:
		import cma
		from cma.optimization_tools import EvalParallel2
		from ewatercycle.container import ContainerImage
	except ImportError as exc:
		raise RuntimeError(
			"Missing calibration dependencies. Required: cma and ewatercycle."
		) from exc

	# Import lazily so validate-only mode does not require full calibration stack.
	from src.pcr_calibration_model import (
		CalibrationObjective,
		denormalize_params,
		normalize_params,
	)

	model_cfg = settings["model"]
	optimizer_cfg = settings["optimizer"]
	runtime_cfg = settings["runtime"]

	objective_weights = settings.get("objective", {}).get("station_metric_weights", {})
	nse_weight = float(objective_weights.get("nse", 0.5))
	kge_weight = float(objective_weights.get("kge", 0.5))
	if not np.isclose(nse_weight, 0.5) or not np.isclose(kge_weight, 0.5):
		print(
			"Warning: objective.station_metric_weights is configured, but the current "
			"CalibrationObjective implementation uses fixed 0.5/0.5 NSE/KGE weights."
		)

	n_workers, pop_size, n_cores = determine_workers_and_population(optimizer_cfg)

	param_names = list(calibration_params.keys())
	x0_original = np.array([calibration_params[name]["initial"] for name in param_names])
	x0_normalized = normalize_params(x0_original, calibration_params)

	perturb_cfg = optimizer_cfg.get("initial_perturbation", {})
	x0_run = x0_normalized.copy()
	if bool(perturb_cfg.get("enabled", True)):
		perturb_seed = evaluate_int_formula(perturb_cfg.get("seed_formula", "run_id * 42"), run_id)
		rng = np.random.default_rng(perturb_seed)
		perturb_min = float(perturb_cfg.get("min", -0.05))
		perturb_max = float(perturb_cfg.get("max", 0.05))
		perturbation = rng.uniform(perturb_min, perturb_max, size=len(x0_run))
		x0_run = np.clip(x0_run + perturbation, 0.0, 1.0)
		print(f"Run {run_id} starting point (perturbed): {x0_run.tolist()}")

	bounds = optimizer_cfg.get("bounds_normalized", [0.0, 1.0])
	lower_bound = float(bounds[0])
	upper_bound = float(bounds[1])

	cma_seed = evaluate_int_formula(optimizer_cfg.get("cma_seed_formula", "run_id * 1000"), run_id)
	sigma0 = float(optimizer_cfg["sigma0"])

	options = {
		"maxiter": int(optimizer_cfg["maxiter"]),
		"popsize": pop_size,
		"bounds": [[lower_bound] * len(param_names), [upper_bound] * len(param_names)],
		"verb_disp": 1,
		"verb_log": 0,
		"tolfun": float(optimizer_cfg["tolfun"]),
		"seed": cma_seed,
	}

	print(
		f"Starting CMA-ES: {len(param_names)} params, sigma0={sigma0}, "
		f"maxiter={options['maxiter']}, popsize={pop_size}, workers={n_workers}, cores={n_cores}"
	)

	objective = CalibrationObjective(
		stations=stations,
		calibration_params=calibration_params,
		output_dir=paths.output_dir,
		template_ini=paths.template_ini,
		params_dir=paths.params_dir,
		forcing_dir=paths.forcing_dir,
		bmi_image=ContainerImage(str(paths.bmi_image)),
		clone_map=paths.clone_map,
		landmask=paths.landmask,
		cal_start=model_cfg["calibration_period"]["start"],
		cal_end=model_cfg["calibration_period"]["end"],
		spinup_days=int(model_cfg["spinup_days"]),
		model_version=str(model_cfg["version"]),
		force_gc_after_run=bool(runtime_cfg.get("force_gc_after_run", True)),
		remove_run_dir_after_eval=bool(runtime_cfg.get("remove_run_dir_after_eval", False)),
	)

	es = cma.CMAEvolutionStrategy(x0_run.tolist(), sigma0, options)
	with EvalParallel2(objective, n_workers) as eval_all:
		while not es.stop():
			X = es.ask()
			es.tell(X, eval_all(X))
			es.disp()

	result = es.result
	best_params_original = denormalize_params(np.array(result.xbest), calibration_params)

	print("\n" + "=" * 60)
	print("CMA-ES CALIBRATION COMPLETE")
	print("=" * 60)
	print(f"Best objective: {result.fbest:.4f}")
	print(f"Total function evaluations: {result.evaluations}")
	print("Best parameters (original scale):")
	for i, name in enumerate(param_names):
		print(f"  {name}: {best_params_original[i]:.6f}")

	summary = {
		"timestamp": datetime.now().isoformat(),
		"run_id": run_id,
		"best_objective": float(result.fbest),
		"evaluations": int(result.evaluations),
		"best_parameters": {
			name: float(best_params_original[i]) for i, name in enumerate(param_names)
		},
	}
	summary_path = paths.output_dir / "best_result.yaml"
	with summary_path.open("w", encoding="utf-8") as handle:
		yaml.safe_dump(summary, handle, sort_keys=False)
	print(f"Saved best-result summary to {summary_path}")


def run_pipeline(
	config_path: Path,
	validate_only: bool,
	prepare_only: bool,
	skip_forcing_load: bool,
) -> None:
	"""Execute the full calibration pipeline."""
	script_start = datetime.now()
	print(f"Pipeline started at: {script_start:%Y-%m-%d %H:%M:%S}")
	print(f"Using configuration: {config_path}")

	log_step(1, "Load YAML settings")
	settings = load_settings(config_path)

	log_step(2, "Validate settings")
	validate_settings(settings)
	print("Configuration validation passed.")

	log_step(3, "Resolve and check required files")
	paths, run_id = resolve_calibration_paths(settings, config_path)
	check_required_files(paths)
	print(f"Resolved template INI: {paths.template_ini}")
	print(f"Resolved forcing dir: {paths.forcing_dir}")
	print(f"Resolved params dir: {paths.params_dir}")
	print(f"Resolved output dir: {paths.output_dir}")

	if validate_only:
		print("Validation-only run complete (steps 1-3).")
		return

	log_step(4, "Load or verify forcing data")
	prepare_forcing(paths.forcing_dir, skip_eager_load=skip_forcing_load)

	log_step(5, "Load observations")
	cal_start = settings["model"]["calibration_period"]["start"]
	cal_end = settings["model"]["calibration_period"]["end"]
	stations = load_observations(
		station_configs=settings["stations"],
		grdc_daily_dir=paths.grdc_daily_dir,
		start_time=cal_start,
		end_time=cal_end,
	)
	print(f"Loaded observations for {len(stations)} station(s).")

	if prepare_only:
		print("Prepare-only run complete (steps 1-5).")
		return

	log_step(6, "Run CMA-ES optimization")
	calibration_params = normalize_calibration_parameters(settings["calibration_parameters"])
	run_cmaes_optimization(
		settings=settings,
		paths=paths,
		stations=stations,
		calibration_params=calibration_params,
		run_id=run_id,
	)

	script_end = datetime.now()
	print(f"\nPipeline finished at: {script_end:%Y-%m-%d %H:%M:%S}")
	print(f"Total runtime: {script_end - script_start}")


def parse_args() -> argparse.Namespace:
	"""Parse command-line arguments."""
	default_config = Path(__file__).resolve().parent / "data" / "configs" / "template.yaml"
	parser = argparse.ArgumentParser(description="Complete PCR-GLOBWB calibration pipeline")
	parser.add_argument(
		"--config",
		type=Path,
		default=default_config,
		help="Path to YAML configuration file.",
	)
	parser.add_argument(
		"--validate-only",
		action="store_true",
		help="Run only steps 1-3 (load, validate, and file checks).",
	)
	parser.add_argument(
		"--prepare-only",
		action="store_true",
		help="Run steps 1-5 and stop before optimization.",
	)
	parser.add_argument(
		"--skip-forcing-load",
		action="store_true",
		help="Skip eager eWaterCycle forcing load and only check for NetCDF files.",
	)
	return parser.parse_args()


def main() -> None:
	"""Entry point."""
	args = parse_args()
	run_pipeline(
		config_path=args.config,
		validate_only=args.validate_only,
		prepare_only=args.prepare_only,
		skip_forcing_load=args.skip_forcing_load,
	)


if __name__ == "__main__":
	main()
