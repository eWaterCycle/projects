from snakemake.script import Snakemake
snakemake: Snakemake
import ewatercycle.forcing
from src.models import simulate_PCRGLOBWB_experiment
from pathlib import Path
from ewatercycle.container import ContainerImage
from complete_pcrglob_run.long_runs_cmip_fut_245 import BASE_OUTPUT_DIR  # type: ignore


config = snakemake.params.config
TAIL = Path(snakemake.config["forcing"]["ewatercycle_tail"])


forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(directory = Path(snakemake.input.forcing_flag).parent / TAIL)



experiment_start_date = config["pcrglob"]["test_experiment"]["start_date"]
experiment_end_date = config["pcrglob"]["test_experiment"]["end_date"]

start_year = experiment_start_date[:4]
end_year = experiment_end_date[:4]

run_name = f"run_{start_year}_{end_year}"
run_output_dir = BASE_OUTPUT_DIR / run_name
run_output_dir.mkdir(parents=True, exist_ok=True)

log_file = run_output_dir / "tqdm.log"
with open(log_file, "a", encoding="utf-8") as log_stream:
    log_stream.write(
        f"Starting {run_name} ({experiment_start_date} -> {experiment_end_date})\n"
    )
    with redirect_stdout(log_stream), redirect_stderr(log_stream):
        simulate_PCRGLOBWB_experiment(
            prepared_PCRGlob_forcing,
            "calibration.ini",
            experiment_start_date,
            experiment_end_date,
            run_output_dir,
        )
    log_stream.write(f"Finished {run_name}\n")