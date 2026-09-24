"""Climate forcing data generation and processing.

This module handles the preparation of meteorological forcing data for
hydrological models within the eWaterCycle framework. It supports:
- ERA5 reanalysis (observations)
- CMIP6 historical and future scenarios
- Both lumped (catchment-average) and gridded formats
- Bias correction and regridding
"""

from pathlib import Path

import ewatercycle.forcing
import matplotlib.pyplot as plt
import xarray as xr
import xesmf as xe
from tempfile import NamedTemporaryFile
import os
import numpy as np
import cftime

from .constants import DEFAULT_CMIP6_MODELS
from .paths import (
    FORCING_CMIP_FUT,
    FORCING_CMIP_HIST,
    FORCING_ERA5,
    FORCING_OUTPUT,
    FORCING_PCRGLOB,
    SHAPEFILES,
)
from .utils import get_integer_multiple_bounds

# ===========================================================================
# FORCING GENERATION (LUMPED)
# - Generate lumped forcing for use in HBV, Leaky Bucket, etc.
# - Variables included:
#     * temperature
#     * precipitation
#     * incoming_shortwave_radiation
#     * potential_evaporation
# - Sources included:
#     * ERA5 (observations / reference)
#     * CMIP historical
#     * CMIP future (SSP scenarios)
# ===========================================================================


# def normalize_noleap_calendar(ds: xr.Dataset) -> xr.Dataset:
#     """Remove leap days and normalize the time axis to a 365-day calendar."""
#     if "time" not in ds.coords:
#         return ds

#     ds = ds.sel(time=~((ds.time.dt.month == 2) & (ds.time.dt.day == 29)))
#     if getattr(ds.time.dt, "calendar", None) != "365_day":
#         ds = ds.convert_calendar("365_day", align_on="date")

#     time_encoding = dict(ds.time.encoding)
#     time_encoding["calendar"] = "365_day"
#     ds["time"].encoding = time_encoding
#     return ds

# def normalize_noleap_calendar(ds: xr.Dataset) -> xr.Dataset:
#     """
#     For 365_day datasets: drop any Feb 29 dates and rebuild the time axis
#     using cftime.DatetimeNoLeap objects so offsets are consistent with the
#     calendar attribute. No-op for all other calendars.
#     """
#     if "time" not in ds.coords:
#         return ds
#     calendar = getattr(ds.time.dt, "calendar", None)

#     print(f"DEBUG normalize_noleap_calendar: calendar={calendar}, time dtype={ds.time.dtype}")
#     if calendar not in ("365_day", "noleap"):
#         return ds
#     # Drop Feb 29 dates if any slipped through
#     ds = ds.sel(time=~((ds.time.dt.month == 2) & (ds.time.dt.day == 29)))

#     # Rebuild time axis as proper DatetimeNoLeap objects from scratch
#     new_times = np.array([
#         cftime.DatetimeNoLeap(int(t.dt.year), int(t.dt.month), int(t.dt.day))
#         for t in ds.time
#     ])
#     ds = ds.assign_coords(time=new_times)

#     ds["time"].encoding = {
#         "calendar": "365_day",
#         "units": "days since 1850-01-01",
#         "dtype": "float64",
#     }
#     return ds

def normalize_noleap_calendar(ds: xr.Dataset) -> xr.Dataset:
    """
    Convert 365_day/noleap calendar to standard Gregorian.
    Feb 29 values in data variables are forward-filled from Feb 28.
    """
    if "time" not in ds.coords:
        return ds

    calendar = getattr(ds.time.dt, "calendar", None)
    if calendar not in ("365_day", "noleap"):
        return ds

    # Convert to standard calendar - Feb 29s become NaN
    ds = ds.convert_calendar("standard", align_on="date", missing=float("nan"))

    # Forward-fill only numeric data variables (tas, pr, etc), not bounds
    for var in ds.data_vars:
        if ds[var].dtype.kind in ('f', 'i'):  # float or int types only
            if "time" in ds[var].dims:
                ds[var] = ds[var].ffill(dim='time')

    ds["time"].encoding = {
        "calendar": "standard",
        "units": "days since 1850-01-01",
        "dtype": "float64",
    }
    return ds


