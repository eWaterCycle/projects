from datetime import datetime, timezone
from pathlib import Path
import sys
import traceback

import numpy as np
import xarray as xr  # pyright: ignore[reportMissingTypeStubs]
import yaml  # pyright: ignore[reportMissingTypeStubs]

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pcrglobwb_workflow import build_run_manifest, infer_station_era


def load_config(config_yaml: Path) -> dict:
    with open(config_yaml, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_stations(config: dict) -> list[dict]:
    stations = config.get("discharge_stations")
    if not stations:
        raise ValueError("config_aral.yaml does not define any discharge_stations")

    required_keys = {"name", "lat", "lon"}
    for index, station in enumerate(stations):
        missing = sorted(required_keys - set(station))
        if missing:
            raise ValueError(f"discharge_stations[{index}] is missing keys: {', '.join(missing)}")

    return stations


def build_station_dataset(source_ds: xr.Dataset, stations: list[dict], run_manifest: dict, source_attrs: dict, source_file: Path) -> xr.Dataset:
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
    discharge.name = "discharge"
    discharge.attrs = {
        **source_attrs,
        "long_name": "PCR-GLOBWB discharge at the nearest grid cell for each observation station",
        "source_variable": source_attrs.get("source_variable", source_attrs.get("long_name", "discharge")),
        "station_selection": "nearest_grid_cell",
        "station_source": "config_aral.yaml:discharge_stations",
    }

    dataset = discharge.to_dataset(name="discharge")
    dataset = dataset.assign_coords(station=("station", names))
    dataset["station"].attrs.update(
        {
            "long_name": "Discharge observation station",
            "description": "Station names taken from config_aral.yaml",
        }
    )
    dataset["time"].attrs.setdefault("long_name", "Time axis of the source PCR-GLOBWB run")

    job = run_manifest["job"]
    stations_csv = ",".join(names)
    lat_csv = ",".join(f"{value:.6f}" for value in latitudes)
    lon_csv = ",".join(f"{value:.6f}" for value in longitudes)

    dataset.attrs.update(
        {
            "title": "Station discharge extracted from PCR-GLOBWB output",
            "summary": "Per-job station discharge extracted from a finished PCR-GLOBWB run.",
            "job_id": job["job_id"],
            "run_id": job["run_id"],
            "time_block": job["time_block"],
            "start_date": job["start_date"],
            "end_date": job["end_date"],
            "group": job["group"],
            "era": infer_station_era(job),
            "model": job["model"],
            "scenario": job["scenario"],
            "forcing": job["forcing"],
            "type": job["type"],
            "parameter_set": job["parameter_set"],
            "station_count": len(names),
            "station_names": stations_csv,
            "station_latitudes": lat_csv,
            "station_longitudes": lon_csv,
            "source_run_output": str(source_file),
            "planner_csv": run_manifest["runtime"]["planner_csv"],
            "config_yaml": str(Path(snakemake.input.yaml).resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "processing_step": "extract_pcrglobwb_outputs",
        }
    )

    return dataset


config_yaml = Path(snakemake.input.yaml)
planner_csv = Path(snakemake.input.planner)
finished_flag = Path(snakemake.input.flag)
output_nc = Path(snakemake.output.station_nc)
output_flag = Path(snakemake.output.flag)
log_file = Path(snakemake.log[0])
job_id = snakemake.wildcards.job_id

try:
    config = load_config(config_yaml)
    run_manifest = build_run_manifest(config, planner_csv, job_id)
    stations = load_stations(config)

    job_dir = output_nc.parent
    source_file = job_dir / "netcdf" / "discharge_dailyTot_output.nc"
    if not source_file.exists():
        raise FileNotFoundError(f"PCR-GLOBWB discharge output not found: {source_file}")

    with xr.open_dataset(source_file) as source_ds:
        if "discharge" in source_ds.data_vars:
            source_var = "discharge"
        elif "discharge_dailyTot" in source_ds.data_vars:
            source_var = "discharge_dailyTot"
        else:
            source_var = list(source_ds.data_vars)[0]

        normalized = source_ds.rename({source_var: "discharge"}) if source_var != "discharge" else source_ds
        _, unique_indices = np.unique(normalized["time"].values, return_index=True)
        normalized = normalized.isel(time=np.sort(unique_indices))
        source_attrs = dict(source_ds[source_var].attrs)
        source_attrs["source_variable"] = source_var

        dataset = build_station_dataset(normalized, stations, run_manifest, source_attrs, source_file)
        output_nc.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_nc.with_suffix(".tmp.nc")
        dataset.to_netcdf(tmp_path, encoding={"discharge": {"zlib": True, "complevel": 4}})
        tmp_path.replace(output_nc)

    output_flag.parent.mkdir(parents=True, exist_ok=True)
    output_flag.touch()

    with open(log_file, "a", encoding="utf-8") as log_stream:
        log_stream.write(f"Finished station extraction for {job_id}\n")
        log_stream.write(f"Finished flag: {finished_flag}\n")
        log_stream.write(f"Output: {output_nc}\n")
except Exception:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as log_stream:
        log_stream.write(traceback.format_exc())
    raise
