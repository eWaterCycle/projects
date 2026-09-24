
# Custom PCRGlobWB wrapper and reusable calibration utilities
import configparser
import csv
import fcntl
import gc
import shutil
import uuid
from datetime import datetime
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from ewatercycle_pcrglobwb.model import PCRGlobWB
from ewatercycle.util import to_absolute_path
from pydantic import model_validator

class PCRGlobWBCustom(PCRGlobWB):
    """Extended PCRGlobWB with support for custom cloneMap and landmask paths."""

    cloneMap: Optional[Path] = None
    landmask: Optional[Path] = None

    @model_validator(mode="after")
    def _check_parameter_set(self):
        if not self.parameter_set:
            return self

        target_model = self.parameter_set.target_model.lower()
        if target_model != "pcrglobwb":
            msg = (
                "Parameter set has wrong target model, "
                f"expected pcrglobwb got {target_model}"
            )
            raise ValueError(msg)

        version = self.version
        ps_versions = self.parameter_set.supported_model_versions
        if version and ps_versions and version not in ps_versions:
            msg = (
                f"Parameter set '{self.parameter_set.name}' not compatible"
                f" with this model version.\nModel version: {version}. "
                f"Compatible versions: {ps_versions}"
            )
            raise ValueError(msg)

        return self

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return to_absolute_path(path, must_be_in_parent=False)
        return to_absolute_path(
            path, parent=self.parameter_set.directory, must_be_in_parent=True
        )

    @model_validator(mode="after")
    def _initialize_config(self: "PCRGlobWBCustom") -> "PCRGlobWBCustom":
        cfg = super()._initialize_config()._config

        # Set cloneMap if provided, otherwise use existing from config
        if self.cloneMap:
            clone_map_abs = str(self._resolve_path(self.cloneMap))
            cfg.set("globalOptions", "cloneMap", clone_map_abs)
        # If cloneMap not already in config, ensure it exists
        elif not cfg.has_option("globalOptions", "cloneMap"):
            # Try to get from parameter set directory as fallback
            # PCRGlobWB models typically have cloneMap in global options
            pass  # Let the original config handle it

        # Set landmask if provided
        if self.landmask:
            landmask_abs = str(self._resolve_path(self.landmask))
            cfg.set("globalOptions", "landmask", landmask_abs)

        self._config = cfg
        return self

    def _make_bmi_instance(self):
        if self.cloneMap:
            clone_dir = str(Path(self.cloneMap).parent)
            if clone_dir not in self._additional_input_dirs:
                self._additional_input_dirs.append(clone_dir)

        if self.landmask:
            landmask_dir = str(Path(self.landmask).parent)
            if landmask_dir not in self._additional_input_dirs:
                self._additional_input_dirs.append(landmask_dir)

        return super()._make_bmi_instance()


def modify_ini_file(template_path, output_path, param_values, calibration_params):
    """Modify INI file with new parameter values.

    Args:
        template_path: Path to the template INI file.
        output_path: Path to write the modified INI file.
        param_values: Array of parameter values in original scale.
        calibration_params: Dict mapping param name -> {section, key, bounds, initial}.
    """
    config = configparser.ConfigParser()
    # Preserve case sensitivity of option names
    config.optionxform = str
    config.read(template_path)

    param_names = list(calibration_params.keys())
    for i, name in enumerate(param_names):
        section = calibration_params[name]['section']
        key = calibration_params[name]['key']
        
        if not config.has_section(section):
            config.add_section(section)
        
        # Format number to avoid scientific notation (PCRGlobWB can't parse it)
        value_str = f"{param_values[i]:.10f}".rstrip('0').rstrip('.')
        config.set(section, key, value_str)
    
    with open(output_path, 'w') as f:
        config.write(f)
    
    return output_path


def normalize_params(params, calibration_params):
    """Normalize parameters from their original bounds to [0, 1].

    Args:
        params: Array of parameter values in original scale.
        calibration_params: Dict mapping param name -> {section, key, bounds, initial}.

    Returns:
        Array of normalized parameter values in [0, 1].
    """
    param_names = list(calibration_params.keys())
    normalized = []
    for i, name in enumerate(param_names):
        lower, upper = calibration_params[name]['bounds']
        norm_val = (params[i] - lower) / (upper - lower)
        normalized.append(norm_val)
    return np.array(normalized)


def denormalize_params(params_normalized, calibration_params):
    """Denormalize parameters from [0, 1] back to their original bounds.

    Args:
        params_normalized: Array of normalized parameter values in [0, 1].
        calibration_params: Dict mapping param name -> {section, key, bounds, initial}.

    Returns:
        Array of parameter values in original scale.
    """
    param_names = list(calibration_params.keys())
    denormalized = []
    for i, name in enumerate(param_names):
        lower, upper = calibration_params[name]['bounds']
        orig_val = params_normalized[i] * (upper - lower) + lower
        denormalized.append(orig_val)
    return np.array(denormalized)


