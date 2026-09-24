import csv
from pathlib import Path

DEFAULT_CONTAINER_IMAGE = Path("/home/avandervee3/ewatercycle_pcr_25mar.sif")


def resolve_container_image_path(config: dict) -> Path:
    runtime = config.get("runtime", {})
    return Path(runtime.get("pcrglobwb_container_image", DEFAULT_CONTAINER_IMAGE))


def iter_expanded_rows(config: dict, planner_csv: Path):
    with open(planner_csv, newline="", encoding="utf-8-sig") as planner_file:
        planner_rows = csv.DictReader(planner_file, delimiter=";")
        required_columns = {
            "run_id",
            "time_group",
            "model",
            "scenario",
            "forcing",
            "type",
            "parameter_set",
        }
        fieldnames = set(planner_rows.fieldnames or [])
        missing_columns = sorted(required_columns - fieldnames)
        if missing_columns:
            raise ValueError(f"experiment planner is missing columns: {', '.join(missing_columns)}")

        for planner_row in planner_rows:
            time_group = planner_row["time_group"]
            if time_group not in config["active_time_blocks"]:
                raise ValueError(f"Unknown time_group in experiment planner: {time_group}")

            for index, time_block in enumerate(config["active_time_blocks"][time_group]):
                if time_block not in config["time_blocks"]:
                    raise ValueError(f"Unknown time_block in config: {time_block}")

                yield {
                    "job_id": f'{planner_row["run_id"]}_{index:03d}',
                    "run_id": planner_row["run_id"],
                    "group": time_group,
                    "time_block": time_block,
                    "start_date": config["time_blocks"][time_block]["start_date"],
                    "end_date": config["time_blocks"][time_block]["end_date"],
                    "model": planner_row["model"],
                    "scenario": planner_row["scenario"],
                    "forcing": planner_row["forcing"],
                    "type": planner_row["type"],
                    "parameter_set": planner_row["parameter_set"],
                }


def expand_pcrglob_job_ids(config: dict, planner_csv: Path) -> list[str]:
    return [row["job_id"] for row in iter_expanded_rows(config, planner_csv)]


def infer_station_era(row: dict) -> str:
    if row["group"] == "cmip_fut":
        return "future"
    return "historical"


def slugify_path_token(value: str) -> str:
    return str(value).strip().replace(" ", "_").replace("/", "_").replace("\\", "_")


def iter_station_output_groups(config: dict, planner_csv: Path):
    grouped_rows: dict[tuple[str, str, str, str, str, str], dict] = {}

    for row in iter_expanded_rows(config, planner_csv):
        era = infer_station_era(row)
        key = (row["run_id"], row["model"], row["scenario"], row["type"], row["parameter_set"], era)

        group = grouped_rows.get(key)
        if group is None:
            group = {
                "run_id": row["run_id"],
                "model": row["model"],
                "scenario": row["scenario"],
                "type": row["type"],
                "parameter_set": row["parameter_set"],
                "era": era,
                "job_ids": [],
                "time_blocks": [],
                "start_dates": [],
                "end_dates": [],
            }
            grouped_rows[key] = group

        group["job_ids"].append(row["job_id"])
        group["time_blocks"].append(row["time_block"])
        group["start_dates"].append(row["start_date"])
        group["end_dates"].append(row["end_date"])

    return list(grouped_rows.values())


def station_job_output_path(project_root: Path, job_id: str) -> Path:
    return project_root / "results" / "runs" / "pcrglobwb" / job_id / "station_discharge.nc"


def station_merged_output_path(project_root: Path, group: dict) -> Path:
    filename = "__".join(
        (
            f"run_id={slugify_path_token(group['run_id'])}",
            f"model={slugify_path_token(group['model'])}",
            f"scenario={slugify_path_token(group['scenario'])}",
            f"type={slugify_path_token(group['type'])}",
            f"parameter_set={slugify_path_token(group['parameter_set'])}",
            f"era={slugify_path_token(group['era'])}",
        )
    )
    return project_root / "results" / "runs" / "pcrglobwb" / "stations" / "merged" / group["run_id"] / f"{filename}.nc"


def station_final_output_path(project_root: Path, era: str) -> Path:
    return project_root / "results" / "runs" / "pcrglobwb" / "stations" / "final" / f"{slugify_path_token(era)}.nc"