def _resolve_shapefile(shape_name: str | None = None, shapefile: Path | None = None) -> tuple[Path, str]:
    if shape_name is not None and shapefile is not None:
        raise ValueError("Provide either shape_name or shapefile, not both")
    if shape_name is None and shapefile is None:
        raise ValueError("Either shape_name or shapefile must be provided")

    if shapefile is not None:
        resolved_shapefile = Path(shapefile)
        if not resolved_shapefile.exists():
            raise FileNotFoundError(f"Shapefile not found: {resolved_shapefile}")
        return resolved_shapefile, resolved_shapefile.stem

    resolved_shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"
    if not resolved_shapefile.exists():
        raise FileNotFoundError(f"Shapefile not found: {resolved_shapefile}")
    return resolved_shapefile, shape_name


def generate_lumped_ERA5_forcing(
    start: str,
    end: str,
    shape_name: str | None = None,
    shapefile: Path | None = None,
    output_root: Path | None = None,
    output_name: str | None = None,
):
    """Generate ERA5 forcing data for a lumped basin defined by a shapefile.

    Parameters
    ----------
    start : str
        Start date in ISO format (YYYY-MM-DD or full ISO timestamp).
    end : str
        End date in ISO format (YYYY-MM-DD or full ISO timestamp).
    shape_name : str, optional
        Name of the shapefile folder and file stem.
    shapefile : Path, optional
        Explicit path to the shapefile.
    output_root : Path, optional
        Root directory for forcing output. Defaults to FORCING_ERA5.
    output_name : str, optional
        Name of the output subfolder. Defaults to the shapefile stem.

    Returns:
    -------
    ewatercycle.forcing.Forcing
        ERA5-based forcing object written to NetCDF files on disk.
    """
    shapefile_path, base_name = _resolve_shapefile(shape_name=shape_name, shapefile=shapefile)

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    output_base = Path(output_root) if output_root is not None else FORCING_ERA5
    folder_name = output_name if output_name is not None else base_name
    forcing_dir = output_base / folder_name / year_span
    forcing_dir.mkdir(parents=True, exist_ok=True)

    # Generate forcing using eWaterCycle
    forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"].generate(
        dataset="ERA5", start_time=start, end_time=end, shape=shapefile_path, directory=forcing_dir
    )

    return forcing


def generate_lumped_CMIP_historical_forcing(
    start: str,
    end: str,
    model: str = DEFAULT_CMIP6_MODELS["historical"],
    shape_name: str | None = None,
    shapefile: Path | None = None,
    output_root: Path | None = None,
    output_name: str | None = None,
):
    """Generate CMIP6 historical forcing data for a lumped basin.

    Parameters
    ----------
    start : str
        Start date in ISO format.
    end : str
        End date in ISO format.
    model : str, optional
        CMIP6 climate model name, by default "MPI-ESM1-2-HR".
    shape_name : str, optional
        Name of the shapefile folder and file stem.
    shapefile : Path, optional
        Explicit path to the shapefile.
    output_root : Path, optional
        Root directory for forcing output. Defaults to FORCING_CMIP_HIST.
    output_name : str, optional
        Name of the output subfolder. Defaults to the shapefile stem.

    Returns:
    -------
    ewatercycle.forcing.Forcing
        CMIP6 historical forcing object written to NetCDF files on disk.
    """
    shapefile_path, base_name = _resolve_shapefile(shape_name=shape_name, shapefile=shapefile)

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    output_base = Path(output_root) if output_root is not None else FORCING_CMIP_HIST
    folder_name = output_name if output_name is not None else base_name
    forcing_dir = output_base / folder_name / year_span
    forcing_dir.mkdir(parents=True, exist_ok=True)

    cmip_historical = {
        "project": "CMIP6",
        "exp": "historical",
        "dataset": model,
        "ensemble": "r1i1p1f1",
        "grid": "gn",
    }

    CMIP_forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"].generate(
        dataset=cmip_historical,
        start_time=start,
        end_time=end,
        shape=shapefile_path,
        directory=forcing_dir,
    )

    return CMIP_forcing


