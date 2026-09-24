"""Module for hydrological model simulations and calibration.
Includes functions to run HBV and PCR-GLOBWB models,
generate parameters, run ensembles, and perform CMA-ES calibration.
"""

import os
import pickle
import shutil
from datetime import datetime
from pathlib import Path

import cma
import ewatercycle.models
import ewatercycle.parameter_sets
import numpy as np
import pandas as pd
import xarray as xr
from tqdm.notebook import tqdm

from src.constants import HBV_PARAM_BOUNDS, PARAMETER_NAMES
from src.forcing import load_lumped_forcing_data
from src.paths import OUTPUT_HBV, PCR_GLOBAL_PARAMS
from src.utils import mmday_to_m3s
from ewatercycle.container import ContainerImage


# INI_FILES is now passed as a parameter to simulate_PCRGLOBWB_experiment
# This was previously hardcoded to complete_pcrglob_run which caused issues
# when running experiments from other projects


def simulate_HBV(
    forcing,
    parameter_set,
    initial_conditions,
    show_progress=True,
    delete_files=False,
    leave_pbar=True,
):
    """Run the HBV model with a given forcing and parameters.

    Parameters
    ----------
    forcing : ewatercycle.forcing.Forcing
        The forcing object (e.g., ERA5_forcing)
    parameter_set : dict
        HBV model parameter set
    initial_conditions : dict
        Initial storage values
    show_progress : bool
        If True, show a tqdm progress bar

    Returns:
    -------
    pd.Series
        Modelled discharge time series
    """
    # Initialize model
    model = ewatercycle.models.HBV(forcing=forcing)
    config_file, config_dir = model.setup(
        parameters=parameter_set, initial_storage=initial_conditions
    )
    model.initialize(config_file)

    Q_m = []
    time = []

    # Determine total steps for progress bar
    total_steps = int((model.end_time - model.start_time) / model.time_step)

    if show_progress:
        pbar = tqdm(total=total_steps, desc="Running HBV model", mininterval=1.0, leave=leave_pbar)

    while model.time < model.end_time:
        model.update()
        Q_m.append(model.get_value("Q")[0])
        time.append(pd.Timestamp(model.time_as_datetime))

        if show_progress:
            pbar.update(1)

    if show_progress:
        pbar.close()

    config_dir = Path(config_dir)

    if delete_files:
        try:
            if config_dir.exists() and config_dir.is_dir():
                files = list(config_dir.iterdir())
                if len(files) == 1 and files[0].name == "HBV_config.json":
                    shutil.rmtree(config_dir)
                else:
                    print(f"Folder {config_dir} not deleted: contains other files")
        except Exception as e:
            print(f"Could not delete folder {config_dir}: {e}")
    model.finalize()

    # Return as pandas Series
    model_output = pd.Series(data=Q_m, name="Modelled_discharge", index=time)
    return model_output


def plot_HBV_output(model_output: pd.Series):
    """Plot the HBV model output time series.

    Parameters
    ----------
    model_output : pd.Series
        Modelled discharge time series
    """
    import matplotlib.pyplot as plt

    plt.figure(figsize=(12, 6))
    plt.plot(model_output.index, model_output.values, label="Modelled Discharge", color="tab:blue")
    plt.xlabel("Time")
    plt.ylabel("Discharge (mm/d)")
    plt.title("HBV Modelled Discharge Time Series")
    plt.legend()
    plt.grid(linestyle="--", alpha=0.5)
    plt.show()