def resolve_forcing_flag(row: dict, config: dict) -> str:
    ensemble = config["forcing"]["ensemble"][0]
    project_root = Path(config["paths"]["project_root"])
    forcing_dir = project_root / "data" / "forcing"
    basin = config["forcing"]["basin"]
    hist_start = config["simulation_period"]["historical_cmip_start_date"][:4]
    hist_end = config["simulation_period"]["historical_cmip_end_date"][:4]
    fut_start = config["simulation_period"]["future_start_date"][:4]
    fut_end = config["simulation_period"]["future_end_date"][:4]
    era5_start = config["simulation_period"]["era5_start_date"][:4]
    era5_end = config["simulation_period"]["era5_end_date"][:4]

    if row["forcing"] == "era5":
        return str(forcing_dir / "ERA5" / "raw" / f"{era5_start}-{era5_end}" / basin / "generated.flag")

    if row["forcing"] == "cmip" and row["scenario"] == "historical":
        return str(
            forcing_dir
            / "CMIP6"
            / "historical"
            / row["type"]
            / row["model"]
            / ensemble
            / f"{hist_start}-{hist_end}"
            / basin
            / "generated.flag"
        )

    # if row["forcing"] == "cmip" and row["scenario"] == "historical" and row["type"] == "bias_corrected":
    #     return str(
    #         forcing_dir
    #         / "CMIP6"
    #         / "historical"
    #         / "bias_corrected"
    #         / row["model"]
    #         / ensemble
    #         / f"{hist_start}-{hist_end}"
    #         / basin
    #         / "generated.flag"
    #     )

    if row["forcing"] == "cmip" and row["group"] == "cmip_fut":
        return str(
            forcing_dir
            / "CMIP6"
            / "future"
            / row["type"]
            / row["model"]
            / row["scenario"]
            / ensemble
            / f"{fut_start}-{fut_end}"
            / basin
            / "generated.flag"
        )

    raise ValueError(f"Unsupported PCR-GLOBWB experiment row for job_id={row['job_id']!r}: {row}")


def build_run_manifest(config: dict, planner_csv: Path, job_id: str) -> dict:
    selected_row = None
    for row in iter_expanded_rows(config, planner_csv):
        if row["job_id"] == job_id:
            selected_row = row
            break

    if selected_row is None:
        raise ValueError(f"No expanded run row found for job_id={job_id!r}")

    parameter_set = selected_row["parameter_set"]
    if parameter_set not in config["parameter_sets"]:
        raise KeyError(f"Unknown parameter_set={parameter_set!r} in config_aral.yaml")

    return {
        "job": selected_row,
        "forcing": {
            "ewatercycle_tail": config["forcing"]["ewatercycle_tail"],
            "input_flag": resolve_forcing_flag(selected_row, config),
        },
        "parameter_sets": {
            parameter_set: config["parameter_sets"][parameter_set],
        },
        "runtime": {
            "container_image": str(resolve_container_image_path(config)),
            "project_root": str(Path(config["paths"]["project_root"])),
            "planner_csv": str(planner_csv),
        },
    }


def collect_preflight_errors(config: dict, planner_csv: Path | None = None) -> list[str]:
    errors: list[str] = []

    project_root = Path(config["paths"]["project_root"])
    shapefiles_dir = project_root / config["paths"]["shapefiles_dir"].lstrip("./")
    planner_csv = planner_csv or (project_root / "config" / "experiment_planner.csv")
    container_image = resolve_container_image_path(config)

    for label, path in [
        ("project root", project_root),
        ("shapefiles", shapefiles_dir),
        ("experiment planner", planner_csv),
        ("PCR-GLOBWB container image", container_image),
    ]:
        if not Path(path).exists():
            errors.append(f"{label} not found: {path}")

    for section_name in ("time_blocks", "active_time_blocks", "parameter_sets"):
        if section_name not in config:
            errors.append(f"Missing config section: {section_name}")

    if "time_blocks" in config and "active_time_blocks" in config:
        for group, blocks in config["active_time_blocks"].items():
            for block in blocks:
                if block not in config["time_blocks"]:
                    errors.append(f"Unknown time_block in active_time_blocks: {group} -> {block}")

    if "parameter_sets" in config:
        for name, parameter_set in config["parameter_sets"].items():
            parameter_path = project_root / parameter_set["path"]
            if not parameter_path.exists():
                errors.append(f"parameter_set not found: {name} -> {parameter_path}")

    if planner_csv.exists():
        try:
            list(iter_expanded_rows(config, planner_csv))
        except Exception as exc:
            errors.append(str(exc))

    return errors
