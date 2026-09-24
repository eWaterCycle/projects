# Imports
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import configparser
import cma  # CMA-ES optimizer
from tqdm import tqdm
import matplotlib.pyplot as plt

from src.constants import STATIONS_PCR
from src.paths import (
    FORCING_PCRGLOB, INI_FILES, LOAD_PCR, OUTPUT_PCRGLOB,
    PCR_GLOBAL_PARAMS, PCR_TAIL,GRDC
)
import ewatercycle.forcing
import ewatercycle.parameter_sets
import ewatercycle.observation.grdc
from ewatercycle.container import ContainerImage

script_start_time = datetime.now()
print(f"Script started at: {script_start_time:%Y-%m-%d %H:%M:%S}")

# Parameters to calibrate with bounds
CALIBRATION_PARAMS = {
    'manningsN': {
        'section': 'routingOptions',
        'key': 'manningsN',
        'bounds': (0.01, 0.1),
        'initial': 0.04
    },
    'floodplainManningsN': {
        'section': 'routingOptions',
        'key': 'floodplainManningsN',
        'bounds': (0.01, 0.1),
        'initial': 0.06
    },
    'referenceepotfactor': {
        'section': 'meteoOptions',
        'key': 'referenceepotfactor',
        'bounds': (0.5, 2),
        'initial': 1.0
    },
        'precipitationFactor': {
        'section': 'meteoOptions',
        'key': 'precipitationFactor',
        'bounds': (0.5, 2),
        'initial': 1.0
    },
    'degreeDayFactor_forest': {
        'section': 'forestOptions',
        'key': 'degreeDayFactor',
        'bounds': (0.000001, 0.01),
        'initial': 0.0025
    },
    'degreeDayFactor_grass': {
        'section': 'grasslandOptions',
        'key': 'degreeDayFactor',
        'bounds': (0.000001, 0.01),
        'initial': 0.0025
    },
    # Add more parameters here (that accept scalar values)
}

print(f"Calibrating {len(CALIBRATION_PARAMS)} parameters")
for name, info in CALIBRATION_PARAMS.items():
    print(f"  {name}: {info['bounds']} (initial: {info['initial']})")

# Paths
# Use basin_path template for custom cloneMap/landmask
template_ini = INI_FILES / "test_comp_speed_basin_path.ini"
forcing_dir = FORCING_PCRGLOB / LOAD_PCR / PCR_TAIL
params_dir = PCR_GLOBAL_PARAMS
bmi_image = ContainerImage("/home/avandervee3/ewatercycle_pcr_17feb.sif")
output_dir = OUTPUT_PCRGLOB / "calibration_runs_11march_overnight"

# Calibration period
cal_start = "1949-10-01T00:00:00Z"
cal_end = "1950-12-31T00:00:00Z"  # Shorter for testing

# Station for calibration
station_name = "Chatly"
station_coords = STATIONS_PCR[station_name]

print(f"Station: {station_name}")
print(f"Coords: {station_coords}")
print(f"Calibration period: {cal_start} to {cal_end}")
print(f"Template INI: {template_ini.name}")

# Option 1: Load from GRDC
obs_data = ewatercycle.observation.grdc.get_grdc_data(
    data_home=GRDC/"Daily",
    station_id="2817100",
    start_time=cal_start,
    end_time=cal_end,
)

# Custom PCRGlobWB wrapper to support custom cloneMap and landmask
from ewatercycle_pcrglobwb.model import PCRGlobWB
from pydantic import model_validator
from typing import Optional
from pathlib import Path
from ewatercycle.util import to_absolute_path

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


def modify_ini_file(template_path, output_path, param_values):
    """Modify INI file with new parameter values"""
    config = configparser.ConfigParser()
    # Preserve case sensitivity of option names
    config.optionxform = str
    config.read(template_path)
    
    param_names = list(CALIBRATION_PARAMS.keys())
    for i, name in enumerate(param_names):
        section = CALIBRATION_PARAMS[name]['section']
        key = CALIBRATION_PARAMS[name]['key']
        
        if not config.has_section(section):
            config.add_section(section)
        
        # Format number to avoid scientific notation (PCRGlobWB can't parse it)
        value_str = f"{param_values[i]:.10f}".rstrip('0').rstrip('.')
        config.set(section, key, value_str)
    
    with open(output_path, 'w') as f:
        config.write(f)
    
    return output_path


def normalize_params(params):
    """
    Normalize parameters from their original bounds to [0, 1]
    
    Args:
        params: Array of parameter values in original scale
    
    Returns:
        Array of normalized parameter values in [0, 1]
    """
    param_names = list(CALIBRATION_PARAMS.keys())
    normalized = []
    for i, name in enumerate(param_names):
        lower, upper = CALIBRATION_PARAMS[name]['bounds']
        norm_val = (params[i] - lower) / (upper - lower)
        normalized.append(norm_val)
    return np.array(normalized)


def denormalize_params(params_normalized):
    """
    Denormalize parameters from [0, 1] back to their original bounds
    
    Args:
        params_normalized: Array of normalized parameter values in [0, 1]
    
    Returns:
        Array of parameter values in original scale
    """
    param_names = list(CALIBRATION_PARAMS.keys())
    denormalized = []
    for i, name in enumerate(param_names):
        lower, upper = CALIBRATION_PARAMS[name]['bounds']
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
    
    return 1 - (numerator / denominator)


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

tools_folder = Path("/home/avandervee3/MSc_AralSea/book/thesis_projects/MSc/2025_Q1_AndreVanDerVeen_CEG/work_in_progress/notebooks/tools")
total_area = tools_folder / "aral_basin_05min.map"


# Track iterations
iteration_counter = [0]
results_log = []

