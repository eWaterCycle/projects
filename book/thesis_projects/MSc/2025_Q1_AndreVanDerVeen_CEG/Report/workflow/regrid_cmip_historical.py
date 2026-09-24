import shutil
import ewatercycle.forcing
from pathlib import Path
from src.forcing import regrid_pcrglobwb_forcing

TAIL = Path(snakemake.config["forcing"]["ewatercycle_tail"])  # type: ignore

src = Path(snakemake.input.cmip_flag).parent  # type: ignore
dst = Path(snakemake.output.flag).parent  # type: ignore

# copy raw to regridded FIRST
shutil.copytree(src, dst, dirs_exist_ok=True)

# then load and regrid
cmip = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
    directory = dst / TAIL
)
era5 = ewatercycle.forcing.sources["PCRGlobWBForcing"].load(
    directory = Path(snakemake.input.era5_flag).parent / TAIL  # type: ignore
)

regrid_pcrglobwb_forcing(cmip, era5)
Path(snakemake.output.flag).touch()  # type: ignore