def save_HBV_results(
    model_output: pd.Series,
    shape_name: str,
    forcing_type: str,
    run_tag: str = None,
    parameters: dict = None,
):
    """Save HBV model output as CSV, NetCDF, and pickle.
    Also converts results to m3/s using shapefile

    Parameters
    ----------
    model_output : pd.Series
        Modelled discharge time series in mm/day
    shape_name : str
        Name of the shapefile / catchment
    forcing_type : str
        Type of forcing (ERA5, CMIP, etc.)
    """
    # Directory where outputs will be stored
    output_dir = OUTPUT_HBV / f"{shape_name}" / f"{forcing_type}"
    output_dir.mkdir(parents=True, exist_ok=True)

    start_year = model_output.index[0].year
    end_year = model_output.index[-1].year

    # conversion to m3/s
    model_output_m3 = mmday_to_m3s(model_output, shape_name)

    # make df
    df = pd.DataFrame({"mm_day": model_output, "m3_s": model_output_m3})

    # generate name
    base_filename = f"{shape_name}_{forcing_type}_{start_year}-{end_year}"

    if run_tag is not None:
        base_filename = f"{base_filename}_{run_tag}"

    # Save CSV (mm/day
    csv_file = output_dir / f"{base_filename}.csv"
    df.to_csv(csv_file, index_label="time")

    # Save as pickle (data + metadata)
    pkl_file = output_dir / f"{base_filename}.pkl"

    payload = {
        "data": df,
        "metadata": {
            "shape_name": shape_name,
            "forcing_type": forcing_type,
            "run_tag": run_tag,
            "start_year": start_year,
            "end_year": end_year,
            "parameters": parameters,
        },
    }

    with open(pkl_file, "wb") as f:
        pickle.dump(payload, f)

    # Save as netcdf
    ds = xr.Dataset(
        {
            "discharge_mm_day": ("time", model_output.values, {"units": "mm/day"}),
            "discharge_m3_s": ("time", model_output_m3.values, {"units": "m3/s"}),
        },
        coords={"time": model_output.index},
    )

    # metadata
    ds.attrs.update(
        {
            "shape_name": shape_name,
            "forcing_type": forcing_type,
            "run_tag": run_tag,
            "start_year": start_year,
            "end_year": end_year,
        }
    )

    if parameters is not None:
        for name, value in parameters.items():
            ds.attrs[f"param_{name}"] = float(value)
    nc_file = output_dir / f"{base_filename}.nc"

    ds.to_netcdf(nc_file)

    return {"csv": csv_file, "pkl": pkl_file, "nc": nc_file}


def simulate_PCRGLOBWB(forcing_path, ini_name, start_date, end_date):
    """Run the PCR-GLOBWB hydrological model for a given forcing and configuration.

    This function sets up and executes a PCR-GLOBWB simulation using the
    specified forcing data and parameter INI file. Currently, it relies on
    the eWaterCycle framework and a hardcoded location for global PCR-GLOBWB
    parameter sets. Progress is displayed with a tqdm bar.

    Parameters
    ----------
    forcing_path : str or Path
        Path to the folder containing PCR-GLOBWB forcing files.
    ini_name : str
        Name of the configuration INI file (e.g., "my_catchment.ini").
        This file should exist in the `INI_FILES` directory.
    start_date : str
        Start date of the simulation in ISO 8601 format (e.g., "1950-01-01T00:00:00Z").
    end_date : str
        End date of the simulation in ISO 8601 format (e.g., "2020-12-31T00:00:00Z").

    Returns:
    -------
    None
        The function writes output to the eWaterCycle-managed model directory.
        Results can be accessed from the `model.output_dir` or via other
        eWaterCycle utilities.

    Notes:
    -----
    - The function currently hardcodes the location of global parameter sets:
      `/data/shared/parameter-sets/pcrglobwb_global`.
    - The `supported_model_versions` is currently set to `{"setters"}`
    - Simulation progress is displayed via a tqdm progress bar.
    - This function does not return Python objects with results; output files
      must be read separately after the run.
    """
    from tqdm import tqdm as classic_tqdm

    # Convert ISO 8601 strings to datetime objects
    start_time = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
    end_time = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")

    # Calculate the number of days for the progression bar
    delta = end_time - start_time
    number_of_days = delta.days

    pbar = classic_tqdm(total=number_of_days, desc="Initializing model", mininterval=1.0)

    # can be hardcoded, location of all the pcr-glob data on ewatercycle
    pcr_glob_directory = PCR_GLOBAL_PARAMS

    forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
        directory=forcing_path,
    )

    parameter_set = ewatercycle.parameter_sets.ParameterSet(
        name="custom_parameter_set",
        directory=pcr_glob_directory,
        config=INI_FILES / ini_name,
        target_model="pcrglobwb",
        supported_model_versions={"setters"},
    )

    model = ewatercycle.models.PCRGlobWB(parameter_set=parameter_set, forcing=forcing)

    model_config, model_dir = model.setup(
        start_time=start_date, end_time=end_date, max_spinups_in_years=0
    )

    model.initialize(model_config)

    pbar.set_description("Running model")
    while model.time < model.end_time:
        model.update()
        pbar.update(1)

    pbar.close()
    tqdm.write("Model run finished!")

    model.finalize()


