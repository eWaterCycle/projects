import argparse
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # pyright: ignore[reportMissingTypeStubs]

from src.models import simulate_PCRGLOBWB_experiment
from src.pcrglobwb_workflow import build_run_manifest, resolve_container_image_path


def resolve_ini_name(config: dict, parameter_set: str) -> str:
    try:
        parameter_path = Path(config["parameter_sets"][parameter_set]["path"])
    except KeyError as exc:
        raise KeyError(f"Unknown parameter_set={parameter_set!r} in config_aral.yaml") from exc
    return parameter_path.name


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_config(config_yaml: Path) -> dict:
    with open(config_yaml, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def run_job(config_yaml: Path, planner_csv: Path, job_id: str, output_flag: Path, log_file: Path) -> None:
    config = load_config(config_yaml)
    run_manifest = build_run_manifest(config, planner_csv, job_id)

    run_output_dir = output_flag.parent
    run_output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_output_dir / "run_manifest.yaml"
    manifest_text = yaml.safe_dump(run_manifest, sort_keys=True)

    if output_flag.exists():
        if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") == manifest_text:
            return
        raise RuntimeError(
            f"Refusing to rerun completed job {job_id!r}; remove {output_flag} only if you intend to rerun it."
        )

    if manifest_path.exists():
        existing_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest != run_manifest:
            raise RuntimeError(
                f"Existing run manifest for {job_id!r} does not match the requested run; refusing to overwrite it."
            )
    else:
        write_text_if_changed(manifest_path, manifest_text)

    job = run_manifest["job"]
    parameter_set = str(job["parameter_set"])
    ini_name = resolve_ini_name(run_manifest, parameter_set)

    forcing_flag = Path(run_manifest["forcing"]["input_flag"])
    forcing_tail = Path(run_manifest["forcing"]["ewatercycle_tail"])
    forcing_dir = forcing_flag.parent / forcing_tail

    ini_files_dir = Path(config["paths"]["project_root"]) / "data" / "ini_file"
    container_image = resolve_container_image_path(config)

    with open(log_file, "a", encoding="utf-8") as log_stream:
        log_stream.write(
            f"Starting {job_id} ({job['run_id']} / {job['time_block']})\n"
        )
        log_stream.write(f"Dates: {job['start_date']} -> {job['end_date']}\n")
        log_stream.write(f"Forcing flag: {forcing_flag}\n")
        log_stream.write(f"Forcing dir: {forcing_dir}\n")
        log_stream.write(f"Parameter set: {parameter_set} -> {ini_name}\n")
        log_stream.write(f"Container image: {container_image}\n")

        with redirect_stdout(log_stream), redirect_stderr(log_stream):
            simulate_PCRGLOBWB_experiment(
                forcing_dir,
                ini_name,
                job["start_date"],
                job["end_date"],
                run_output_dir,
                ini_files_dir=ini_files_dir,
                container_image_path=container_image,
                tqdm_file=log_stream,
            )

        output_flag.touch()
        log_stream.write(f"Finished {job_id}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one PCR-GLOBWB experiment from the planner.")
    parser.add_argument("--config-yaml", required=True)
    parser.add_argument("--planner-csv", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-flag", required=True)
    parser.add_argument("--log-file", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_job(
        Path(args.config_yaml),
        Path(args.planner_csv),
        args.job_id,
        Path(args.output_flag),
        Path(args.log_file),
    )


if __name__ == "__main__":
    main()
