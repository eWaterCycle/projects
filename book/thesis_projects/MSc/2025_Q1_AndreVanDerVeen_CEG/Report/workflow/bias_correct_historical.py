# workflow/bias_correct_historical.py
import logging
import shutil
import sys
from pathlib import Path

log_file = snakemake.log[0] # type: ignore
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

dst = None

try:
    import ewatercycle.forcing
    from src.forcing import bias_map_pcrglobwb_forcing

    TAIL = Path(snakemake.config["forcing"]["ewatercycle_tail"])  # type: ignore

    # copy regridded to bias_corrected
    src = Path(snakemake.input.historical_flag).parent  # type: ignore
    dst = Path(snakemake.output.flag).parent  # type: ignore
    logging.info(f"Copying from {src} to {dst}")
    shutil.copytree(src, dst, dirs_exist_ok=True)

    # load forcing objects
    logging.info("Loading forcing objects...")
    target    = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(directory = dst / TAIL)
    baseline  = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(directory = Path(snakemake.input.historical_flag).parent / TAIL) # type: ignore
    reference = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(directory = Path(snakemake.input.era5_flag).parent / TAIL) # type: ignore

    logging.info("Starting bias correction...")
    bias_map_pcrglobwb_forcing(
        reference_forcing  = reference,
        baseline_forcing   = baseline,
        target_forcing     = target,
        method             = "quantile_delta_mapping",
        n_quantiles        = 200,
        overwrite          = True,
        spatial_chunk_size = 32,
    )

    logging.info("Bias correction finished, creating flag file.")
    Path(snakemake.output.flag).touch()  # type: ignore

except Exception as e:
    logging.error("Script failed with an exception.")
    logging.exception(e)
    # Clean up partially created files
    if dst is not None:
        logging.info(f"Cleaning up {dst}")
        shutil.rmtree(dst, ignore_errors=True)
    raise