def generate_HBV_parameters(n_particles: int):
    """Generate a set of HBV model parameter vectors.

    Parameters
    ----------
    n_particles : int
        Number of parameter vectors to generate.

    Returns:
    -------
    list of dict
        Each element is a dictionary containing a full set of HBV parameters
        for a single particle/run.

    Notes:
    -----
    Parameters are randomly sampled within predefined ranges.
    """
    p_min = np.array([0, 0.2, 40, 0.5, 0.001, 1, 0.01, 0.0001, 0.01])  # hardcoded for now TODO
    p_max = np.array([25, 1, 800, 4, 0.3, 15, 0.02, 0.01, 0.8])  # hardcoded for now TODO

    array_random_num = np.array(
        [[np.random.random() for i in range(len(p_max))] for i in range(n_particles)]
    )
    generated_parameters = p_min + array_random_num * (p_max - p_min)

    return generated_parameters


def simulate_HBV_ensemble(n_particles: int, forcing, delete_files=True):
    """Run multiple HBV simulations as an ensemble.

    Parameters
    ----------
    n_particles : int
        Number of ensemble members.
    forcing : ewatercycle.forcing.Forcing
        Forcing object for the simulations.
    delete_files : bool, default True
        If True, intermediate files are deleted after the simulation.

    Returns:
    -------
    list of pd.Series
        Each element contains the simulated discharge time series for one particle.
    """
    list_parameters = generate_HBV_parameters(n_particles)  # store somewhere TODO

    s_0 = np.array([0, 100, 0, 5, 0])  # hardcoded storage TODO

    all_series = []

    for i in tqdm(range(n_particles), desc="Running HBV particles"):
        s = run_HBV_model(
            forcing=forcing,
            parameter_set=list_parameters[i],
            initial_conditions=s_0,
            show_progress=True,
            delete_files=delete_files,
            leave_pbar=False,
        )
        all_series.append(s)

    df_all = pd.concat(all_series, axis=1)
    df_all.columns = [f"particle_{i}" for i in range(n_particles)]

    return df_all


# ===========================================================================
# better way of calibration?
# using scipy optimize
# more text to be added here
# ===========================================================================

