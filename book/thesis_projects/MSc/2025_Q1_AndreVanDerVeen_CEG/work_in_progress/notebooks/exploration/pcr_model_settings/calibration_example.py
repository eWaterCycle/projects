"""
PCRGlobWB Calibration using CMA-ES
Example workflow for calibrating model parameters
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import configparser
import cma  # pip install cma
from scipy.optimize import differential_evolution
import ewatercycle.observation.grdc
import ewatercycle.forcing
import ewatercycle.parameter_sets
from tqdm import tqdm

# ============================================================================
# 1. DEFINE CALIBRATION PARAMETERS
# ============================================================================

CALIBRATION_PARAMS = {
    'parameter_name': {
        'ini_section': 'routingOptions',
        'ini_key': 'manningsN',
        'bounds': (0.01, 0.15),  # min, max
        'initial': 0.04,
        'description': "Manning's roughness coefficient"
    },
    'recession_coeff': {
        'ini_section': 'groundwaterOptions',
        'ini_key': 'recessionCoeff',
        'bounds': (0.01, 0.5),
        'initial': 0.1,
        'description': "Groundwater recession coefficient"
    },
    'crop_coefficient': {
        'ini_section': 'landSurfaceOptions',
        'ini_key': 'cropCoefficientNC',
        'bounds': (0.8, 1.2),
        'initial': 1.0,
        'description': "Crop coefficient multiplier"
    },
    # Add more parameters as needed
}

# ============================================================================
# 2. HELPER FUNCTIONS
# ============================================================================

def modify_ini_file(template_ini_path, output_ini_path, param_dict):
    """
    Modify INI file with new parameter values
    
    Args:
        template_ini_path: Path to template .ini file
        output_ini_path: Path to save modified .ini file
        param_dict: Dict of {param_name: value} to update
    """
    config = configparser.ConfigParser()
    config.read(template_ini_path)
    
    for param_name, value in param_dict.items():
        if param_name in CALIBRATION_PARAMS:
            section = CALIBRATION_PARAMS[param_name]['ini_section']
            key = CALIBRATION_PARAMS[param_name]['ini_key']
            
            # Ensure section exists
            if not config.has_section(section):
                config.add_section(section)
            
            config.set(section, key, str(value))
    
    with open(output_ini_path, 'w') as f:
        config.write(f)
    
    return output_ini_path


def load_observations(station_name, start_date, end_date, grdc_id):
    """Load GRDC observation data for calibration period"""
    observations = ewatercycle.observation.grdc.get_grdc_data(
        station_id=grdc_id,
        start_time=start_date,
        end_time=end_date,
        parameter='discharge',
        data_home=None  # or specify path
    )
    return observations


def calculate_nash_sutcliffe(observed, simulated):
    """
    Calculate Nash-Sutcliffe Efficiency (NSE)
    
    NSE = 1 - sum((obs - sim)^2) / sum((obs - mean(obs))^2)
    Range: -∞ to 1, where 1 is perfect
    """
    # Remove NaN values
    mask = ~(np.isnan(observed) | np.isnan(simulated))
    obs = observed[mask]
    sim = simulated[mask]
    
    if len(obs) == 0:
        return -999  # Bad fitness if no valid data
    
    numerator = np.sum((obs - sim) ** 2)
    denominator = np.sum((obs - np.mean(obs)) ** 2)
    
    if denominator == 0:
        return -999
    
    nse = 1 - (numerator / denominator)
    return nse


def calculate_rmse(observed, simulated):
    """Calculate Root Mean Square Error"""
    mask = ~(np.isnan(observed) | np.isnan(simulated))
    obs = observed[mask]
    sim = simulated[mask]
    
    if len(obs) == 0:
        return 9999  # Bad fitness
    
    rmse = np.sqrt(np.mean((obs - sim) ** 2))
    return rmse


def calculate_kge(observed, simulated):
    """
    Calculate Kling-Gupta Efficiency (KGE)
    
    KGE = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2)
    where:
        r = correlation
        alpha = std(sim)/std(obs)
        beta = mean(sim)/mean(obs)
    """
    mask = ~(np.isnan(observed) | np.isnan(simulated))
    obs = observed[mask]
    sim = simulated[mask]
    
    if len(obs) == 0:
        return -999
    
    # Correlation
    r = np.corrcoef(obs, sim)[0, 1]
    
    # Variability ratio
    alpha = np.std(sim) / np.std(obs)
    
    # Bias ratio
    beta = np.mean(sim) / np.mean(obs)
    
    # KGE
    kge = 1 - np.sqrt((r - 1)**2 + (alpha - 1)**2 + (beta - 1)**2)
    
    return kge

# ============================================================================
# 3. OBJECTIVE FUNCTION (THE CORE)
# ============================================================================

class PCRGlobWBCalibrator:
    """Wrapper class for model calibration"""
    
    def __init__(self, 
                 template_ini,
                 forcing_directory,
                 pcr_global_params,
                 bmi_image,
                 output_base_dir,
                 calibration_start,
                 calibration_end,
                 observation_data,
                 station_coords,
                 metric='nse'):
        
        self.template_ini = Path(template_ini)
        self.forcing_dir = forcing_directory
        self.params_dir = pcr_global_params
        self.bmi_image = bmi_image
        self.output_base = Path(output_base_dir)
        self.cal_start = calibration_start
        self.cal_end = calibration_end
        self.obs_data = observation_data
        self.station_coords = station_coords
        self.metric = metric
        
        self.iteration = 0
        self.results_log = []
        
        # Create output directory
        self.output_base.mkdir(parents=True, exist_ok=True)
    
    
    def objective_function(self, params):
        """
        Objective function for optimizer
        
        Args:
            params: Array of parameter values to test
        
        Returns:
            float: Objective value (negative for maximization)
        """
        self.iteration += 1
        
        # Convert array to parameter dict
        param_dict = {}
        param_names = list(CALIBRATION_PARAMS.keys())
        for i, name in enumerate(param_names):
            param_dict[name] = params[i]
        
        print(f"\n{'='*60}")
        print(f"Iteration {self.iteration}")
        print(f"Parameters: {param_dict}")
        print(f"{'='*60}")
        
        try:
            # 1. Create modified INI file
            run_dir = self.output_base / f"run_{self.iteration:04d}"
            run_dir.mkdir(exist_ok=True)
            
            modified_ini = run_dir / "calibration.ini"
            modify_ini_file(self.template_ini, modified_ini, param_dict)
            
            # 2. Setup model
            parameter_set = ewatercycle.parameter_sets.ParameterSet(
                name=f"calibration_run_{self.iteration}",
                directory=self.params_dir,
                config=modified_ini,
                target_model="pcrglobwb",
                supported_model_versions={"17feb"},
            )
            
            forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
                directory=self.forcing_dir
            )
            
            from pcr_clonemaps import PCRGlobWBCustom  # Import custom class
            model = PCRGlobWBCustom(
                parameter_set=parameter_set,
                forcing=forcing,
                bmi_image=self.bmi_image
            )
            
            # 3. Run model
            config, directory = model.setup(
                cfg_dir=run_dir,
                start_time=self.cal_start,
                end_time=self.cal_end,
                max_spinups_in_years=0,
            )
            
            model.initialize(config)
            
            # Get number of timesteps
            start_dt = datetime.strptime(self.cal_start, "%Y-%m-%dT%H:%M:%SZ")
            end_dt = datetime.strptime(self.cal_end, "%Y-%m-%dT%H:%M:%SZ")
            n_days = (end_dt - start_dt).days
            
            # Store simulated discharge
            simulated = []
            for _ in tqdm(range(n_days), desc=f"Run {self.iteration}"):
                model.update()
                
                # Get discharge at station
                discharge = model.get_value_at_coords(
                    "discharge",
                    lat=[self.station_coords['lat']],
                    lon=[self.station_coords['lon']],
                )
                simulated.append(discharge[0])
            
            model.finalize()
            
            # 4. Calculate objective
            simulated = np.array(simulated)
            observed = self.obs_data.values
            
            if self.metric == 'nse':
                objective = calculate_nash_sutcliffe(observed, simulated)
            elif self.metric == 'kge':
                objective = calculate_kge(observed, simulated)
            elif self.metric == 'rmse':
                objective = -calculate_rmse(observed, simulated)  # Negative for minimization
            else:
                raise ValueError(f"Unknown metric: {self.metric}")
            
            print(f"Objective ({self.metric}): {objective:.4f}")
            
            # 5. Log results
            self.results_log.append({
                'iteration': self.iteration,
                'objective': objective,
                **param_dict
            })
            
            # Save log periodically
            if self.iteration % 10 == 0:
                self.save_results()
            
            # Return negative for minimization (optimizers minimize by default)
            return -objective
        
        except Exception as e:
            print(f"ERROR in iteration {self.iteration}: {e}")
            return 999  # Bad fitness
    
    
    def save_results(self):
        """Save calibration results to CSV"""
        df = pd.DataFrame(self.results_log)
        output_file = self.output_base / "calibration_results.csv"
        df.to_csv(output_file, index=False)
        print(f"Results saved to {output_file}")


# ============================================================================
# 4. RUN CALIBRATION WITH CMA-ES
# ============================================================================

def calibrate_with_cmaes(calibrator, max_iterations=100):
    """
    Run calibration using CMA-ES
    
    Args:
        calibrator: PCRGlobWBCalibrator instance
        max_iterations: Maximum number of iterations
    """
    # Get initial values and bounds
    param_names = list(CALIBRATION_PARAMS.keys())
    x0 = [CALIBRATION_PARAMS[p]['initial'] for p in param_names]
    bounds = [CALIBRATION_PARAMS[p]['bounds'] for p in param_names]
    
    # Scale to [0, 1] for CMA-ES
    lower_bounds = [b[0] for b in bounds]
    upper_bounds = [b[1] for b in bounds]
    
    # CMA-ES options
    options = {
        'maxiter': max_iterations,
        'bounds': [lower_bounds, upper_bounds],
        'popsize': 10,  # Population size
        'verb_disp': 1,  # Verbosity
        'verb_log': 1,
    }
    
    # Run optimizer
    sigma0 = 0.2  # Initial standard deviation
    es = cma.CMAEvolutionStrategy(x0, sigma0, options)
    
    es.optimize(calibrator.objective_function)
    
    # Get best result
    best_params = es.result.xbest
    best_fitness = es.result.fbest
    
    print("\n" + "="*60)
    print("CALIBRATION COMPLETE")
    print("="*60)
    print(f"Best objective: {-best_fitness:.4f}")
    print("Best parameters:")
    for i, name in enumerate(param_names):
        print(f"  {name}: {best_params[i]:.6f}")
    
    return best_params, best_fitness


# ============================================================================
# 5. ALTERNATIVE: scipy.optimize.differential_evolution
# ============================================================================

def calibrate_with_differential_evolution(calibrator, max_iterations=100):
    """
    Run calibration using Differential Evolution
    Simpler than CMA-ES, works well for up to ~20 parameters
    """
    param_names = list(CALIBRATION_PARAMS.keys())
    bounds = [CALIBRATION_PARAMS[p]['bounds'] for p in param_names]
    
    result = differential_evolution(
        calibrator.objective_function,
        bounds=bounds,
        maxiter=max_iterations,
        popsize=15,
        strategy='best1bin',
        workers=1,  # Sequential (change to -1 for parallel, but be careful!)
        updating='deferred',
        disp=True,
    )
    
    print("\n" + "="*60)
    print("CALIBRATION COMPLETE")
    print("="*60)
    print(f"Best objective: {-result.fun:.4f}")
    print("Best parameters:")
    for i, name in enumerate(param_names):
        print(f"  {name}: {result.x[i]:.6f}")
    
    return result.x, result.fun


# ============================================================================
# 6. USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    """
    Example usage - adapt this to your pcr_clonemaps.ipynb setup
    """
    
    # Configuration (adapt from your notebook)
    from src.constants import STATIONS_PCR
    from src.paths import (
        FORCING_PCRGLOB, INI_FILES, LOAD_PCR, OUTPUT_PCRGLOB,
        PCR_GLOBAL_PARAMS, PCR_TAIL
    )
    from ewatercycle.container import ContainerImage
    
    # Setup
    template_ini = INI_FILES / "test_comp_speed_full.ini"
    forcing_dir = FORCING_PCRGLOB / LOAD_PCR / PCR_TAIL
    params_dir = PCR_GLOBAL_PARAMS
    bmi_image = ContainerImage("/home/avandervee3/ewatercycle_pcr_17feb.sif")
    output_dir = OUTPUT_PCRGLOB / "calibration_runs"
    
    # Calibration period
    cal_start = "1949-10-01T00:00:00Z"
    cal_end = "1950-06-30T00:00:00Z"
    
    # Load observation data
    station_name = "Chatly"
    station_coords = STATIONS_PCR[station_name]
    
    # obs_data = load_observations(station_name, cal_start, cal_end, grdc_id="...")
    # For now, create dummy data
    obs_data = pd.Series(np.random.randn(273))
    
    # Create calibrator
    calibrator = PCRGlobWBCalibrator(
        template_ini=template_ini,
        forcing_directory=forcing_dir,
        pcr_global_params=params_dir,
        bmi_image=bmi_image,
        output_base_dir=output_dir,
        calibration_start=cal_start,
        calibration_end=cal_end,
        observation_data=obs_data,
        station_coords=station_coords,
        metric='nse'  # or 'kge', 'rmse'
    )
    
    # Run calibration
    # Option 1: CMA-ES
    best_params, best_fitness = calibrate_with_cmaes(calibrator, max_iterations=50)
    
    # Option 2: Differential Evolution
    # best_params, best_fitness = calibrate_with_differential_evolution(
    #     calibrator, max_iterations=50
    # )