def generate_lumped_CMIP_future_forcing(
    start: str,
    end: str,
    ssp: str = "ssp245",
    model: str = DEFAULT_CMIP6_MODELS["future"],
    shape_name: str | None = None,
    shapefile: Path | None = None,
    output_root: Path | None = None,
    output_name: str | None = None,
):
    """Generate CMIP6 future scenario forcing data for a lumped basin.

    Parameters
    ----------
    start : str
        Start date in ISO format.
    end : str
        End date in ISO format.
    ssp : str
        Scenario name (e.g., "ssp126", "ssp245", "ssp585").
    model : str, optional
        CMIP6 climate model name, by default "EC-Earth3".
    shape_name : str, optional
        Name of the shapefile folder and file stem.
    shapefile : Path, optional
        Explicit path to the shapefile.
    output_root : Path, optional
        Root directory for forcing output. Defaults to FORCING_CMIP_FUT.
    output_name : str, optional
        Name of the output subfolder. Defaults to the shapefile stem.

    Returns:
    -------
    ewatercycle.forcing.Forcing
        CMIP6 future forcing object written to NetCDF files on disk.
    """
    shapefile_path, base_name = _resolve_shapefile(shape_name=shape_name, shapefile=shapefile)

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    output_base = Path(output_root) if output_root is not None else FORCING_CMIP_FUT
    folder_name = output_name if output_name is not None else base_name
    forcing_dir = output_base / model / ssp / folder_name / year_span

    forcing_dir.mkdir(parents=True, exist_ok=True)

    cmip_dataset = {
        "project": "CMIP6",
        "activity": "ScenarioMIP",
        "exp": ssp,
        "mip": "day",
        "dataset": model,
        "ensemble": "r1i1p1f1",
        "grid": "*",
    }

    CMIP_forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"].generate(
        dataset=cmip_dataset,
        start_time=start,
        end_time=end,
        shape=shapefile_path,
        directory=forcing_dir,
    )

    return CMIP_forcing


def load_lumped_forcing_data(
    shape_name: str, forcing_type: str, year_span: str, base_forcing_dir=None
):
    """Load previously generated lumped forcing data for a given shapefile.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile / catchment (lowercase, consistent with folder names)
    forcing_type : str
        Forcing type, e.g., "ERA5", "CMIP_HIST"
    base_forcing_dir : pathlib.Path, optional
        Base directory where forcing outputs are stored.
        If None, defaults to FORCING_OUTPUT from paths.py

    Returns:
    -------
    ewatercycle.forcing.Forcing
        Loaded forcing object
    """
    # Use default forcing output folder if none provided
    if base_forcing_dir is None:
        base_forcing_dir = FORCING_OUTPUT

    # Construct the load path
    load_location = (
        base_forcing_dir
        / f"{forcing_type}"
        / f"{shape_name}"
        / year_span
        / "work"
        / "diagnostic"
        / "script"
    )

    # Load the forcing
    forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"].load(directory=load_location)

    return forcing


def _ensure_dataset(obj):
    """Ensure the object is an xarray.Dataset.

    Parameters
    ----------
    obj : xarray.Dataset or str / Path
        If a path, the dataset will be opened using xr.open_dataset.

    Returns:
    -------
    xr.Dataset
        Dataset object.
    """
    if isinstance(obj, xr.Dataset):
        return obj
    return xr.open_dataset(obj)


def plot_lumped_ERA5_forcing(forcing_obj, shape_name: str = None):
    """Plot precipitation, temperature, shortwave radiation, and potential evaporation
    from a loaded ERA5 forcing object.

    Parameters
    ----------
    forcing_obj : dict or ewatercycle.forcing.Forcing
        Forcing object containing 'pr', 'tas', 'rsds', 'evspsblpot'.
    shape_name : str, optional
        Name of the catchment/shapefile, added to title if provided.
    """
    ERA5_data = {
        "precipitation pr": _ensure_dataset(forcing_obj["pr"]),
        "temperature tas": _ensure_dataset(forcing_obj["tas"]),
        "incoming_shortwave_radiation rsds": _ensure_dataset(forcing_obj["rsds"]),
        "potential_evaporation evspsblpot": _ensure_dataset(forcing_obj["evspsblpot"]),
    }

    plt.figure(figsize=(15, 10))
    for i, (name, data) in enumerate(ERA5_data.items(), 1):
        plt.subplot(2, 2, i)
        variable_name = name.split(" ")[-1]
        title_name = name.split(" ")[0]
        data[variable_name].plot()
        plt.title(f"{title_name}")
        plt.grid(linestyle="--", alpha=0.5)

    if shape_name:
        plt.suptitle(f"ERA5 LumpedMakkink Forcing Data \n (shapefile = {shape_name})", fontsize=20)
    else:
        plt.suptitle("ERA5 LumpedMakkink Forcing Data", fontsize=20)
    plt.tight_layout()
    plt.show()