parameter_names = [
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


# history tracking
history = {"theta_norm": [], "theta_phys": [], "objective": []}


p_min = HBV_PARAM_BOUNDS["min"]
p_max = HBV_PARAM_BOUNDS["max"]
# p_min = np.array([0, 0.2, 40, 0.5, 0.001, 1, 0.01, 0.0001, 0.01])
# p_max = np.array([25, 1, 800, 4, 0.3, 15, 0.02, 0.01, 0.8])


# scale parameters
def scale(theta):
    """Scale a physical HBV parameter vector to normalized [0,1] values.

    Parameters
    ----------
    theta : array-like
        Physical parameter vector.

    Returns:
    -------
    np.ndarray
        Normalized parameter vector with values in [0,1].
    """
    return (theta - p_min) / (p_max - p_min)


def unscale(x):
    """Convert a normalized [0,1] HBV parameter vector back to physical units.

    Parameters
    ----------
    x : array-like
        Normalized parameter vector with values in [0,1].

    Returns:
    -------
    np.ndarray
        Physical HBV parameter vector.
    """
    return p_min + x * (p_max - p_min)


bounds = list(zip(p_min, p_max))


def run_hbv_single(theta, forcing, shape_name):
    """Run a single HBV simulation with given parameter vector.

    Parameters
    ----------
    theta : array-like
        Physical HBV parameters.
    forcing : ewatercycle.forcing.Forcing
        Forcing object (e.g., ERA5, CMIP).
    shape_name : str
        Catchment identifier (used for mm/day → m³/s conversion).

    Returns:
    -------
    pd.Series
        Simulated discharge time series in m³/s.
    """
    s_0 = np.array([0, 100, 0, 5, 0])  # later: make configurable

    model_output = run_HBV_model(
        forcing=forcing,
        parameter_set=theta,
        initial_conditions=s_0,
        show_progress=False,
        delete_files=True,
        leave_pbar=False,
    )

    model_output_m3 = mmday_to_m3s(model_output, shape_name)

    # assume sim is a pd.Series of discharge
    return model_output_m3


def objective(theta_norm, forcing, q_obs, years, shape_name):
    """Objective function for HBV calibration combining hydrograph fit and yearly volume error.

    Parameters
    ----------
    theta_norm : array-like
        Normalized HBV parameter vector.
    forcing : ewatercycle.forcing.Forcing
        Forcing object.
    q_obs : pd.Series
        Observed discharge time series.
    years : array-like
        Array of years corresponding to observations.
    shape_name : str
        Catchment identifier.

    Returns:
    -------
    float
        Weighted objective value: (1 - NSE) + mean squared relative yearly volume error.

    Notes:
    -----
    - NSE: Nash-Sutcliffe Efficiency measuring hydrograph fit.
    - Volume term: mean squared relative error in yearly total discharge.
    """
    theta = unscale(theta_norm)
    sim = run_hbv_single(theta, forcing, shape_name)

    # --- hydrograph fit ---
    nse_val = 1 - np.sum((sim - q_obs) ** 2) / np.sum((q_obs - q_obs.mean()) ** 2)

    # --- yearly volume error ---
    vol_errs = []
    for y in np.unique(years):
        mask = years == y
        sim_y = sim[mask].sum()
        obs_y = q_obs[mask].sum()
        vol_errs.append((sim_y - obs_y) / obs_y)

    vol_term = np.mean(np.square(vol_errs))

    # combined objective
    J = (1 - nse_val) + vol_term

    return float(J)


def volume_error(sim, obs):
    """Compute absolute relative volume error between simulated and observed discharge.

    Parameters
    ----------
    sim : array-like
        Simulated discharge.
    obs : array-like
        Observed discharge.

    Returns:
    -------
    float
        Absolute relative volume error: |1 - sum(sim)/sum(obs)|.
    """
    return abs(1 - np.sum(sim) / np.sum(obs))


call_counter = {"n": 0}


def objective_HBV_safe(theta_norm, forcing, q_obs, shape_name, history):
    """Safe objective function for CMA-ES calibration of the HBV model.

    Parameters
    ----------
    theta_norm : array_like
        Normalized parameter vector (values in [0,1]).
    forcing : pd.DataFrame or dict
        Meteorological forcing data for the model.
    q_obs : pd.Series
        Observed streamflow time series.
    shape_name : str
        Identifier of the catchment.
    history : dict
        Dictionary to store parameters, metrics, and evaluation info.
        Must be initialized outside this function.

    Returns:
    -------
    float
        Weighted objective value: 0.3*(1-NSE) + 0.3*(1-KGE) + 0.4*VolumeError.

    Notes:
    -----
    - NSE: Nash-Sutcliffe Efficiency.
    - KGE: Kling-Gupta Efficiency.
    - VolumeError: Absolute error in total simulated vs. observed streamflow.
    - Updates `history` dictionary with parameter sets and metric values.
    """
    call_counter["n"] += 1

    # Unscale parameters for HBV
    theta_phys = unscale(theta_norm)

    # Run HBV
    sim = run_hbv_single(theta_phys, forcing, shape_name)

    # --- Metrics ---
    nse = 1 - np.sum((sim - q_obs) ** 2) / np.sum((q_obs - q_obs.mean()) ** 2)

    r = np.corrcoef(sim, q_obs)[0, 1]
    alpha = np.std(sim) / np.std(q_obs)
    beta = np.mean(sim) / np.mean(q_obs)
    kge = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)

    vol_err = volume_error(sim, q_obs)

    # --- Combined objective ---
    obj_val = 0.3 * (1 - nse) + 0.3 * (1 - kge) + 0.4 * vol_err

    # --- Store in history ---
    history.setdefault("theta_norm", []).append(theta_norm.copy())
    history.setdefault("theta_phys", []).append(theta_phys.copy())
    history.setdefault("objective", []).append(obj_val)
    history.setdefault("nse", []).append(nse)
    history.setdefault("kge", []).append(kge)
    history.setdefault("vol_err", []).append(vol_err)

    return obj_val


