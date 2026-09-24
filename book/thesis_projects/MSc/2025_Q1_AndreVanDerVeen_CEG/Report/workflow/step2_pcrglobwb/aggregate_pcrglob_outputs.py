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


def load_config(config_yaml: Path) -> dict:
    with open(config_yaml, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_stations(config: dict) -> list[dict]:
    stations = config.get("discharge_stations")
    if not stations:
        raise ValueError("config_aral.yaml does not define any discharge_stations")
    return stations


def station_attr_strings(stations: list[dict]) -> tuple[str, str, str]:
    names = ",".join(station["name"] for station in stations)
    latitudes = ",".join(f"{float(station['lat']):.6f}" for station in stations)
    longitudes = ",".join(f"{float(station['lon']):.6f}" for station in stations)
    return names, latitudes, longitudes


def era_output_path(output_historical: Path, output_future: Path, era: str) -> Path:
    if era == "historical":
        return output_historical
    if era == "future":
        return output_future
    raise ValueError(f"Unsupported era: {era!r}")


def experiment_label(dataset: xr.Dataset) -> str:
    return "__".join(
        (
            f"run_id={dataset.attrs.get('run_id', 'unknown')}",
            f"model={dataset.attrs.get('model', 'unknown')}",
            f"scenario={dataset.attrs.get('scenario', 'unknown')}",
            f"type={dataset.attrs.get('type', 'unknown')}",
            f"parameter_set={dataset.attrs.get('parameter_set', 'unknown')}",
            f"era={dataset.attrs.get('era', 'unknown')}",
        )
    )


def load_experiment_dataset(path: Path) -> xr.Dataset:
    if not path.exists():
        raise FileNotFoundError(f"Missing merged experiment station file: {path}")

    with xr.open_dataset(path, chunks={"time": 365}) as dataset:
        loaded = dataset.load()

    return loaded


def write_dataset(path: Path, dataset: xr.Dataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.nc")
    dataset.to_netcdf(tmp_path, encoding={"discharge": {"zlib": True, "complevel": 4}})
    tmp_path.replace(path)


config_yaml = Path(snakemake.input.yaml)
experiment_files = [Path(path) for path in snakemake.input.station_files]
output_historical = Path(snakemake.output.historical)
output_future = Path(snakemake.output.future)
log_file = Path(snakemake.log[0])

try:
    config = load_config(config_yaml)
    stations = load_stations(config)
    station_names, station_latitudes, station_longitudes = station_attr_strings(stations)

    grouped_files = {"historical": [], "future": []}
    for path in experiment_files:
        dataset = load_experiment_dataset(path)
        era = dataset.attrs.get("era")
        if era not in grouped_files:
            raise ValueError(f"Unexpected era {era!r} in source file {path}")
        grouped_files[era].append((path, dataset))

    for era, era_files in grouped_files.items():
        if not era_files:
            raise ValueError(f"No source experiment files available for {era} output")

        era_labels = [experiment_label(dataset) for _, dataset in era_files]
        era_datasets = [dataset for _, dataset in era_files]

        station_values = None
        discharge_attrs = None
        station_attrs = None
        for dataset in era_datasets:
            if station_values is None:
                station_values = dataset["station"].values
                station_attrs = dict(dataset["station"].attrs)
                discharge_attrs = dict(dataset["discharge"].attrs)
            elif not np.array_equal(station_values, dataset["station"].values):
                raise ValueError(f"Station coordinates differ in {era} aggregate inputs")

        merged = xr.concat(
            era_datasets,
            dim=xr.DataArray(era_labels, dims="experiment", name="experiment"),
            join="outer",
            combine_attrs="override",
        )
        merged = merged.sortby("experiment")

        discharge = merged["discharge"]
        discharge.attrs = {
            **(discharge_attrs or {}),
            "long_name": "PCR-GLOBWB station discharge aggregated across experiments",
            "merge_strategy": "concatenate_along_experiment_and_align_time",
            "source_variable": "discharge",
            "aggregated_experiment_count": str(len(era_datasets)),
        }

        dataset = discharge.to_dataset(name="discharge")
        if station_values is not None:
            dataset = dataset.assign_coords(station=("station", station_values))
        if station_attrs:
            dataset["station"].attrs.update(station_attrs)
        dataset["station"].attrs.setdefault("long_name", "Discharge observation station")
        dataset["station"].attrs.setdefault("description", "Station names taken from config_aral.yaml")
        dataset["experiment"].attrs.update(
            {
                "long_name": "Merged experiment identifier",
                "description": "Experiment keys derived from run_id, model, scenario, type, parameter_set, and era.",
            }
        )
        dataset["time"].attrs.setdefault("long_name", "Time axis of the aggregated PCR-GLOBWB runs")

        source_files = ",".join(str(path) for path, _ in era_files)
        source_labels = ",".join(era_labels)
        source_run_ids = ",".join(dataset.attrs.get("run_id", "unknown") for _, dataset in era_files)
        source_models = ",".join(dataset.attrs.get("model", "unknown") for _, dataset in era_files)
        source_scenarios = ",".join(dataset.attrs.get("scenario", "unknown") for _, dataset in era_files)
        source_types = ",".join(dataset.attrs.get("type", "unknown") for _, dataset in era_files)
        source_parameter_sets = ",".join(dataset.attrs.get("parameter_set", "unknown") for _, dataset in era_files)
        source_job_ids = ",".join(dataset.attrs.get("source_job_ids", "") for _, dataset in era_files)

        dataset.attrs.update(
            {
                "title": f"Aggregated PCR-GLOBWB station discharge ({era})",
                "summary": "Station discharge aggregated across experiment-level merged outputs.",
                "era": era,
                "station_count": len(stations),
                "station_names": station_names,
                "station_latitudes": station_latitudes,
                "station_longitudes": station_longitudes,
                "source_experiment_labels": source_labels,
                "source_experiment_files": source_files,
                "source_run_ids": source_run_ids,
                "source_models": source_models,
                "source_scenarios": source_scenarios,
                "source_types": source_types,
                "source_parameter_sets": source_parameter_sets,
                "source_job_ids": source_job_ids,
                "config_yaml": str(config_yaml),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "processing_step": "aggregate_pcrglobwb_station_outputs",
                "merge_axis": "experiment",
            }
        )

        write_dataset(era_output_path(output_historical, output_future, era), dataset)

    with open(log_file, "a", encoding="utf-8") as log_stream:
        log_stream.write("Aggregated station outputs into historical and future files\n")
except Exception:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as log_stream:
        log_stream.write(traceback.format_exc())
    raise