# NOT WORKING FOR NOW, HBV ONLY ACCEPTS REAL EWATERCYCLE FORCING
def create_forcing_slice(forcing_obj, start, end):
    """Temporarily slice ERA5 forcing data in memory.
    To use in HBV (and Leakybucket?)

    NOT WORKING FOR NOW, HBV ONLY ACCEPTS REAL EWATERCYCLE FORCING

    Parameters
    ----------
    forcing_obj : dict-like
        Must contain paths for 'pr', 'tas', 'rsds', 'evspsblpot'
    start, end : str
        Time slice, e.g. "1990-01-01", "2014-12-31"

    Returns:
    -------
    dict[str, xarray.Dataset]
        Sliced datasets (not written to disk)
    """
    # NOT WORKING FOR NOW, HBV ONLY ACCEPTS REAL EWATERCYCLE FORCING
    sliced = {}

    for var in ["pr", "tas", "rsds", "evspsblpot"]:
        ds = xr.open_dataset(forcing_obj[var])
        sliced[var] = ds.sel(time=slice(start, end))

    return sliced


# ===========================================================================
# FORCING GENERATION (PCR-GLOBWB)
# - Generate combined PCR-GLOBWB forcing
# - Variables included:
#     * temperature
#     * precipitation
# - Includes:
#     * ERA5 (observations / reference)
#     * CMIP historical
#     * CMIP future (SSP scenarios)
# ===========================================================================


def generate_PCRGLOBWB_ERA5_forcing( 
        start: str, 
        end: str,
        shapefile: Path | None = None,
        shape_name: str | None = None,
        output_name: str | None = None,
        forcing_root: Path | None = None,
    ) -> "ewatercycle.forcing.Forcing":
    """Generate ERA5 forcing data for PCR-GLOBWB model.

    Parameters
    ----------
    start : str
        Start date in ISO format, e.g., "1940-01-01T00:00:00Z"
    end : str
        End date in ISO format, e.g., "2020-12-31T00:00:00Z"
    shapefile : Path, optional
        Explicit path to the shapefile.
        Mutually exclusive with shape_name.
    shape_name : str, optional
        Name of the shapefile (must match folder and file name in SHAPEFILES dir).
        Mutually exclusive with shapefile. Remains for backwards compatibility.
    output_name : str, optional
        Name for the output folder. Defaults to shape_name or shapefile stem.
    forcing_root : Path, optional
        Root directory for forcing output. Defaults to FORCING_PCRGLOB from paths.py.

    Returns
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object.

    Raises
    ------
    ValueError
        If both or neither of shape_name and shapefile are provided.
    """
    if shape_name is not None and shapefile is not None:
        raise ValueError("Provide either shape_name or shapefile, not both")
    if shape_name is None and shapefile is None:
        raise ValueError("Either shape_name or shapefile must be provided")
    
    # resolve shp and base name
    if shapefile is not None:
        shp = Path(shapefile)
        base_name = shp.stem
    else:
        shp = SHAPEFILES / shape_name / f"{shape_name}.shp"
        base_name = shape_name


    # output_name overrides base_name if provided
    if output_name is not None:
        folder_name = output_name
    else:
        folder_name = base_name

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    root = Path(forcing_root) if forcing_root is not None else FORCING_PCRGLOB
    forcing_dir = root / year_span / folder_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefiles = shp,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset="ERA5",
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shp,
        extract_region={
            "start_longitude": lon_min_f - esmvaltool_padding,
            "end_longitude": lon_max_f + esmvaltool_padding,
            "start_latitude": lat_min_f - esmvaltool_padding,
            "end_latitude": lat_max_f + esmvaltool_padding,
        },
        directory=forcing_dir,
    )

    return pcrglobwb_forcing