def save_history(history, filename, folder="results", fmt="csv"):
    """Save CMA-ES calibration history to file.

    Parameters
    ----------
    history : dict
        Dictionary containing CMA-ES calibration history.
        Expected keys: 'theta_norm', 'theta_phys', 'objective', 'nse', 'kge', 'vol_err', ...
    filename : str
        Name of the file (without extension) to save.
    folder : str, optional
        Folder to save the file in (default is "results"). Created if it does not exist.
    fmt : str, optional
        File format: "csv", "json", or "pkl" (default is "csv").
    """
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename + "." + fmt)

    # Convert history to DataFrame if possible
    df = pd.DataFrame(history)

    if fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "json":
        df.to_json(path, orient="records", indent=2)
    elif fmt == "pkl":
        df.to_pickle(path)
    else:
        raise ValueError("Unsupported format. Choose 'csv', 'json', or 'pkl'.")

    print(f"History saved to {path}")


# TODO: add function for cma-es (note to self: see work document)
def run_cma_multiple_seeds(
    objective_fn, x0_norm, sigma0, args, p_min, p_max, seeds=None, popsize=15, maxfevals=500
):
    """Run multiple CMA-ES calibrations with different random seeds and collect histories.

    Parameters
    ----------
    objective_fn : callable
        The objective function to minimize.
    x0_norm : array-like
        Initial normalized parameter guess.
    sigma0 : float
        Initial standard deviation (step size) for CMA-ES.
    args : tuple
        Additional arguments to pass to the objective function (forcing, observations, etc.).
    p_min, p_max : array-like
        Min and max bounds for parameters (normalized to [0,1]).
    seeds : list of int
        List of random seeds for independent runs.
    popsize : int
        CMA-ES population size.
    maxfevals : int
        Maximum number of function evaluations per run.

    Returns:
    -------
    results_list : list of dict
        Each element is a dict with keys 'res' (CMA-ES output) and 'history' (DataFrame of metrics).
    """
    if seeds is None:
        seeds = [0, 1, 2]
    results_list = []

    for s in seeds:
        # reset objective history for each run
        global history
        history = {}

        np.random.seed(s)
        res = cma.fmin(
            objective_fn,
            x0_norm,
            sigma0,
            args=args,
            options={
                "bounds": [np.zeros_like(p_min).tolist(), np.ones_like(p_max).tolist()],
                "popsize": popsize,
                "maxfevals": maxfevals,
                "seed": s,
            },
        )

        # convert history dict to DataFrame
        history_df = pd.DataFrame(history)

        results_list.append({"seed": s, "res": res, "history": history_df})

    return results_list


def run_cma_single(
    cma_seed,
    x0_norm,
    sigma0,
    objective_fn,
    popsize,
    maxfevals,
    bounds=(0.0, 1.0),
    save_folder=None,
):
    """Run a single CMA-ES calibration with a given random seed and save results optionally.

    Parameters
    ----------
    cma_seed : int
        Random seed for CMA-ES.
    x0_norm : array-like
        Initial normalized parameter vector (values in [0,1]).
    sigma0 : float
        Initial standard deviation (step size) for CMA-ES.
    objective_fn : callable
        Objective function to minimize. Should accept parameters (theta_norm) and a history dict.
    popsize : int
        CMA-ES population size.
    maxfevals : int
        Maximum number of function evaluations.
    bounds : tuple of float, optional
        Lower and upper bounds for parameters (default is (0.0, 1.0)).
    save_folder : str or Path, optional
        Folder to save results as pickle. If None, no file is saved.

    Returns:
    -------
    dict
        Dictionary containing:
        - 'seed': CMA-ES seed
        - 'best_f': best objective value found
        - 'best_x': best parameter vector found
        - 'nfev': number of function evaluations
        - 'sigma_final': final step size
        - 'history': local history of the optimization
    """
    import pickle

    import cma

    local_history = {}

    # Wrap the objective to use this local history
    def objective_wrapped(theta_norm):
        return objective_fn(theta_norm, local_history)

    es = cma.CMAEvolutionStrategy(
        x0_norm,
        sigma0,
        {
            "seed": cma_seed,
            "popsize": popsize,
            "maxfevals": maxfevals,
            "bounds": bounds,
        },
    )

    es.optimize(objective_wrapped)

    result = {
        "seed": cma_seed,
        "best_f": es.best.f,
        "best_x": es.best.x,
        "nfev": es.countevals,
        "sigma_final": es.sigma,
        "history": local_history.copy(),
    }

    # Save result if folder is provided
    if save_folder is not None:
        save_folder = Path(save_folder)
        save_folder.mkdir(parents=True, exist_ok=True)
        file_path = save_folder / f"result_seed_{cma_seed}.pkl"
        with open(file_path, "wb") as f:
            pickle.dump(result, f)
    return result


