from pathlib import Path
import yaml
import pandas as pd


config_path = Path(__file__).resolve().parents[2] / "config_aral.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# -----------------------------
# Load experiment CSV
# -----------------------------
csv_path = Path(__file__).resolve().parents[2]/ "config" / "experiment_planner.csv"

df = pd.read_csv(csv_path, sep=";")


time_blocks = config["time_blocks"]
groups = config["active_time_blocks"]

expanded = []

for _, row in df.iterrows():

    group = row["time_group"]   # era5 / cmip_hist / cmip_fut

    if group not in groups:
        raise ValueError(f"Unknown group: {group}")

    blocks = groups[group]

    for block in blocks:

        if block not in time_blocks:
            raise ValueError(f"Unknown block: {block}")

        tb = time_blocks[block]

        expanded.append({
            "run_id": row["run_id"],
            "group": group,
            "time_block": block,
            "start_date": tb["start_date"],
            "end_date": tb["end_date"],
            "model": row.get("model", ""),
            "scenario": row.get("scenario", ""),
            "parameter_set": row.get("parameter_set", ""),
        })

out = pd.DataFrame(expanded)
out.to_csv("expanded_runs.csv", index=False)

print(out.head())
print(f"TOTAL RUNS: {len(out)}")
