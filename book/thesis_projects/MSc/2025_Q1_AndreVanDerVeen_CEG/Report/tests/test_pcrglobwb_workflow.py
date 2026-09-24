from pathlib import Path

import yaml

from src.pcrglobwb_workflow import (
    build_run_manifest,
    collect_preflight_errors,
    expand_pcrglob_job_ids,
    resolve_container_image_path,
)


ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with open(ROOT / "config_aral.yaml", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def test_expanded_job_ids_include_known_runs() -> None:
    config = load_config()
    planner_csv = ROOT / "config" / "experiment_planner.csv"

    job_ids = expand_pcrglob_job_ids(config, planner_csv)

    assert job_ids
    assert all(job_id.count("_") == 1 for job_id in job_ids)


def test_build_run_manifest_resolves_forcing_and_container_image() -> None:
    config = load_config()
    planner_csv = ROOT / "config" / "experiment_planner.csv"

    manifest = build_run_manifest(config, planner_csv, "r001_000")

    assert manifest["job"]["job_id"] == "r001_000"
    assert manifest["forcing"]["input_flag"].endswith("generated.flag")
    assert manifest["runtime"]["container_image"].endswith("ewatercycle_pcr_25mar.sif")


def test_collect_preflight_errors_is_empty_for_current_repo_state() -> None:
    config = load_config()

    assert resolve_container_image_path(config).name == "ewatercycle_pcr_25mar.sif"
    assert collect_preflight_errors(config) == []
