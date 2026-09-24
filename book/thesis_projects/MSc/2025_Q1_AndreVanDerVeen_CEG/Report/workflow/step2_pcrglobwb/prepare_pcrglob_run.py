from pathlib import Path

import yaml  # pyright: ignore[reportMissingTypeStubs]

from src.pcrglobwb_workflow import build_run_manifest


planner_csv = snakemake.input.planner
config_yaml = snakemake.input.yaml
output_yaml = snakemake.output.run_config


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


with open(config_yaml, encoding="utf-8") as config_file:
    config = yaml.safe_load(config_file)

run_config = build_run_manifest(config, Path(planner_csv), snakemake.wildcards.job_id)

write_text_if_changed(Path(output_yaml), yaml.safe_dump(run_config, sort_keys=True))
