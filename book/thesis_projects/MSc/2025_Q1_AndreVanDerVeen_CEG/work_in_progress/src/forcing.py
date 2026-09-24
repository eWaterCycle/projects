"""Climate forcing data generation and processing.

This module handles the preparation of meteorological forcing data for
hydrological models within the eWaterCycle framework. It supports:
- ERA5 reanalysis (observations)
- CMIP6 historical and future scenarios
- Both lumped (catchment-average) and gridded formats
- Bias correction and regridding
"""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import ewatercycle.forcing
import matplotlib.pyplot as plt
import xarray as xr
import xesmf as xe

from src.constants import DEFAULT_CMIP6_MODELS
from src.paths import (
    FORCING_CMIP_FUT,
    FORCING_CMIP_HIST,
    FORCING_ERA5,
    FORCING_OUTPUT,
    FORCING_PCRGLOB,
    SHAPEFILES,
)
from src.utils import get_integer_multiple_bounds

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


def generate_lumped_ERA5_forcing(shape_name: str, start: str, end: str):
    """Generate ERA5 forcing data for a lumped basin defined by a shapefile.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile (folder and file should be the same: .../shape_name/shape_name.shp).
    start : str
        Start date in ISO format (YYYY-MM-DD or full ISO timestamp).
    end : str
        End date in ISO format (YYYY-MM-DD or full ISO timestamp).

    Returns:
    -------
    ewatercycle.forcing.Forcing
        ERA5-based forcing object written to NetCDF files on disk.
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    forcing_dir = FORCING_ERA5 / shape_name / year_span
    forcing_dir.mkdir(parents=True, exist_ok=True)

    # Generate forcing using eWaterCycle
    forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"].generate(
        dataset="ERA5", start_time=start, end_time=end, shape=shapefile, directory=forcing_dir
    )

    return forcing


def generate_lumped_CMIP_historical_forcing(
    shape_name: str, start: str, end: str, model: str = DEFAULT_CMIP6_MODELS["historical"]
):
    """Generate CMIP6 historical forcing data for a lumped basin.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile (folder and file stem).
    start : str
        Start date in ISO format.
    end : str
        End date in ISO format.
    model : str, optional
        CMIP6 climate model name, by default "MPI-ESM1-2-HR".

    Returns:
    -------
    ewatercycle.forcing.Forcing
        CMIP6 historical forcing object written to NetCDF files on disk.
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    forcing_dir = FORCING_CMIP_HIST / shape_name / year_span
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
        shape=shapefile,
        directory=forcing_dir,
    )

    return CMIP_forcing