def generate_PCRGLOBWB_CMIP_historical_forcing(
    start: str,
    end: str,
    model: str = DEFAULT_CMIP6_MODELS["historical"],
    ensemble: str = "r1i1p1f1",
    forcing_root: Path | None = None,
    shape_name: str | None = None,
    shapefile: Path | None = None,
    ) -> "ewatercycle.forcing.Forcing":
    """Generate CMIP6 historical forcing data for PCR-GLOBWB model.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile (must match folder and file name in SHAPEFILES dir).
    start : str
        Start date in ISO format, e.g., "1940-01-01T00:00:00Z"
    end : str
        End date in ISO format, e.g., "2014-12-31T00:00:00Z"
    model : str, optional
        CMIP6 model name. Defaults to DEFAULT_CMIP6_MODELS["historical"].
    ensemble : str, optional
        Ensemble member identifier. Defaults to "r1i1p1f1".
    forcing_root : Path, optional
        Root directory for forcing output. Defaults to FORCING_PCRGLOB from paths.py.

    Returns
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object.
    """
    # Path to the shapefile
    # Path to the shapefile
    if shape_name is not None and shapefile is not None:
        raise ValueError("Provide either shape_name or shapefile, not both")
    if shape_name is None and shapefile is None:
        raise ValueError("Either shape_name or shapefile must be provided")

    if shapefile is not None:
        shp = Path(shapefile)
        shape_name = shp.stem
    else:
        shp = SHAPEFILES / shape_name / f"{shape_name}.shp"

    cmip_historical = {
        "project": "CMIP6",
        "exp": "historical",
        "dataset": model,
        "ensemble": ensemble,
        "grid": "gn",
    }

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # make output directory
    root = Path(forcing_root) if forcing_root is not None else FORCING_PCRGLOB
    forcing_dir = root / model / ensemble / year_span / shape_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefiles = shp,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset=cmip_historical,
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shp,
        extract_region={
            "start_longitude": lon_min_f - esmvaltool_padding,
            "end_longitude": lon_max_f + esmvaltool_padding,
            "start_latitude": lat_min_f - esmvaltool_padding,
            "end_latitude": lat_max_f + esmvaltool_padding,
        },
        directory=forcing_dir,
    )

    return pcrglobwb_forcing


def generate_PCRGLOBWB_CMIP_future_forcing(
    start: str,
    end: str,
    ssp: str,
    model: str = DEFAULT_CMIP6_MODELS["future"],
    ensemble: str = "r1i1p1f1",
    forcing_root: Path | None = None,
    shape_name: str | None = None,
    shapefile: Path | None = None,
) -> "ewatercycle.forcing.Forcing":
    
    """Setup and generate forcing data for a given shapefile.
    To be used with PCR-GLOBWB model.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile (should match folder and shapefile name)
    start : str
        Start date in ISO format, e.g., "1950-01-01T00:00:00Z"
    end : str
        End date in ISO format, e.g., "2020-12-31T00:00:00Z"

    Returns
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object.
    """
    # Path to the shapefile
    if shape_name is not None and shapefile is not None:
        raise ValueError("Provide either shape_name or shapefile, not both")
    if shape_name is None and shapefile is None:
        raise ValueError("Either shape_name or shapefile must be provided")

    if shapefile is not None:
        shp = Path(shapefile)
        shape_name = shp.stem
    else:
        shp = SHAPEFILES / shape_name / f"{shape_name}.shp"

    cmip_dataset = {
        "project": "CMIP6",
        "activity": "ScenarioMIP",
        "exp": ssp,
        "mip": "day",
        "dataset": model,
        "ensemble": ensemble,
        "grid": "*",
    }

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    root = Path(forcing_root) if forcing_root is not None else FORCING_PCRGLOB
    forcing_dir = root / model / ssp / ensemble / year_span / shape_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefiles = shp,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset=cmip_dataset,
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shp,
        extract_region={
            "start_longitude": lon_min_f - esmvaltool_padding,
            "end_longitude": lon_max_f + esmvaltool_padding,
            "start_latitude": lat_min_f - esmvaltool_padding,
            "end_latitude": lat_max_f + esmvaltool_padding,
        },
        directory=forcing_dir,
    )

    return pcrglobwb_forcing


# ===========================================================================
# REGRIDDING
# - Regrid CMIP forcing to ERA5 grid
# - Applies to precipitation and temperature variables
# - Overwrites original CMIP files
# ===========================================================================


