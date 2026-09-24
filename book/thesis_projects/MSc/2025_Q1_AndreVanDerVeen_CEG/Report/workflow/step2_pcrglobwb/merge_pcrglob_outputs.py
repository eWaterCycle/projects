from datetime import datetime, timezone
from pathlib import Path
import csv
import sys
import traceback

import numpy as np
import xarray as xr  # pyright: ignore[reportMissingTypeStubs]
import yaml  # pyright: ignore[reportMissingTypeStubs]

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pcrglobwb_workflow import infer_station_era


def load_config(config_yaml: Path) -> dict:
    with open(config_yaml, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_expanded_rows(expanded_runs_csv: Path) -> list[dict]:
    with open(expanded_runs_csv, newline="", encoding="utf-8") as run_file:
        return list(csv.DictReader(run_file))


def load_stations(config: dict) -> list[dict]:
    stations = config.get("discharge_stations")
    if not stations:
        raise ValueError("config_aral.yaml does not define any discharge_stations")
    return stations


def source_output_path(project_root: Path, job_id: str) -> Path:
    return project_root / "results" / "runs" / "pcrglobwb" / job_id / "netcdf" / "discharge_dailyTot_output.nc"


def finished_run_flag(project_root: Path, job_id: str) -> Path:
    return project_root / "results" / "runs" / "pcrglobwb" / job_id / "generated.flag"


def station_attr_strings(stations: list[dict]) -> tuple[str, str, str]:
    names = ",".join(station["name"] for station in stations)
    latitudes = ",".join(f"{float(station['lat']):.6f}" for station in stations)
    longitudes = ",".join(f"{float(station['lon']):.6f}" for station in stations)
    return names, latitudes, longitudes


def select_rows_for_output(rows: list[dict], wildcards) -> list[dict]:
    selected = []
    for row in rows:
        if row["run_id"] != wildcards.run_id:
            continue
        if row["model"] != wildcards.model:
            continue
        if row["scenario"] != wildcards.scenario:
            continue
        if row["type"] != wildcards.type:
            continue
        if row["parameter_set"] != wildcards.parameter_set:
            continue
        if infer_station_era(row) != wildcards.era:
            continue
        selected.append(row)
    return selected


def write_dataset(path: Path, dataset: xr.Dataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.nc")
    dataset.to_netcdf(tmp_path, encoding={"discharge": {"zlib": True, "complevel": 4}})
    tmp_path.replace(path)


def extract_station_data(source_ds: xr.Dataset, stations: list[dict]) -> xr.Dataset:
    names = [station["name"] for station in stations]
    latitudes = np.array([station["lat"] for station in stations], dtype=float)
    longitudes = np.array([station["lon"] for station in stations], dtype=float)

    lat_indices = np.array([np.abs(source_ds["lat"].values - lat).argmin() for lat in latitudes])
    lon_indices = np.array([np.abs(source_ds["lon"].values - lon).argmin() for lon in longitudes])

    discharge = source_ds["discharge"].isel(
        lat=xr.DataArray(lat_indices, dims="station"),
        lon=xr.DataArray(lon_indices, dims="station"),
    )
    discharge = discharge.assign_coords(station=("station", names))
    return discharge.to_dataset(name="discharge")


config_yaml = Path(snakemake.input.yaml)
expanded_runs_csv = Path(snakemake.input.expanded_runs)
output_nc = Path(snakemake.output[0])
log_file = Path(snakemake.log[0])
project_root = Path(yaml.safe_load(config_yaml.read_text(encoding="utf-8"))["paths"]["project_root"])

try:
    config = load_config(config_yaml)
    rows = load_expanded_rows(expanded_runs_csv)
    stations = load_stations(config)
    station_names, station_latitudes, station_longitudes = station_attr_strings(stations)
    selected_rows = select_rows_for_output(rows, snakemake.wildcards)

    if not selected_rows:
        raise ValueError(f"No expanded runs match the requested merged output: {output_nc}")

    datasets = []
    reference_station_values = None
    reference_station_attrs = None
    reference_discharge_attrs = None
    source_job_ids = []
    source_time_blocks = []
    source_start_dates = []
    source_end_dates = []

    for row in selected_rows:
        job_id = row["job_id"]
        finished_flag = finished_run_flag(project_root, job_id)
        source_file = source_output_path(project_root, job_id)
        if not finished_flag.exists() or not source_file.exists():
            continue

        with xr.open_dataset(source_file, chunks={"time": 365}) as ds:
            if "discharge" in ds.data_vars:
                source_var = "discharge"
            elif "discharge_dailyTot" in ds.data_vars:
                source_var = "discharge_dailyTot"
            else:
                source_var = list(ds.data_vars)[0]

            normalized = ds.rename({source_var: "discharge"}) if source_var != "discharge" else ds
            _, unique_indices = np.unique(normalized["time"].values, return_index=True)
            normalized = normalized.isel(time=np.sort(unique_indices))
            loaded = extract_station_data(normalized, stations).load()

        station_values = loaded["station"].values
        if reference_station_values is None:
            reference_station_values = station_values
            reference_station_attrs = dict(loaded["station"].attrs)
            reference_discharge_attrs = dict(loaded["discharge"].attrs)
        elif not np.array_equal(reference_station_values, station_values):
            raise ValueError(f"Station coordinates differ between finished runs; cannot merge job {job_id}")

        datasets.append(loaded)
        source_job_ids.append(job_id)
        source_time_blocks.append(row["time_block"])
        source_start_dates.append(row["start_date"])
        source_end_dates.append(row["end_date"])

    if not datasets:
        raise ValueError(
            "No finished PCR-GLOBWB runs were available for this merged output. "
            "The script only consumes existing generated.flag and raw discharge files."
        )

    merged = xr.concat(datasets, dim="time")
    merged = merged.sortby("time")
    _, unique_indices = np.unique(merged["time"].values, return_index=True)
    merged = merged.isel(time=np.sort(unique_indices))

    discharge = merged["discharge"]
    discharge.attrs = {
        **(reference_discharge_attrs or {}),
        "long_name": "PCR-GLOBWB discharge merged across job-level station extractions",
        "merge_strategy": "concatenate_along_time_and_drop_duplicate_timestamps",
        "source_variable": "discharge",
        "merged_job_count": str(len(selected_rows)),
    }

    dataset = discharge.to_dataset(name="discharge")
    dataset = dataset.assign_coords(station=("station", reference_station_values if reference_station_values is not None else []))
    if reference_station_attrs:
        dataset["station"].attrs.update(reference_station_attrs)
    dataset["station"].attrs.setdefault("long_name", "Discharge observation station")
    dataset["station"].attrs.setdefault("description", "Station names taken from config_aral.yaml")
    dataset["time"].attrs.setdefault("long_name", "Time axis of the merged PCR-GLOBWB runs")

    dataset.attrs.update(
        {
            "title": "Merged PCR-GLOBWB station discharge",
            "summary": "Merged station discharge for a single run definition and era.",
            "run_id": snakemake.wildcards.run_id,
            "model": snakemake.wildcards.model,
            "scenario": snakemake.wildcards.scenario,
            "type": snakemake.wildcards.type,
            "parameter_set": snakemake.wildcards.parameter_set,
            "era": snakemake.wildcards.era,
            "station_count": len(stations),
            "station_names": station_names,
            "station_latitudes": station_latitudes,
            "station_longitudes": station_longitudes,
            "source_job_ids": ",".join(source_job_ids),
            "source_time_blocks": ",".join(source_time_blocks),
            "source_start_dates": ",".join(source_start_dates),
            "source_end_dates": ",".join(source_end_dates),
            "expanded_runs_csv": str(expanded_runs_csv),
            "config_yaml": str(config_yaml),
            "source_discharge_files": ",".join(str(source_output_path(project_root, job_id)) for job_id in source_job_ids),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "processing_step": "merge_pcrglobwb_station_outputs",
            "merge_axis": "time",
        }
    )

    write_dataset(output_nc, dataset)

    with open(log_file, "a", encoding="utf-8") as log_stream:
        log_stream.write(f"Merged station outputs to {output_nc}\n")
        log_stream.write(f"Source job ids: {', '.join(source_job_ids)}\n")
except Exception:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as log_stream:
        log_stream.write(traceback.format_exc())
    raise
