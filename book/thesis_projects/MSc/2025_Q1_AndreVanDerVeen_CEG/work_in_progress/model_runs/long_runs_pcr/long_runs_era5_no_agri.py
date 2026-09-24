# setup imports
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
import sys
from pathlib import Path

PROJECT_ROOT = Path().resolve().parents[1]  # pas aan als notebook dieper/dichter zit
sys.path.append(str(PROJECT_ROOT))

import ewatercycle.forcing
import ewatercycle.models
import ewatercycle.parameter_sets
from ewatercycle.container import ContainerImage

from src.models import simulate_PCRGLOBWB_experiment
from src.paths import *




prepared_PCRGlob_forcing = (
    FORCING_PCRGLOB / "ERA5_1940-2020" / "AralSea_basin" / "work/diagnostic/script"
)

forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
    directory=prepared_PCRGlob_forcing,
)





experiment_start_date_1 = "1940-01-01T00:00:00Z"
experiment_end_date_1 = "1970-12-31T00:00:00Z"

experiment_start_date_2 = "1965-01-01T00:00:00Z"
experiment_end_date_2 = "1995-12-31T00:00:00Z"

experiment_start_date_3 = "1990-01-01T00:00:00Z"
experiment_end_date_3 = "2020-12-31T00:00:00Z"



experiments = [
    (experiment_start_date_1, experiment_end_date_1),
    (experiment_start_date_2, experiment_end_date_2),
    (experiment_start_date_3, experiment_end_date_3),
]

BASE_OUTPUT_DIR = Path(__file__).resolve().parent / "era5_parallel_runs_no_agri"
BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def _run_experiment(experiment):
    experiment_start_date, experiment_end_date = experiment
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
                "calibrated_best_no_agri.ini",
                experiment_start_date,
                experiment_end_date,
                run_output_dir,
            )
        log_stream.write(f"Finished {run_name}\n")


def main():
    with ProcessPoolExecutor(max_workers=len(experiments)) as executor:
        futures = [executor.submit(_run_experiment, experiment) for experiment in experiments]
        for future in as_completed(futures):
            future.result()


if __name__ == "__main__":
    main()