def regrid_pcrglobwb_forcing(cmip_forcing, era5_forcing):
    """Regrid CMIP PCR-GLOBWB forcing to match ERA5 grid.

    Parameters
    ----------
    cmip_forcing : PCRGlobWBForcing
        CMIP forcing object with NetCDF files.
    era5_forcing : PCRGlobWBForcing
        ERA5 forcing object providing the target grid.

    Returns:
    -------
    None
        NetCDF files in cmip_forcing.directory are overwritten.

    Notes:
    -----
    - Original CMIP files are modified. Backup recommended.
    - Applies variable-aware regridding to precipitation and temperature.
    """
    _regrid_cmip_forcing_to_era5(
        cmip_path=cmip_forcing.directory / cmip_forcing.precipitationNC,
        era5_path=era5_forcing.directory / era5_forcing.precipitationNC,
    )
    _regrid_cmip_forcing_to_era5(
        cmip_path=cmip_forcing.directory / cmip_forcing.temperatureNC,
        era5_path=era5_forcing.directory / era5_forcing.temperatureNC,
    )


def _regrid_cmip_forcing_to_era5(
    cmip_path,
    era5_path,
    overwrite=True,
):
    """Internal Helper, Regrid CMIP forcing exactly onto ERA5 grid.

    Parameters
    ----------
    cmip_path : Path or str
        CMIP forcing NetCDF file (source grid).
    era5_path : Path or str
        ERA5 forcing NetCDF file (target grid).
    overwrite : bool
        Overwrite CMIP file after regridding.

    Returns:
    -------
    xr.Dataset
        Regridded dataset.
    """
    cmip_path = Path(cmip_path)
    era5_path = Path(era5_path)

    ds_cmip = xr.load_dataset(cmip_path, use_cftime=True)
    ds_era5 = xr.load_dataset(era5_path)

    # Remove Feb 29 dates from CMIP data to match noleap calendar requirement.
    ds_cmip = normalize_noleap_calendar(ds_cmip)

    # Basic grid sanity check
    for dim in ("lat", "lon"):
        if dim not in ds_cmip.dims or dim not in ds_era5.dims:
            raise ValueError(f"Missing '{dim}' dimension for regridding")

    # Detect variable type
    forcing_type = detect_forcing_variable(ds_cmip)

    # Choose regridding method
    if forcing_type == "precipitation" or forcing_type == "temperature":
        method = "bilinear"
        extrap_method = "nearest_s2d"
    else:
        raise RuntimeError("Unhandled forcing type")

    # Create regridder
    regridder = xe.Regridder(
        ds_cmip,
        ds_era5,
        method=method,
        extrap_method=extrap_method,
        # reuse_weights=True,
    )

    # Apply regridding
    ds_out = regridder(ds_cmip)

    #ds_out = normalize_noleap_calendar(ds_out)

    # Preserve metadata
    ds_out.attrs.update(ds_cmip.attrs)
    ds_out.attrs["regridded_to"] = "ERA5"
    ds_out.attrs["regridding_method"] = method

    if overwrite:
        ds_out.to_netcdf(cmip_path)

    return ds_out


def detect_forcing_variable(ds):
    """Detect forcing variable type from dataset.

    Returns:
    -------
    str
        One of: 'precipitation', 'temperature'
    """
    varnames = set(ds.data_vars)

    precip_vars = {"pr", "precipitation", "tp"}
    temp_vars = {"tas", "t2m", "temperature"}

    if varnames & precip_vars:
        return "precipitation"
    if varnames & temp_vars:
        return "temperature"

    raise ValueError(f"Could not detect forcing variable from variables: {varnames}")


# ===========================================================================
# Bias correction forcing
# - Apply monthly bias factors to precipitation and temperature
# - Uses ERA5 as reference
# ===========================================================================