def calculate_nse(observed, simulated):
    """Calculate Nash-Sutcliffe Efficiency"""
    mask = ~(np.isnan(observed) | np.isnan(simulated))
    obs = observed[mask]
    sim = simulated[mask]
    
    if len(obs) == 0:
        return -999
    
    numerator = np.sum((obs - sim) ** 2)
    denominator = np.sum((obs - np.mean(obs)) ** 2)
    
    if denominator == 0:
        return -999
    
    nse_value = 1 - (numerator / denominator)
    nse_score = nse_value/(2-nse_value)
    return nse_score


def calculate_kge(observed, simulated):
    """Calculate Kling-Gupta Efficiency"""
    mask = ~(np.isnan(observed) | np.isnan(simulated))
    obs = observed[mask]
    sim = simulated[mask]
    
    if len(obs) < 2:
        return -999
    
    r = np.corrcoef(obs, sim)[0, 1]
    alpha = np.std(sim) / np.std(obs) if np.std(obs) > 0 else 0
    beta = np.mean(sim) / np.mean(obs) if np.mean(obs) > 0 else 0
    
    kge = 1 - np.sqrt((r - 1)**2 + (alpha - 1)**2 + (beta - 1)**2)
    return kge

import ewatercycle.forcing
import ewatercycle.parameter_sets
from tqdm import tqdm