def objective_function(params_normalized):
    """
    Run model with given parameters and return objective value
    
    Args:
        params_normalized: Array of normalized parameter values in [0, 1]
    
    Returns:
        float: Objective value (negative NSE, to minimize)
    """
    iteration_counter[0] += 1
    iteration = iteration_counter[0]
    
    # Denormalize parameters from [0, 1] to original scale
    params = denormalize_params(params_normalized)
    
    param_names = list(CALIBRATION_PARAMS.keys())
    param_dict = dict(zip(param_names, params))
    
    print(f"\nIteration {iteration}")
    print(f"Params: {param_dict}")
    
    try:
        # Setup run directory
        run_dir = output_dir / f"run_{iteration:04d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Modify INI
        modified_ini = run_dir / "calibration.ini"
        modify_ini_file(template_ini, modified_ini, params)
        
        # Setup parameter set
        parameter_set = ewatercycle.parameter_sets.ParameterSet(
            name=f"cal_run_{iteration}",
            directory=params_dir,
            config=modified_ini,
            target_model="pcrglobwb",
            supported_model_versions={"17feb"},
        )
        
        # Load forcing data
        forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
            directory=forcing_dir
        )
        
        # Create model instance using PCRGlobWBCustom
        # You can optionally add cloneMap and landmask if needed:
        # cloneMap=Path("path/to/clonemap.map"),
        # landmask=Path("path/to/landmask.map"),
        model = PCRGlobWBCustom(
            parameter_set=parameter_set,
            forcing=forcing,
            bmi_image=bmi_image,
            cloneMap=total_area,
            landmask=total_area,
        )
        
        # Setup and initialize
        config, directory = model.setup(
            cfg_dir=run_dir,
            start_time=cal_start,
            end_time=cal_end,
            max_spinups_in_years=0,
        )
        
        model.initialize(config)
        
        # Run model and collect discharge
        n_days = len(obs_data['time'])
        simulated = []
        
        # Update progress roughly every 2% of timesteps.
        # update_interval = int(n_days * 0.02)
        for _ in tqdm(
            range(n_days),
            desc=f"Run {iteration}",
            leave=False,
            # miniters=update_interval,
        ):
            model.update()
            discharge = model.get_value_at_coords(
                "discharge",
                lat=[station_coords['lat']],
                lon=[station_coords['lon']],
            )
            simulated.append(discharge[0])
        
        model.finalize()
        
        # Calculate objective
        simulated = np.array(simulated)
        observed = obs_data['streamflow'].values
        
        nse = calculate_nse(observed[30:], simulated[30:])  # TODO Skip first 30 days for spinup
        kge = calculate_kge(observed[30:], simulated[30:])  # TODO Skip first 30 days for spinup
        # Return function (for minimization)
        obj_val = 0.5 * (1 - nse) + 0.5 * (1 - kge)  # Use negative NSE to maximize it
        
        print(f"Iteration {iteration}, OBJ: {obj_val:.4f}, NSE: {nse:.4f}, KGE: {kge:.4f}")
        
        # Log results
        results_log.append({
            'iteration': iteration,
            'objective_value': obj_val,
            'nse': nse,
            'kge': kge,
            **param_dict
        })
        
        # Save results periodically
        if iteration % 1 == 0:
            df = pd.DataFrame(results_log)
            df.to_csv(output_dir / "calibration_results.csv", index=False)
        
        # Return function (for minimization)
        #obj_val = 0.5 * (1 - nse) + 0.5 * (1 - kge)  # Use negative NSE to maximize it
        return obj_val
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 999  # Bad fitness

# Get initial values and bounds for CMA-ES
param_names = list(CALIBRATION_PARAMS.keys())
x0_original = [CALIBRATION_PARAMS[p]['initial'] for p in param_names]

# Normalize initial values to [0, 1]
x0_normalized = normalize_params(np.array(x0_original))

# All parameters now have bounds [0, 1]
lower_bounds = [0.0] * len(param_names)
upper_bounds = [1.0] * len(param_names)


print(f"Starting CMA-ES calibration with {len(param_names)} parameters")
print(f"Original initial values: {x0_original}")
print(f"Normalized initial values: {x0_normalized.tolist()}")
print(f"Normalized bounds: [0, 1] for all parameters")

# CMA-ES options
options = {
    'maxiter': 4,  # Number of generations (increase for real calibration)
    'popsize': 4,   # Population size per generation
    'bounds': [lower_bounds, upper_bounds],
    'verb_disp': 1,  # Display every iteration
    'verb_log': 0,   # Don't create log files
    'tolfun': 1e-6,  # Termination criterion: function value tolerance
}

# Initial step size (sigma) - now reasonable for [0, 1] space
sigma0 = 0.2  # 20% of the [0, 1] range

# Run CMA-ES optimization
es = cma.CMAEvolutionStrategy(x0_normalized.tolist(), sigma0, options)
es.optimize(objective_function)

# Get results
result = es.result
best_params_normalized = result.xbest
best_params_original = denormalize_params(np.array(best_params_normalized))
best_fitness = result.fbest

print("\n" + "="*60)
print("CMA-ES CALIBRATION COMPLETE")
print("="*60)
print(f"Best Result: {-best_fitness:.4f}")
print(f"Total function evaluations: {result.evaluations}")
print(f"Best parameters (original scale):")
for i, name in enumerate(param_names):
    print(f"  {name}: {best_params_original[i]:.6f}")
print(f"\nBest parameters (normalized): {best_params_normalized}")

script_end_time = datetime.now()
print(f"Script ended at: {script_end_time:%Y-%m-%d %H:%M:%S}")
print(f"Total runtime: {script_end_time - script_start_time}")