def bias_map_pcrglobwb_forcing(
    reference_forcing,
    baseline_forcing,
    target_forcing,
    method: str = "quantile_delta_mapping",
    n_quantiles: int = 1000,
    overwrite: bool = True,
    spatial_chunk_size: int = 16,
) -> None:
    """Bias-correct PCR-GLOBWB forcing using a reference dataset.

    Parameters
    ----------
    reference_forcing : PCRGlobWBForcing
        Observational reference forcing (e.g. ERA5).
    baseline_forcing : PCRGlobWBForcing
        CMIP historical forcing used as model baseline.
    target_forcing : PCRGlobWBForcing
        Forcing to be bias-corrected (future or historical). Files overwritten in place.
    method : str
        Bias-correction method from cmethods. Default is quantile_delta_mapping.
    n_quantiles : int
        Number of quantiles for quantile-based methods.
    overwrite : bool
        Overwrite target files after correction.
    spatial_chunk_size : int
        Chunk size for lat/lon dimensions during correction.

    Returns
    -------
    None
        NetCDF files in target_forcing.directory are overwritten.
    """
    _bias_map_cmip_future_with_era5(
        obs_path  = reference_forcing.directory / reference_forcing.precipitationNC,
        simh_path = baseline_forcing.directory / baseline_forcing.precipitationNC,
        simp_path = target_forcing.directory / target_forcing.precipitationNC,
        method    = method,
        n_quantiles = n_quantiles,
        kind      = "*",
        overwrite = overwrite,
        spatial_chunk_size = spatial_chunk_size,
    )
    _bias_map_cmip_future_with_era5(
        obs_path  = reference_forcing.directory / reference_forcing.temperatureNC,
        simh_path = baseline_forcing.directory / baseline_forcing.temperatureNC,
        simp_path = target_forcing.directory / target_forcing.temperatureNC,
        method    = method,
        n_quantiles = n_quantiles,
        kind      = "+",
        overwrite = overwrite,
        spatial_chunk_size = spatial_chunk_size,
    )


def _pick_variable_name(ds, preferred_names):
    """Pick the first matching variable name, or fall back to the first variable."""
    for name in preferred_names:
        if name in ds.data_vars:
            return name
    return list(ds.data_vars)[0]


def _bias_correction_data_summary(da):
    """Return a compact summary for bias-correction diagnostics."""
    return f"dims={dict(da.sizes)}, size={da.size}"


def _assert_writable_target(path):
    """Fail fast when output location is not writable."""
    path = Path(path)
    parent = path.parent

    if not parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {parent}")

    # Directory write+execute is required to create temporary files.
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        raise PermissionError(f"No write permission in output directory: {parent}")

    # If target already exists, we also need permission to replace it.
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"No write permission for output file: {path}")

    # Try creating and removing a tiny probe file in the output directory.
    probe = None
    try:
        with NamedTemporaryFile(dir=parent, prefix=".write_check_", delete=False) as tmp:
            probe = Path(tmp.name)
    except PermissionError as exc:
        raise PermissionError(f"Cannot create files in output directory: {parent}") from exc
    finally:
        if probe and probe.exists():
            probe.unlink(missing_ok=True)