def wrap_objective_safe(forcing, q_obs, shape_name):
    """Create a “safe” objective function for HBV CMA-ES calibration with a fixed forcing and catchment.

    This returns a closure that wraps `objective_safe` with the provided forcing,
    observed streamflow, and catchment name, so it only requires `theta_norm`
    and `history` during optimization.

    Parameters
    ----------
    forcing : pd.DataFrame or dict
        Meteorological forcing data for the HBV model.
    q_obs : pd.Series
        Observed streamflow time series.
    shape_name : str
        Name of the catchment.

    Returns:
    -------
    callable
        Function of signature `objective(theta_norm, history)` compatible with CMA-ES.
    """

    def objective(theta_norm, history):
        return objective_safe(theta_norm, forcing, q_obs, shape_name, history)

    return objective


def run_hbv_for_best_params(
    shapefile: str,
    forcing_type: str,
    year_span: str,
    params_path: Path,
    initial_conditions: dict,
    leave_pbar: bool = False,
    delete_files: bool = True,
):
    """Load best parameter sets from a pickle file and run HBV simulations.

    Parameters
    ----------
    shapefile : str
        Path to the catchment shapefile.
    forcing_type : str
        Meteorological forcing type (e.g., 'ERA5').
    year_span : str
        Simulation years, e.g., '1940-2020'.
    params_path : Path
        Path to the pickle file containing best parameters dataframe.
    initial_conditions : dict
        Initial conditions for the model.
    leave_pbar : bool, optional
        Whether to leave the progress bar visible.
    delete_files : bool, optional
        Whether to delete temporary files after simulation.

    Returns:
    -------
    list of dict
        Simulation results and parameters for each parameter set.
    """
    # Load best parameters
    best_params_df = pd.read_pickle(params_path)
    parameter_sets = best_params_df[PARAMETER_NAMES].to_numpy().tolist()

    # Run HBV simulations using the previous helper function
    results = run_hbv_simulations(
        shapefile=shapefile,
        forcing_type=forcing_type,
        year_span=year_span,
        parameter_sets=parameter_sets,
        initial_conditions=initial_conditions,
        leave_pbar=leave_pbar,
        delete_files=delete_files,
    )

    return results


def run_hbv_simulations(
    shapefile: str,
    forcing_type: str,
    year_span: str,
    parameter_sets: list,
    initial_conditions: dict,
    leave_pbar: bool = False,
    delete_files: bool = True,
):
    """Run HBV simulations for a given catchment and set of parameter sets.

    Parameters
    ----------
    shapefile : str
        Path to the shapefile for the catchment.
    forcing_type : str
        Meteorological forcing type (e.g., 'ERA5').
    year_span : str
        Years to simulate, e.g., '1940-2020'.
    parameter_sets : list of lists
        Each inner list contains a set of HBV parameters.
    initial_conditions : dict
        Initial conditions for the model.
    leave_pbar : bool, optional
        Whether to leave the progress bar visible. Default is False.
    delete_files : bool, optional
        Whether to delete temporary files after simulation. Default is True.

    Returns:
    -------
    list of dict
        List of results for each parameter set. Each item contains the
        simulation output and associated parameter dictionary.
    """
    # Load forcing
    forcing = load_lumped_forcing_data(
        shape_name=shapefile, forcing_type=forcing_type, year_span=year_span
    )

    all_results = []

    for i, parameter_set in enumerate(parameter_sets):
        simulatie = simulate_HBV(
            forcing,
            parameter_set=parameter_set,
            initial_conditions=initial_conditions,
            leave_pbar=leave_pbar,
            delete_files=delete_files,
        )

        parameters = dict(zip(PARAMETER_NAMES, parameter_set))

        save_HBV_results(
            simulatie,
            shape_name=shapefile,
            forcing_type=forcing_type,
            run_tag=f"cmaes_{i:03d}",
            parameters=parameters,
        )

        all_results.append(
            {
                "simulation": simulatie,
                "parameters": parameters,
            }
        )

    return all_results