def generate_lumped_CMIP_future_forcing(
    shape_name: str,
    start: str,
    end: str,
    ssp: str = "ssp245",
    model: str = DEFAULT_CMIP6_MODELS["future"],
):
    """Generate CMIP6 future scenario forcing data for a lumped basin.

    Parameters
    ----------
    shape_name : str
        Name of the shapefile (folder and file stem).
    start : str
        Start date in ISO format.
    end : str
        End date in ISO format.
    ssp : str
        Scenario name (e.g., "ssp126", "ssp245", "ssp585").
    model : str, optional
        CMIP6 climate model name, by default "EC-Earth3".

    Returns:
    -------
    ewatercycle.forcing.Forcing
        CMIP6 future forcing object written to NetCDF files on disk.
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    forcing_dir = FORCING_CMIP_FUT / model / ssp / shape_name / year_span

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
        shape=shapefile,
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


def generate_PCRGLOBWB_ERA5_forcing(shape_name: str, start: str, end: str):
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

    Returns:
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    forcing_dir = FORCING_PCRGLOB / f"ERA5_{year_span}" / shape_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefile,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset="ERA5",
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shapefile,
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
    shape_name: str,
    start: str,
    end: str,
    model: str = DEFAULT_CMIP6_MODELS["historical"],
    ensemble: str = "r1i1p1f1",
):
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

    Returns:
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    cmip_historical = {
        "project": "CMIP6",
        "exp": "historical",
        "dataset": model,
        "ensemble": ensemble,
        "grid": "gn",
    }

    # year for naming
    year_span = f"{start[:4]}-{end[:4]}"

    # Directory where forcing outputs will be stored
    forcing_dir = FORCING_PCRGLOB / f"CMIP6_{model}_{year_span}" / shape_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefile,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset=cmip_historical,
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shapefile,
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
    shape_name: str,
    start: str,
    end: str,
    ssp: str,
    model: str = DEFAULT_CMIP6_MODELS["future"],
    ensemble: str = "r1i1p1f1",
):
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

    Returns:
    -------
    ewatercycle.forcing.Forcing
        The generated forcing object
    """
    # Path to the shapefile
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

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
    forcing_dir = FORCING_PCRGLOB / "CMIP6" / model / ssp / ensemble / year_span / shape_name
    forcing_dir.mkdir(parents=True, exist_ok=True)

    esmvaltool_padding = 2

    lon_min_f, lat_min_f, lon_max_f, lat_max_f = get_integer_multiple_bounds(
        shapefile,  #   <----- add shapefiles here
        multiple=3,  # makes sure resolution is always correct
    )

    pcrglobwb_forcing = ewatercycle.forcing.sources["PCRGlobWBForcing"].generate(
        dataset=cmip_dataset,
        start_time=start,
        end_time=end,
        start_time_climatology=start,
        end_time_climatology=end,
        shape=shapefile,
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
    time_chunk_size=365,
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
    time_chunk_size : int, optional
        Number of time steps to keep in memory per chunk while regridding.

    Returns:
    -------
    xr.Dataset
        Regridded dataset.
    """
    cmip_path = Path(cmip_path)
    era5_path = Path(era5_path)

    if not cmip_path.exists():
        raise FileNotFoundError(f"CMIP forcing file does not exist: {cmip_path}")
    if cmip_path.stat().st_size == 0:
        raise ValueError(f"CMIP forcing file is empty: {cmip_path}")

    ds_cmip = xr.open_dataset(cmip_path, chunks={"time": time_chunk_size})
    ds_era5 = xr.open_dataset(era5_path)

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
    source_grid = ds_cmip.isel(time=0, drop=True) if "time" in ds_cmip.dims else ds_cmip

    regridder = xe.Regridder(
        source_grid,
        ds_era5,
        method=method,
        extrap_method=extrap_method,
        # reuse_weights=True,
    )

    # Apply regridding
    ds_out = regridder(ds_cmip)

    # Preserve metadata
    ds_out.attrs.update(ds_cmip.attrs)
    ds_out.attrs["regridded_to"] = "ERA5"
    ds_out.attrs["regridding_method"] = method

    if overwrite:
        with NamedTemporaryFile(dir=cmip_path.parent, suffix=".tmp", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        try:
            ds_out.to_netcdf(tmp_path)
            tmp_path.replace(cmip_path)
        finally:
            if tmp_path.exists() and tmp_path != cmip_path:
                tmp_path.unlink(missing_ok=True)

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
    cmip_future_forcing,
    cmip_historical_forcing,
    era5_forcing,
    method="quantile_delta_mapping",
    n_quantiles=1000,
    overwrite=True,
    spatial_chunk_size=16,
):
    """Bias-correct CMIP future PCR-GLOBWB forcing with ERA5 reference.

    Parameters
    ----------
    cmip_future_forcing : PCRGlobWBForcing
        CMIP future forcing object to be corrected.
    cmip_historical_forcing : PCRGlobWBForcing
        CMIP historical forcing object used as model baseline.
    era5_forcing : PCRGlobWBForcing
        ERA5 forcing object used as observational reference.
    method : str
        Bias-correction method from cmethods.
    n_quantiles : int
        Number of quantiles for quantile-based methods.
    overwrite : bool
        Overwrite CMIP future files after correction.
    spatial_chunk_size : int
        Chunk size used for lat/lon while correcting.

    Returns:
    -------
    None
        NetCDF files in cmip_future_forcing.directory are overwritten.
    """
    _bias_map_cmip_future_with_era5(
        obs_path=era5_forcing.directory / era5_forcing.precipitationNC,
        simh_path=cmip_historical_forcing.directory / cmip_historical_forcing.precipitationNC,
        simp_path=cmip_future_forcing.directory / cmip_future_forcing.precipitationNC,
        method=method,
        n_quantiles=n_quantiles,
        kind="*",
        overwrite=overwrite,
        spatial_chunk_size=spatial_chunk_size,
    )
    _bias_map_cmip_future_with_era5(
        obs_path=era5_forcing.directory / era5_forcing.temperatureNC,
        simh_path=cmip_historical_forcing.directory / cmip_historical_forcing.temperatureNC,
        simp_path=cmip_future_forcing.directory / cmip_future_forcing.temperatureNC,
        method=method,
        n_quantiles=n_quantiles,
        kind="+",
        overwrite=overwrite,
        spatial_chunk_size=spatial_chunk_size,
    )


def _pick_variable_name(ds, preferred_names):
    """Pick the first matching variable name, or fall back to the first variable."""
    for name in preferred_names:
        if name in ds.data_vars:
            return name
    return list(ds.data_vars)[0]


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

    # cmethods expects matching non-time coordinates.
    if "lat" in simh.dims and "lon" in simh.dims:
        obs = obs.interp(lat=simh["lat"], lon=simh["lon"], method="linear")
        simp = simp.interp(lat=simh["lat"], lon=simh["lon"], method="linear")

    obs, simh = xr.align(obs, simh, join="inner")

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
setup_bias_map_pcr_forcing = bias_map_pcrglobwb_forcing