def _bias_map_cmip_future_with_era5(
    obs_path,
    simh_path,
    simp_path,
    method,
    n_quantiles,
    kind,
    overwrite=True,
    spatial_chunk_size=16,
):
    """Internal helper to bias-correct one forcing variable (pr or tas)."""
    try:
        from cmethods import adjust
    except ImportError as exc:
        raise ImportError(
            "Bias mapping requires cmethods. Install it with: pip install cmethods"
        ) from exc

    obs_path = Path(obs_path)
    simh_path = Path(simh_path)
    simp_path = Path(simp_path)

    for p in (obs_path, simh_path, simp_path):
        if not p.exists():
            raise FileNotFoundError(f"Bias mapping input does not exist: {p}")
        if p.stat().st_size == 0:
            raise ValueError(f"Bias mapping input is empty: {p}")

    if overwrite:
        _assert_writable_target(simp_path)

    obs_ds = xr.open_dataset(obs_path, chunks={"time": 365})
    simh_ds = xr.open_dataset(simh_path, chunks={"time": 365})
    simp_ds = xr.open_dataset(simp_path, chunks={"time": 365})

    forcing_type = detect_forcing_variable(simh_ds)
    if forcing_type == "precipitation":
        candidates = ("pr", "precipitation", "tp")
    elif forcing_type == "temperature":
        candidates = ("tas", "t2m", "temperature")
    else:
        raise RuntimeError("Unhandled forcing type")

    obs_var = _pick_variable_name(obs_ds, candidates)
    simh_var = _pick_variable_name(simh_ds, candidates)
    simp_var = _pick_variable_name(simp_ds, candidates)

    obs = obs_ds[obs_var]
    simh = simh_ds[simh_var]
    simp = simp_ds[simp_var]

    # Preserve key output encoding from the original future variable.
    simp_var_encoding = {}
    for key in (
        "dtype",
        "_FillValue",
        "scale_factor",
        "add_offset",
        "zlib",
        "complevel",
        "shuffle",
        "fletcher32",
        "contiguous",
        "chunksizes",
    ):
        value = simp.encoding.get(key)
        if value is not None:
            simp_var_encoding[key] = value

    target_dtype = simp_var_encoding.get("dtype", simp.dtype)



    # # cmethods expects matching non-time coordinates.
    # if "lat" in simh.dims and "lon" in simh.dims:
    #     obs = obs.interp(lat=simh["lat"], lon=simh["lon"], method="linear")
    #     simp = simp.interp(lat=simh["lat"], lon=simh["lon"], method="linear")

    # Assert grids are already aligned after upstream regridding, no more silent interpolation here.
    assert obs.dims == simh.dims, f"Dimension mismatch: obs={obs.dims}, simh={simh.dims}"
    np.testing.assert_allclose(obs["lat"].values, simh["lat"].values, rtol=1e-5,
        err_msg="lat coordinates do not match between obs and simh")
    np.testing.assert_allclose(obs["lon"].values, simh["lon"].values, rtol=1e-5,
        err_msg="lon coordinates do not match between obs and simh")

    model_calendar = simh.time.dt.calendar
    obs_calendar = obs.time.dt.calendar
    if obs_calendar != model_calendar:
        obs = obs.convert_calendar(model_calendar, align_on="date")

    obs, simh = xr.align(obs, simh, join="inner")

    # cmethods fails with a cryptic zero-size reduction error when one of the
    # aligned inputs has no valid data left. Catch that early with context.
    for name, da in (("obs", obs), ("simh", simh), ("simp", simp)):
        if da.size == 0:
            raise ValueError(
                f"Bias correction input {name} is empty after alignment/regridding: "
                f"{_bias_correction_data_summary(da)}"
            )
        if bool(da.isnull().all().compute().item()):
            raise ValueError(
                f"Bias correction input {name} contains only missing values after "
                f"alignment/regridding: {_bias_correction_data_summary(da)}"
            )

    # cmethods runs apply_ufunc with time as a core dimension.
    qdm_chunks = {"time": -1}
    if "lat" in simh.dims:
        qdm_chunks["lat"] = spatial_chunk_size
    if "lon" in simh.dims:
        qdm_chunks["lon"] = spatial_chunk_size

    obs_qdm = obs.chunk(qdm_chunks)
    simh_qdm = simh.chunk(qdm_chunks)
    simp_qdm = simp.chunk(qdm_chunks)

    corrected = adjust(
        method=method,
        obs=obs_qdm,
        simh=simh_qdm,
        simp=simp_qdm,
        n_quantiles=n_quantiles,
        kind=kind,
    )

    if isinstance(corrected, xr.Dataset):
        corr_var = list(corrected.data_vars)[0]
        corrected_da = corrected[corr_var].rename(simp_var)
    else:
        corrected_da = corrected.rename(simp_var)

    corrected_da = corrected_da.astype(target_dtype)
    corrected_da.attrs.update(simp.attrs)

    ds_out = simp_ds.copy()
    ds_out[simp_var] = corrected_da
    ds_out.attrs.update(simp_ds.attrs)
    ds_out.attrs["bias_corrected_with"] = "ERA5"
    ds_out.attrs["bias_correction_method"] = method
    ds_out.attrs["bias_correction_kind"] = kind

    if overwrite:
        with NamedTemporaryFile(dir=simp_path.parent, suffix=".tmp", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        try:
            ds_out.to_netcdf(tmp_path, encoding={simp_var: simp_var_encoding})
            tmp_path.replace(simp_path)
        finally:
            if tmp_path.exists() and tmp_path != simp_path:
                tmp_path.unlink(missing_ok=True)

    return ds_out


# ---------------------------
# Backward compatibility
setup_ERA5_forcing = generate_lumped_ERA5_forcing
setup_CMIP_historical_forcing = generate_lumped_CMIP_historical_forcing
setup_CMIP_future_forcing = generate_lumped_CMIP_future_forcing
setup_ERA5_PCR_forcing = generate_PCRGLOBWB_ERA5_forcing
setup_cmip_hist_PCR_forcing = generate_PCRGLOBWB_CMIP_historical_forcing
setup_cmip_fut_PCR_forcing = generate_PCRGLOBWB_CMIP_future_forcing
