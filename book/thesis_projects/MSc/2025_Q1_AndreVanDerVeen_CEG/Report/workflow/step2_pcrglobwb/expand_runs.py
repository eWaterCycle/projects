from pathlib import Path

import pandas as pd  # pyright: ignore[reportMissingTypeStubs]
import yaml  # pyright: ignore[reportMissingTypeStubs]

from src.pcrglobwb_workflow import iter_expanded_rows


# --------------------------------------------------
# Snakemake paths
# --------------------------------------------------
planner_csv = snakemake.input.planner
config_yaml = snakemake.input.yaml
output_csv = snakemake.output.expanded_runs


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

# --------------------------------------------------
# Load config and expand rows via shared helpers
# --------------------------------------------------
with open(config_yaml, encoding="utf-8") as config_file:
    config = yaml.safe_load(config_file)

expanded = list(iter_expanded_rows(config, Path(planner_csv)))

# --------------------------------------------------
# Write expanded table
# --------------------------------------------------
out = pd.DataFrame(expanded)

csv_text = out.to_csv(index=False)
write_text_if_changed(Path(output_csv), csv_text)

print(out.head())
print(f"\nTOTAL RUNS: {len(out)}")