def simulate_PCRGLOBWB_experiment(
    forcing_path,
    ini_name,
    start_date,
    end_date,
    output_dir,
    ini_files_dir=None,
    container_image_path=None,
    tqdm_file=None,
):
    """Run the PCR-GLOBWB hydrological model for a given forcing and configuration.

    This function sets up and executes a PCR-GLOBWB simulation using the
    specified forcing data and parameter INI file. Currently, it relies on
    the eWaterCycle framework and a hardcoded location for global PCR-GLOBWB
    parameter sets. Progress is displayed with a tqdm bar.

    Parameters
    ----------
    forcing_path : str or Path
        Path to the folder containing PCR-GLOBWB forcing files.
    ini_name : str
        Name of the configuration INI file (e.g., "my_catchment.ini").
        This file should exist in the `ini_files_dir` directory.
    start_date : str
        Start date of the simulation in ISO 8601 format (e.g., "1950-01-01T00:00:00Z").
    end_date : str
        End date of the simulation in ISO 8601 format (e.g., "2020-12-31T00:00:00Z").
    output_dir : str or Path
        Output directory for model results.
    ini_files_dir : str or Path, optional
        Path to the directory containing INI files. If None, defaults to
        /home/avandervee3/complete_pcrglob_run/data/ini_file for backward compatibility.
    tqdm_file : file-like object, optional
        Stream to write tqdm progress output to. If omitted, tqdm uses its default
        output stream.

    Returns:
    -------
    None
        The function writes output to the eWaterCycle-managed model directory.
        Results can be accessed from the `model.output_dir` or via other
        eWaterCycle utilities.

    Notes:
    -----
    - The function currently hardcodes the location of global parameter sets:
      `/data/shared/parameter-sets/pcrglobwb_global`.
    - The `supported_model_versions` is currently set to `{"25mar"}`
    - Simulation progress is displayed via a tqdm progress bar.
    - This function does not return Python objects with results; output files
      must be read separately after the run.
    """
    from tqdm import tqdm as classic_tqdm

    # Set default ini_files_dir for backward compatibility
    if ini_files_dir is None:
        ini_files_dir = Path("/home/avandervee3/complete_pcrglob_run/data/ini_file")
    else:
        ini_files_dir = Path(ini_files_dir)

    if container_image_path is None:
        container_image_path = Path("/home/avandervee3/ewatercycle_pcr_25mar.sif")
    else:
        container_image_path = Path(container_image_path)

    bmi_image = ContainerImage(container_image_path)

    # Convert ISO 8601 strings to datetime objects
    start_time = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
    end_time = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")

    # Calculate the number of days for the progression bar
    delta = end_time - start_time
    number_of_days = delta.days

    pbar = classic_tqdm(
        total=number_of_days,
        desc="Initializing model",
        mininterval=1.0,
        file=tqdm_file,
    )

    # can be hardcoded, location of all the pcr-glob data on ewatercycle
    pcr_glob_directory = PCR_GLOBAL_PARAMS

    forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
        directory=forcing_path,
    )

    parameter_set = ewatercycle.parameter_sets.ParameterSet(
        name="custom_parameter_set",
        directory=pcr_glob_directory,
        config=ini_files_dir / ini_name,
        target_model="pcrglobwb",
        supported_model_versions={"25mar"},
    )

    model = ewatercycle.models.PCRGlobWB(parameter_set=parameter_set, forcing=forcing, bmi_image=bmi_image)

    model_config, model_dir = model.setup(
        cfg_dir=output_dir,
        start_time=start_date,
        end_time=end_date,
        max_spinups_in_years=0
    )

    model.initialize(model_config)

    pbar.set_description("Running model")
    while model.time < model.end_time:
        model.update()
        pbar.update(1)

    pbar.close()
    classic_tqdm.write("Model run finished!", file=tqdm_file)

    model.finalize()








# ---------------------------
# Backward compatibility

run_HBV_model = simulate_HBV
run_ensemble_HBV = simulate_HBV_ensemble
run_PCRGLOBWB_model = simulate_PCRGLOBWB
run_cma = run_cma_single
make_objective_safe = wrap_objective_safe
objective_safe = objective_HBV_safe
run_cma_ensemble = run_cma_multiple_seeds