class CalibrationObjective:
    """Callable objective function for CMA-ES calibration.

    Supports one or multiple GRDC stations as calibration targets. Pass a list
    of station dicts, each with 'name', 'coords', and 'obs_data'. An optional
    'weight' key (default 1.0) controls the contribution of each station to the
    aggregated objective::

        stations = [
            {
                'name': 'Chatly',
                'coords': {'lat': 41.97, 'lon': 60.68},
                'obs_data': obs_chatly,   # xarray dataset from get_grdc_data
                'weight': 1.0,            # optional
            },
            {
                'name': 'Kzylorda',
                'coords': {'lat': 44.85, 'lon': 65.48},
                'obs_data': obs_kzylorda,
                'weight': 1.0,
            },
        ]
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
        )
        es.optimize(obj)
        print(obj.results)  # list of dicts, one per evaluation
    """

    def __init__(
        self,
        stations,
        calibration_params,
        output_dir,
        template_ini,
        params_dir,
        forcing_dir,
        bmi_image,
        clone_map,
        landmask,
        cal_start,
        cal_end,
        spinup_days=30,
        model_version="17feb",
        force_gc_after_run=True,
        remove_run_dir_after_eval=False,
    ):
        """
        Args:
            stations: List of dicts, each with keys:
                - 'name'     (str)   label used in logging and results CSV
                - 'coords'   (dict)  {'lat': float, 'lon': float}
                - 'obs_data' (xarray Dataset) from ewatercycle.observation.grdc
                - 'weight'   (float, optional) default 1.0
        """
        self.stations = stations
        self.calibration_params = calibration_params
        self.output_dir = Path(output_dir)
        self.template_ini = Path(template_ini)
        self.params_dir = Path(params_dir)
        self.forcing_dir = Path(forcing_dir)
        self.bmi_image = bmi_image
        self.clone_map = Path(clone_map)
        self.landmask = Path(landmask)
        self.cal_start = cal_start
        self.cal_end = cal_end
        self.spinup_days = spinup_days
        self.model_version = model_version
        self.force_gc_after_run = force_gc_after_run
        self.remove_run_dir_after_eval = remove_run_dir_after_eval

        self.iteration = 0
        self.results = []

    def __call__(self, params_normalized, iteration=None):
        """Run one model evaluation. Called by CMA-ES for each candidate.

        Args:
            params_normalized: Candidate parameter vector in [0, 1].
            iteration: Optional explicit iteration number. When running
                candidates in parallel each worker receives a pre-assigned
                number so there are no races on self.iteration. When None
                (sequential use) self.iteration is auto-incremented.
        """
        if iteration is None:
            # Use a UUID-based tag so parallel workers forked from the same
            # process never collide on the same run directory.
            run_tag = uuid.uuid4().hex[:8]
        else:
            self.iteration = max(self.iteration, iteration)
            run_tag = f"{iteration:04d}"

        params = denormalize_params(np.array(params_normalized), self.calibration_params)
        param_names = list(self.calibration_params.keys())
        param_dict = dict(zip(param_names, params))

        print(f"\nRun {run_tag}")
        print(f"Params: {param_dict}")

        run_dir = None
        model = None
        forcing = None
        parameter_set = None
        model_initialized = False

        try:
            run_dir = self.output_dir / f"run_{run_tag}"
            run_dir.mkdir(parents=True, exist_ok=True)

            modified_ini = run_dir / "calibration.ini"
            modify_ini_file(self.template_ini, modified_ini, params, self.calibration_params)

            parameter_set = ewatercycle.parameter_sets.ParameterSet(
                name=f"cal_run_{run_tag}",
                directory=self.params_dir,
                config=modified_ini,
                target_model="pcrglobwb",
                supported_model_versions={self.model_version},
            )

            forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
                directory=self.forcing_dir
            )

            model = PCRGlobWBCustom(
                parameter_set=parameter_set,
                forcing=forcing,
                bmi_image=self.bmi_image,
                cloneMap=self.clone_map,
                landmask=self.landmask,
            )

            config, directory = model.setup(
                cfg_dir=run_dir,
                start_time=self.cal_start,
                end_time=self.cal_end,
                max_spinups_in_years=0,
            )
            model.initialize(config)
            model_initialized = True

            n_days = len(self.stations[0]['obs_data']['time'])
            simulated_per_station = {s['name']: [] for s in self.stations}

            lats = [s['coords']['lat'] for s in self.stations]
            lons = [s['coords']['lon'] for s in self.stations]

            for _ in tqdm(range(n_days), desc=f"Run {run_tag}", leave=False):
                model.update()
                discharges = model.get_value_at_coords(
                    "discharge", lat=lats, lon=lons
                )
                for i, station in enumerate(self.stations):
                    simulated_per_station[station['name']].append(discharges[i])

            station_metrics = {}
            weighted_obj_sum = 0.0
            total_weight = sum(s.get('weight', 1.0) for s in self.stations)

            for station in self.stations:
                name = station['name']
                weight = station.get('weight', 1.0)
                sim = np.array(simulated_per_station[name])
                obs = station['obs_data']['streamflow'].values
                nse = calculate_nse(obs[self.spinup_days:], sim[self.spinup_days:])
                nse = -5 if np.isnan(nse) else nse # TODO handle NaN NSE more gracefully in the future
                kge = calculate_kge(obs[self.spinup_days:], sim[self.spinup_days:])
                kge = -5 if np.isnan(kge) else kge # TODO handle NaN KGE more gracefully in the future
                station_obj = 0.5 * (1 - nse) + 0.5 * (1 - kge)
                station_metrics[name] = {'nse': nse, 'kge': kge, 'obj': station_obj}
                weighted_obj_sum += weight * station_obj
                print(f"  {name}: NSE={nse:.4f}, KGE={kge:.4f}, obj={station_obj:.4f} (w={weight})")

            obj_val = weighted_obj_sum / total_weight
            print(f"Run {run_tag}, OBJ: {obj_val:.4f} (weighted mean across {len(self.stations)} station(s))")

            result_row = {'run_tag': run_tag, 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'objective_value': obj_val, **param_dict}
            for name, metrics in station_metrics.items():
                result_row[f'nse_{name}'] = metrics['nse']
                result_row[f'kge_{name}'] = metrics['kge']
                result_row[f'obj_{name}'] = metrics['obj']

            self.results.append(result_row)
            # In parallel mode each worker has its own process-local
            # self.results list. Append one row atomically to avoid workers
            # overwriting each other's CSV content.
            self._append_result_row(result_row)
            return obj_val

        except Exception as e:
            print(f"ERROR in iteration {iteration}: {e}")
            import traceback
            traceback.print_exc()
            return 999.0
        finally:
            if model is not None and model_initialized:
                try:
                    model.finalize()
                except Exception as finalize_error:
                    print(f"WARNING: finalize failed for run {run_tag}: {finalize_error}")

            # Drop references to large objects held in worker processes.
            model = None
            forcing = None
            parameter_set = None

            if self.remove_run_dir_after_eval and run_dir is not None and run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

            if self.force_gc_after_run:
                gc.collect()

    def _save_results(self):
        df = pd.DataFrame(self.results)
        df.to_csv(self.output_dir / "calibration_results.csv", index=False)

    def _append_result_row(self, row):
        csv_path = self.output_dir / "calibration_results.csv"
        fieldnames = list(row.keys())

        with open(csv_path, "a+", newline="") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            first_line = f.readline().strip()
            has_header = bool(first_line)

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not has_header:
                writer.writeheader()

            f.seek(0, 2)
            writer.writerow(row)
            f.flush()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)