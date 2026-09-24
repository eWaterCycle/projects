
"""
This script runs the Karakum Canal water removal experiments with PCR-GLOBWB.

It is a refactored and parameterized version of the `karalkum_experiment.ipynb`
notebook, designed to be run from the command line for different time periods.

The script runs three parallel experiments:
1.  `single_point`: Water is removed from a single grid cell.
2.  `multi_point`: Water is removed from multiple grid cells.
3.  `wave`: Water removal from multiple cells follows a seasonal wave pattern.

The annual water removal target is read from `KarakumCanal.csv` and can be
scaled. The script is configured to use the Amu Darya calibrated parameter set
and ERA5 forcing data.

Example usage:
    python run_karakum_experiments.py --start-date 1965-01-01 --end-date 1995-12-31 --output-dir /path/to/output
"""

import sys
from datetime import datetime
from pathlib import Path
import yaml

import numpy as np
import pandas as pd
import xarray as xr
from rich import print
from tqdm import tqdm

import ewatercycle.forcing
import ewatercycle.models
import ewatercycle.parameter_sets
from ewatercycle.container import ContainerImage

def load_config(config_path: str) -> dict:
    """Loads the YAML config file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_karakum_data(csv_path: str, scaling_factor: float) -> pd.DataFrame:
    """Loads and processes the Karakum Canal water removal data."""
    df = pd.read_csv(csv_path, delimiter=';', decimal=',')
    df["m3s_scaled"] = df["m3s"] * scaling_factor
    df = df.set_index("year")
    return df



def get_yearly_removal_target(year: int, karakum_df: pd.DataFrame) -> float:
    """
    Gets the water removal target for a given year.

    - Returns 0 for years before the data starts.
    - Returns the last available value for years after the data ends.
    """
    if year in karakum_df.index:
        return karakum_df.loc[year, "m3s_scaled"]
    elif year < karakum_df.index.min():
        return 0.0
    else: # year > karakum_df.index.max()
        return karakum_df["m3s_scaled"].iloc[-1]


def run_single_experiment(experiment_name: str, config: dict, snakemake_params: dict):
    """Main function to set up and run a single experiment."""
    # --- Load Data and Set Up ---
    exp_config = config['karakum_experiment']
    project_root = Path(config['paths']['project_root'])
    output_dir = Path(snakemake_params.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    karakum_df = load_karakum_data(
        project_root / exp_config['karakum_canal_csv'],
        exp_config['removal_scaling_factor']
    )
    
    experiment_start_date = f"{snakemake_params.start_date}T00:00:00Z"
    experiment_end_date = f"{snakemake_params.end_date}T00:00:00Z"

    # --- eWaterCycle Model Setup ---
    # The parameter_set requires a directory with all the static data (maps, etc.)
    # and a config .ini file that points to them.
    # parameter_set = ewatercycle.parameter_sets.load(exp_config['parameter_set_name'])

    parameter_set = ewatercycle.parameter_sets.ParameterSet(
        name="custom_parameter_set",
        directory=exp_config['PCR_GLOBAL_PARAMS'],
        config=exp_config['karalkum_ini'],
        target_model="pcrglobwb",
        supported_model_versions={"25mar"},
    )

    forcing_path = Path(snakemake.input.era5_forcing_flag).parent / config["forcing"]["ewatercycle_tail"]
    forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
        directory=forcing_path,
    )
    
    bmi_image = ContainerImage(exp_config['pcrglobwb_container'])

    model = ewatercycle.models.PCRGlobWB(parameter_set=parameter_set, forcing=forcing, bmi_image=bmi_image)


    
    # Overwrite the default config with our experiment-specific one
    cfg_dir = output_dir / f"config_{experiment_name}"

    cfg_file, cfg_dir = model.setup(
        start_time=experiment_start_date,
        end_time=experiment_end_date,
        max_spinups_in_years=0,
        cfg_dir=str(cfg_dir),
    )
    model.initialize(cfg_file)

    # --- Simulation Loop ---
    start_dt = datetime.strptime(experiment_start_date, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(experiment_end_date, "%Y-%m-%dT%H:%M:%SZ")
    number_of_days = (end_dt - start_dt).days

    # load station coordinates and indices from config
    stations_pcr = exp_config['stations']
    single_point_coords = exp_config['single_point_coords']
    multi_point_coords = [tuple(c) for c in exp_config['multi_point_coords']]
    single_point_lat_idx, single_point_lon_idx = single_point_coords[0], single_point_coords[1]

    timestamps = []
    station_records = {st: {"discharge": [], "channel_storage": []} for st in stations_pcr}
    history = []

    

    with open(Path(cfg_dir) / "progress.log", "w") as progress_log:
        for i in tqdm(range(number_of_days), desc=f"Running experiment: {experiment_name}", file=progress_log):
            current_time = pd.to_datetime(model.time_as_isostr)
            timestamps.append(current_time)
            
            # Get this year's removal target
            annual_target_m3s = get_yearly_removal_target(current_time.year, karakum_df)
            daily_removal_target_m3 = annual_target_m3s * (24 * 3600) # Convert flow rate to daily volume

            # Update model and record station data
            model.update()
            for station_name, coords in stations_pcr.items():
                discharge = model.get_value_at_coords("discharge", lat=[coords["lat"]], lon=[coords["lon"]])
                channel_storage = model.get_value_at_coords("channel_storage", lat=[coords["lat"]], lon=[coords["lon"]])
                station_records[station_name]["discharge"].append(float(discharge[0]))
                station_records[station_name]["channel_storage"].append(float(channel_storage[0]))

            # --- Apply Perturbations ---
            storage = model.get_value_as_xarray("channel_storage").values.copy()
            
            if experiment_name == "single_point":
                old_val = storage[single_point_lat_idx, single_point_lon_idx]
                if old_val > 0:
                    factor = np.clip((old_val - daily_removal_target_m3) / old_val, 0.2, 1.0)
                    storage[single_point_lat_idx, single_point_lon_idx] *= factor
                change = storage[single_point_lat_idx, single_point_lon_idx] - old_val
                history.append(change)

            elif experiment_name in ["multi_point", "wave"]:
                changes = {}
                if experiment_name == "multi_point":
                    target_per_cell = daily_removal_target_m3 / len(multi_point_coords)
                else: # wave
                    doy = current_time.day_of_year
                    seasonal_target = (1 - np.cos(2 * np.pi * (doy - 1) / 365)) * daily_removal_target_m3
                    target_per_cell = seasonal_target / len(multi_point_coords)

                for lat_idx, lon_idx in multi_point_coords:
                    old_val = storage[lat_idx, lon_idx]
                    if old_val > 0:
                        factor = np.clip((old_val - target_per_cell) / old_val, 0.2, 1.0)
                        storage[lat_idx, lon_idx] *= factor
                    changes[(lat_idx, lon_idx)] = storage[lat_idx, lon_idx] - old_val
                history.append(changes)

            model.set_value("channel_storage", storage.flatten())

    print("Simulation finished. Saving results...")

    # --- Finalize and Save Results ---
    model.finalize()

    datetime_timestamps = np.array(timestamps, dtype="datetime64[ns]")

    # Save station data
    ds_station = xr.Dataset(
        data_vars={
            f"{station}_{var}": ("time", values)
            for station, vars_dict in station_records.items()
            for var, values in vars_dict.items()
        },
        coords={"time": datetime_timestamps}
    )
    ds_station.to_netcdf(output_dir / f"karakum_experiment_{experiment_name}_station_data.nc")

    # Save storage change history
    if experiment_name == "single_point":
        ds_results = xr.Dataset(
            {"storage_change": ("time", history)},
            coords={"time": datetime_timestamps}
        )
    else: # multi_point or wave
        unique_lats = sorted(list(set(c[0] for c in multi_point_coords)))
        unique_lons = sorted(list(set(c[1] for c in multi_point_coords)))
        lat_map = {lat: i for i, lat in enumerate(unique_lats)}
        lon_map = {lon: i for i, lon in enumerate(unique_lons)}
        grid_data = np.zeros((len(datetime_timestamps), len(unique_lats), len(unique_lons)))
        for t_idx, daily_dict in enumerate(history):
            for coord, value in daily_dict.items():
                grid_data[t_idx, lat_map[coord[0]], lon_map[coord[1]]] = value
        ds_results = xr.Dataset(
            {"storage_change": (["time", "lat", "lon"], grid_data)},
            coords={"time": datetime_timestamps, "lat": unique_lats, "lon": unique_lons}
        )
    
    ds_results.to_netcdf(output_dir / f"karakum_experiment_{experiment_name}.nc")

    print(f"Successfully saved all results for {experiment_name} to {output_dir}")


def main():
    """Loads config and runs the specified experiment."""
    config = load_config(snakemake.params.config_file)
    experiment_name = snakemake.wildcards.experiment
    run_single_experiment(experiment_name, config, snakemake.params)


if __name__ == "__main__":
    main()

