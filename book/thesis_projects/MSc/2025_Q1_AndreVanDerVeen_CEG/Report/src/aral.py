"""Aral Sea connected lake model.
Based on daily water balance including river inflow and evaporation.
"""

import glob
import os
import pickle
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr
from scipy.interpolate import interp1d
from tqdm.notebook import tqdm
import itertools
import yaml
import logging
DEFAULT_MODEL_COLOR = "#6c757d"

MODEL_COLORS = {
    "MPI-ESM1-2-HR": "#06d6a0",
    "MIROC6":         "#ffd166",
    "CanESM5":        "#3d348b",
    "MRI-ESM2-0":     "#6c757d"
}



# Load Makkink and groundwater inflow from config_aral.yaml (with sensible defaults)
logger = logging.getLogger(__name__)
try:
    CONFIG_PATH = Path(__file__).resolve().parents[1] / "config_aral.yaml"
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
            _cfg = yaml.safe_load(_f) or {}
        _aral_cfg = _cfg.get("aral_sea_experiment", {})
        MAKKINK_FACTOR = float(_aral_cfg.get("MAKKINK_FACTOR", _cfg.get("MAKKINK_FACTOR", 1.0)))
        GROUNDWATER_INFLOW = float(
            _aral_cfg.get("GROUNDWATER_INFLOW", _cfg.get("GROUNDWATER_INFLOW", 1.0 / 365.0))
        )
    else:
        logger.warning(f"Config file not found at {CONFIG_PATH}; using defaults")
        MAKKINK_FACTOR = 1.0
        GROUNDWATER_INFLOW = 1.0 / 365.0
except Exception:
    logger.exception("Failed to load config_aral.yaml; using default constants")
    MAKKINK_FACTOR = 1.0
    GROUNDWATER_INFLOW = 1.0 / 365.0
from src.paths import BATHYMETRY, DAHITI, GRDC, OUTPUT_HBV


# Geometry stuff, needs update later to account for separate north and south basins
class LakeGeometry:
    """Represent the geometry of a lake using an area-height-volume (AHV) relationship.

    This class provides methods to compute lake surface elevation and area
    from a given volume, based on an AHV curve loaded from CSV.

    TODO expand with north south split etc

    Attributes:
    ----------
    h_of_v : scipy.interpolate.interp1d
        Interpolation function for elevation (m) as a function of volume (km³).
    a_of_h : scipy.interpolate.interp1d
        Interpolation function for area (km²) as a function of elevation (m).
    """

    def __init__(self, ahv_csv):
        """Initialize LakeGeometry from an area-height-volume (AHV) CSV file.

        The CSV file must have columns:
            - elevation_m : lake surface elevation (meters)
            - volume_km3  : lake volume (km³)
            - area_km2    : lake surface area (km²)

        The constructor creates two interpolation functions:
            - elevation as a function of volume
            - area as a function of elevation

        Parameters
        ----------
        ahv_csv : str or Path
            Path to CSV file containing the AHV curve. Columns must be separated
            by ';' and decimal points may use ','.
        """
        if not Path(ahv_csv).exists():
            raise FileNotFoundError(f"AHV file not found: {ahv_csv}")

        df = pd.read_csv(ahv_csv, sep=";", decimal=",").sort_values("elevation_m")
        self.df = df  # Store the DataFrame for potential future use

        self.h_of_v = interp1d(
            df["volume_km3"], df["elevation_m"], bounds_error=False, fill_value="extrapolate"
        )

        self.a_of_h = interp1d(
            df["elevation_m"], df["area_km2"], bounds_error=False, fill_value="extrapolate"
        )

    def elevation_from_volume(self, V_km3):
        """Compute lake surface elevation from volume using interpolation.

        Parameters
        ----------
        V_km3 : float
            Lake volume in km³

        Returns:
        -------
        float
            Lake surface elevation in meters
        """
        if V_km3 < 0:
            raise ValueError(f"Volume cannot be negative: {V_km3}")
        return float(self.h_of_v(V_km3))

    def area_from_volume(self, V_km3):
        """Compute lake surface area from volume using interpolation.

        Internally, it first computes elevation from volume, then uses the
        area-elevation relationship.

        Parameters
        ----------
        V_km3 : float
            Lake volume in km³

        Returns:
        -------
        float
            Lake surface area in km²
        """
        if V_km3 < 0:
            raise ValueError(f"Volume cannot be negative: {V_km3}")
        h = self.elevation_from_volume(V_km3)

        return float(self.a_of_h(h))

    def plot_ahv_curve(self):
        """Plot the area-height-volume relationships for validation."""
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        df = self.df

        # 1. Area vs Height
        axes[0].plot(df["elevation_m"], df["area_km2"], marker="o", color="tab:blue")
        axes[0].set_xlabel("Height [m]")
        axes[0].set_ylabel("Area [km²]")
        axes[0].set_title("Area vs Height")
        axes[0].grid(True)

        # 2. Volume vs Height
        axes[1].plot(df["elevation_m"], df["volume_km3"], marker="o", color="tab:green")
        axes[1].set_xlabel("Height [m]")
        axes[1].set_ylabel("Volume [km³]")
        axes[1].set_title("Volume vs Height")
        axes[1].grid(True)

        # 3. Volume vs Area
        axes[2].plot(df["area_km2"], df["volume_km3"], marker="o", color="tab:orange")
        axes[2].set_xlabel("Area [km²]")
        axes[2].set_ylabel("Volume [km³]")
        axes[2].set_title("Volume vs Area")
        axes[2].grid(True)

        fig.tight_layout()
        return fig, axes


class River:
    def __init__(
        self, data, q_col=None, name=None, factor: float = 86400 / 1e9, scaling: float = 1
    ):
        """Wraps a river discharge time series for the lake model.

        Parameters
        ----------
        data : pd.DataFrame, pd.Series, xr.DataArray, xr.Dataset, str or Path
            Input time series. Can be:
            - pandas DataFrame or Series
            - xarray DataArray or Dataset
            - path to a NetCDF file (str or Path)
        q_col : str, optional
            Column name in DataFrame or Dataset (required if multiple variables)
        name : str, optional
            River name (for plotting)
        factor : float
            Unit conversion factor (e.g., m³/s → km³/day)
        scaling : float
            Additional scaling factor
        """
        self.name = name
        self.metadata = None

        # Handle string / Path input (NetCDF)
        if isinstance(data, (str, Path)):
            ds = xr.open_dataset(data)
            if q_col is None:
                # Use the first variable by default
                var_name = list(ds.data_vars)[0]
            else:
                var_name = q_col
            self.Q_raw = ds[var_name].to_pandas()

        # Handle xarray DataArray / Dataset
        elif isinstance(data, xr.DataArray):
            self.Q_raw = data.to_pandas()
        elif isinstance(data, xr.Dataset):
            if q_col is None:
                # Use the first variable by default
                var_name = list(data.data_vars)[0]
            else:
                var_name = q_col
            self.Q_raw = data[var_name].to_pandas()

        # Handle pandas DataFrame / Series
        elif isinstance(data, pd.DataFrame):
            if q_col is None:
                raise ValueError("q_col must be provided when passing a DataFrame")
            self.Q_raw = data[q_col]
        elif isinstance(data, pd.Series):
            self.Q_raw = data
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        # Ensure datetime index
        if not pd.api.types.is_datetime64_any_dtype(self.Q_raw.index):
            self.Q_raw.index = pd.to_datetime(self.Q_raw.index)

        # -------------------------
        # Detect monthly vs daily
        # -------------------------
        freq = pd.infer_freq(self.Q_raw.index)
        if freq and freq.startswith("M"):
            # Monthly average m³/s → daily km³/day via interpolation
            daily_index = pd.date_range(
                start=self.Q_raw.index.min(), end=self.Q_raw.index.max(), freq="D"
            )
            self.Q = self.Q_raw.reindex(daily_index).interpolate("time")  # m³/s daily
            self.Q = self.Q * factor * scaling  # convert to km³/day
        else:
            # Assume daily data already
            self.Q = self.Q_raw * factor * scaling

    def plot_yearly(
            self,
            skipna=True,
            return_fig=False,
            observations=None,
            observation_label="Observation",
            observation_kwargs=None,
            ax=None,
        ):
            Q = self.Q.copy()
            if skipna:
                Q = Q.dropna()

            yearly = Q.resample("YE").sum(min_count=1 if skipna else None)

            if ax is None:
                fig, ax = plt.subplots(figsize=(5, 4))
            else:
                fig = ax.figure

            ax.bar(yearly.index.year, yearly.values,
                color="skyblue",
                label=self.name or "Model")

            if observations is not None:
                if isinstance(observations, pd.DataFrame):
                    if observations.shape[1] != 1:
                        raise ValueError(
                            "observations DataFrame must contain exactly one discharge column"
                        )
                    observations = observations.iloc[:, 0]

                obs = pd.Series(observations).dropna()
                obs_index = obs.index

                if pd.api.types.is_datetime64_any_dtype(obs_index):
                    obs_years = pd.Index(obs_index).year
                else:
                    obs_years = pd.to_numeric(obs_index, errors="coerce")
                    if obs_years.isna().any():
                        obs_years = pd.to_datetime(obs_index, errors="coerce").year

                scatter_kwargs = {"color": "black", "s": 15, "zorder": 3}
                if observation_kwargs:
                    scatter_kwargs.update(observation_kwargs)

                ax.scatter(obs_years, obs.values,
                        label=observation_label,
                        **scatter_kwargs)

            ax.set_ylabel("Yearly Discharge (km³/yr)")
            ax.set_xlabel("Year")
            ax.set_title(f"{self.name} Yearly Discharge")
            ax.grid(True)

            if observations is not None:
                ax.legend()

            fig.tight_layout()

            if return_fig:
                return fig

            if ax is None:
                plt.show()

    def plot_daily(self, skipna=True):
        """Plot daily discharge as a line chart."""
        daily = self.Q.copy()
        if skipna:
            daily = daily.dropna()
        plt.figure(figsize=(12, 4))
        plt.plot(daily.index, daily.values, color="dodgerblue")
        plt.ylabel("Daily Discharge (km³/day)")
        plt.xlabel("Date")
        plt.title(f"{self.name} Daily Discharge")
        plt.grid(True)
        plt.show()

    def resample_5y_aligned(self, start_year: int, end_year: int, skipna=True) -> pd.DataFrame:
        """Compute yearly totals and then 5-year averages with aligned bins, returning a DataFrame.
        Index = first year of the bin, label as separate column.

        Parameters
        ----------
        start_year : int
            First year of the first 5-year bin
        end_year : int
            Last year to consider for bins
        skipna : bool
            Whether to skip NaNs when aggregating

        Returns:
        -------
        pd.DataFrame
            5-year average of yearly sums, index = first year of bin, 'bin_label' column included
        """
        # 1. Yearly totals
        yearly_sum = self.Q.resample("YE").sum()
        yearly_sum.index = yearly_sum.index.year  # convert to integer years

        if skipna:
            yearly_sum = yearly_sum.dropna()

        # 2. Aligned 5-year bins
        bins = list(range(start_year, end_year + 1, 5))
        labels = [f"{b}-{b+4}" for b in bins[:-1]]

        # 3. Group by bins
        grouped = yearly_sum.groupby(
            pd.cut(yearly_sum.index, bins=bins, labels=labels, right=True), observed=False
        )

        # 4. Compute 5-year average
        result = grouped.mean()

        # 5. Convert to DataFrame
        col_name = self.name or "River"
        df = pd.DataFrame({col_name: result})

        # 6. Add bin label as a separate column
        df["bin_label"] = df.index.astype(str)

        # 7. Change index to first year of the bin
        df.index = [int(label.split("-")[0]) for label in df["bin_label"]]

        return df

    @classmethod
    def from_pickle(
        cls, pkl_path: Path, name: str = None, scaling: float = 1.0, q_col: str = "m3_s"
    ):
        """Load a River object from a pickle saved by save_HBV_results.

        Parameters
        ----------
        pkl_path : Path
            Path to the pickle file
        name : str, optional
            River name; if None, will use name from metadata or "Unnamed"
        scaling : float, optional
            Scaling factor applied to discharge
        q_col : str, optional
            Column name in the DataFrame that contains discharge values
        """
        with open(pkl_path, "rb") as f:
            payload = pickle.load(f)
        df = payload["data"]
        river_name = name or payload["metadata"].get("name", "Unnamed")
        river = cls(df, q_col=q_col, name=river_name, scaling=scaling)
        river.metadata = payload["metadata"]
        return river


class MultiRiver:
    def __init__(self, rivers, q_col=None, factor: float = 86400 / 1e9, scaling: float = 1):
        """Wrapper for multiple rivers.

        Parameters
        ----------
        rivers : dict
            Keys = river names, values = data (DataFrame/Series/xarray/NetCDF)
        q_col : str, optional
            Column name for DataFrames/Datasets with multiple variables
        factor, scaling : float
            Unit conversion and scaling
        """
        self.rivers = {}
        for name, data in rivers.items():
            if isinstance(data, River):
                self.rivers[name] = data
            else:
                self.rivers[name] = River(data, name=name)

    def plot_yearly(self, return_fig=False):
        fig, ax = plt.subplots(figsize=(12, 5))
        for name, river in self.rivers.items():
            yearly = river.Q.resample("YE").sum()
            ax.plot(yearly.index.year, yearly.values, marker="o", label=name)
        ax.set_ylabel("Yearly Discharge (km³/yr)")
        ax.set_xlabel("Year")
        ax.set_title("Yearly Discharge - Multiple Rivers")
        ax.grid(True)
        ax.legend()
        fig.tight_layout()

        if return_fig:
            return fig

        plt.show()

    def plot_daily(self):
        plt.figure(figsize=(12, 5))
        for name, river in self.rivers.items():
            daily = river.Q.dropna()
            plt.plot(daily.index, daily.values, label=name)
        plt.ylabel("Daily Discharge (km³/day)")
        plt.xlabel("Date")
        plt.title("Daily Discharge - Multiple Rivers")
        plt.grid(True)
        plt.legend()
        plt.show()


# fluxes
def discharge_to_km3day(Q_m3s):
    """Converts discharge from m3s to km3day

    :param Q_m3s: Description
    """
    return Q_m3s * 86400 / 1e9


def compute_total_river_inflow(i, rivers, connected=True):
    """Compute river inflow(s) for timestep i.

    Parameters
    ----------
    i : int
        Time index
    rivers : list of River
        List of River objects
    connected : bool
        If True, sum all rivers into one inflow
        If False, can be used for split-lake routing (future)

    Returns:
    -------
    float
        Total inflow (connected case)
    """
    if connected:
        return sum(r.Q.iloc[i] for r in rivers)
    # Placeholder for future north/south split
    # e.g., return {'north': rivers[1].Q.iloc[i], 'south': rivers[0].Q.iloc[i]}
    return sum(r.Q.iloc[i] for r in rivers)


def compute_evaporation_km3day(evap_flux_kg_m2_s, area_km2):
    """Convert potential evaporation flux to km3/day.

    Parameters
    ----------
    evap_flux_kg_m2_s : float
        Evaporation flux in kg m^-2 s^-1
    area_km2 : float
        Lake area in km^2

    Returns:
    -------
    float
        Evaporation in km3/day
    """
    # kg/m²/s → mm/day
    evap_mm_day = evap_flux_kg_m2_s * 86400

    # mm/day → km³/day
    evap_km3_day = evap_mm_day / 1e6 * area_km2

    # makkink conversion factor open water evaporation
    evap_km3_day = MAKKINK_FACTOR * evap_km3_day
    return evap_km3_day


def compute_precip_km3day(precip_mm_day, area_km2):
    """Convert potential precip flux to km3/day. very rudimenteray right now

    TODO expand this.


    Parameters
    ----------
    precip_mm_day : float
        precip flux in mm day^-1
    area_km2 : float
        Lake area in km^2

    Returns:
    -------
    float
        precip in km3/day
    """
    # kg/m²/s → mm/day

    # mm/day → km³/day
    precip_km3_day = precip_mm_day / 1e6 * area_km2

    # makkink conversion factor open water evaporation
    # evap_km3_day = MAKKINK_FACTOR * evap_km3_day
    return precip_km3_day


## Daily status update - Volume balance
def update_volume(
    V_prev,
    Q_in,
    evap,
    Q_gw=GROUNDWATER_INFLOW,
    scale_inflow=1.0,
    precip=0,
):
    """Updates the volume for the volume balance model. rudimentary right now."""
    V_new = V_prev + scale_inflow * Q_in - Q_gw - evap + precip
    return max(V_new, 0.0)


# --- main model ---
def run_connected_aral_model(
    aral_meteo: xr.Dataset,  # xarray Dataset with meteo forcing, must containg [evspsblpot]
    rivers: list["River"],  # list of River objects, e.g., [River_Amu_Darya, River_Syr_Darya]
    ahv_csv: str,  # path to A-H-V CSV file with columns: elevation_m, volume_km3, area_km2
    V0_km3: float = 1100,  # initial lake volume [km3]
    start_time=None,  # optional: datetime-like string or pd.Timestamp
    end_time=None,  # optional: datetime-like string or pd.Timestamp
    show_progress: bool = True,
    tqdm_position: int = 0,
    aral_precip: xr.Dataset = None,  # xarray Dataset with meteo forcing, must containg [evspsblpot]
) -> pd.DataFrame:
    """Connected Aral Sea daily water balance model.

    Parameters
    ----------
    aral_meteo : xarray.Dataset
        Meteorological forcing, must contain 'evspsblpot'
    rivers : list of River
        List of River objects (must have .Q attribute)
    ahv_csv : str
        Path to A-H-V CSV file
    V0_km3 : float
        Initial lake volume [km3]

    Returns:
    -------
    pandas.DataFrame
        Columns: time, volume_km3, area_km2, elevation_m
    """
    # --- Slice meteorological forcing ---
    if start_time is not None or end_time is not None:
        aral_meteo = aral_meteo.sel(time=slice(start_time, end_time))

    # --- Slice river time series (without mutating River objects) ---
    river_q_series = []
    for r in rivers:
        q = r.Q
        if start_time is not None or end_time is not None:
            q = q.loc[slice(pd.to_datetime(start_time), pd.to_datetime(end_time))]
        river_q_series.append(q)

    n = min(len(aral_meteo.time), min(len(q) for q in river_q_series))

    V = pd.Series(index=range(n), dtype=float)
    A = pd.Series(index=range(n), dtype=float)
    H = pd.Series(index=range(n), dtype=float)
    Q_in_series = pd.Series(index=range(n), dtype=float)
    evap_series = pd.Series(index=range(n), dtype=float)
    precip_series = pd.Series(index=range(n), dtype=float)

    V.iloc[0] = V0_km3
    geom = LakeGeometry(ahv_csv)

    it = range(1, n)
    if show_progress:
        it = tqdm(
            it, desc="Simulating Aral Sea volume balance", position=tqdm_position, leave=False
        )

    for i in it:
        # Geometry
        A.iloc[i] = geom.area_from_volume(V.iloc[i - 1])
        H.iloc[i] = geom.elevation_from_volume(V.iloc[i - 1])

        # Total river inflow
        Q_in = sum(q.iloc[i] for q in river_q_series)
        Q_in_series.iloc[i] = Q_in

        if H.iloc[i] >= 64:
            Q_in = 0

        # Evaporation
        evap = compute_evaporation_km3day(aral_meteo["evspsblpot"].isel(time=i).values, A.iloc[i])
        evap_series.iloc[i] = evap

        # Precipitation
        precip = 0
        if aral_precip:
            precip = compute_precip_km3day(aral_precip["pr"].isel(time=i).values, A.iloc[i])
        precip_series.iloc[i] = precip

        # Update volume
        V.iloc[i] = update_volume(V.iloc[i - 1], Q_in, evap, precip=precip)

    return pd.DataFrame(
        {
            "time": aral_meteo.time.values[:n],
            "volume_km3": V,
            "area_km2": A,
            "elevation_m": H,
            "Q_in_km3day": Q_in_series,
            "evap_km3day": evap_series,
            "precip_km3day": precip_series,
        }
    )

# --- main model ---
def run_connected_aral_model_karakum(
    aral_meteo: xr.Dataset,  # xarray Dataset with meteo forcing, must containg [evspsblpot]
    rivers: list["River"],  # list of River objects, e.g., [River_Amu_Darya, River_Syr_Darya]
    ahv_csv: str,  # path to A-H-V CSV file with columns: elevation_m, volume_km3, area_km2
    V0_km3: float = 1100,  # initial lake volume [km3]
    start_time=None,  # optional: datetime-like string or pd.Timestamp
    end_time=None,  # optional: datetime-like string or pd.Timestamp
    show_progress: bool = True,
    tqdm_position: int = 0,
    aral_precip: xr.Dataset = None,  # xarray Dataset with meteo forcing, must containg [evspsblpot]
    karakum: str = None, #path to KarakumCanal csv with columns: year; km3; m3s
) -> pd.DataFrame:
    """Connected Aral Sea daily water balance model.

    Parameters
    ----------
    aral_meteo : xarray.Dataset
        Meteorological forcing, must contain 'evspsblpot'
    rivers : list of River
        List of River objects (must have .Q attribute)
    ahv_csv : str
        Path to A-H-V CSV file
    V0_km3 : float
        Initial lake volume [km3]

    Returns:
    -------
    pandas.DataFrame
        Columns: time, volume_km3, area_km2, elevation_m
    """
    #---- load karakum canal data if provided ---
    if karakum:
        karakum_df = pd.read_csv(karakum, sep=";", decimal=",")
        karakum_df["time"] = pd.to_datetime(karakum_df["year"], format="%Y")
        karakum_q_series = karakum_df.set_index("time")["m3s"].resample("D").interpolate("time")
        karakum_daily =  discharge_to_km3day(karakum_q_series)

    # --- Slice meteorological forcing ---
    if start_time is not None or end_time is not None:
        aral_meteo = aral_meteo.sel(time=slice(start_time, end_time))

    # --- Slice river time series (without mutating River objects) ---
    river_q_series = []
    for r in rivers:
        q = r.Q
        if start_time is not None or end_time is not None:
            q = q.loc[slice(pd.to_datetime(start_time), pd.to_datetime(end_time))]
        river_q_series.append(q)

    n = min(len(aral_meteo.time), min(len(q) for q in river_q_series))

    V = pd.Series(index=range(n), dtype=float)
    A = pd.Series(index=range(n), dtype=float)
    H = pd.Series(index=range(n), dtype=float)
    Q_in_series = pd.Series(index=range(n), dtype=float)
    evap_series = pd.Series(index=range(n), dtype=float)
    precip_series = pd.Series(index=range(n), dtype=float)

    V.iloc[0] = V0_km3
    geom = LakeGeometry(ahv_csv)

    it = range(1, n)
    if show_progress:
        it = tqdm(
            it, desc="Simulating Aral Sea volume balance", position=tqdm_position, leave=False
        )

    for i in it:
        # Geometry
        A.iloc[i] = geom.area_from_volume(V.iloc[i - 1])
        H.iloc[i] = geom.elevation_from_volume(V.iloc[i - 1])

        # Total river inflow
        Q_in = sum(q.iloc[i] for q in river_q_series)
        Q_in_series.iloc[i] = Q_in

        if H.iloc[i] >= 64:
            Q_in = 0

        # Evaporation
        evap = compute_evaporation_km3day(aral_meteo["evspsblpot"].isel(time=i).values, A.iloc[i])
        evap_series.iloc[i] = evap

        # Precipitation
        precip = 0
        if aral_precip:
            precip = compute_precip_km3day(aral_precip["pr"].isel(time=i).values, A.iloc[i])
        precip_series.iloc[i] = precip

        # Update volume
        V.iloc[i] = update_volume(V.iloc[i - 1], Q_in, evap, precip=precip)

    return pd.DataFrame(
        {
            "time": aral_meteo.time.values[:n],
            "volume_km3": V,
            "area_km2": A,
            "elevation_m": H,
            "Q_in_km3day": Q_in_series,
            "evap_km3day": evap_series,
            "precip_km3day": precip_series,
        }
    )


def plot_aral_results(results, labels=None, observations=None, ahv_csv=None, title=None, legend=True, save_path=None, smooth=False):
    """Plot one or more Aral Sea simulation results side-by-side, optionally with observations.

    Parameters
    ----------
    results : pandas.DataFrame or list of pandas.DataFrame
        Single simulation or a list of simulation results. Must contain:
        'time', 'volume_km3', 'elevation_m', 'area_km2'
    labels : list of str, optional
        Labels for each simulation. If None, default labels will be used.
    observations : list of tuples (df, label), optional
        Observation datasets to overlay. Each tuple: (DataFrame, label)
        DataFrame must have columns 'time' and 'elevation_m'
    ahv_csv : str or Path, optional
        Path to the AHV curve CSV used to derive observation volume and area
        from elevation. If None, the default bathymetry curve is used.

    Returns:
    -------
    None
        Displays a matplotlib figure.
    """

    geometry = LakeGeometry(ahv_csv or (BATHYMETRY / "ahv_curve.csv"))
    v_of_h = interp1d(
        geometry.df["elevation_m"],
        geometry.df["volume_km3"],
        bounds_error=False,
        fill_value="extrapolate",
    )

    # Ensure results is a list
    if not isinstance(results, list):
        results = [results]

    n_results = len(results)

    # Default labels
    if labels is None:
        labels = [f"Simulation {i+1}" for i in range(n_results)]

    # Create subplots
    fig, axs = plt.subplots(1, 3, figsize=(18, 5))

    # Define colors
    colors = plt.cm.tab10.colors  # up to 10 colors
    colors = colors * ((n_results // 10) + 1)

    # Plot each simulation
    for df, label, color in zip(results, labels, colors):
        
        # 2. Make sure time is a datetime object for resampling
        df["time"] = pd.to_datetime(df["time"])
        
        # 3. Apply resampling if smooth=True
        if smooth:
            df_plot = (
                df.set_index("time")
                .resample("YE")   # 'YE' stands for Year End. (Use 'Y' if your pandas is older than v2.0.0)
                .mean()           # Averages out any sub-yearly oscillations/noise
                .reset_index()
            )
        else:
            df_plot = df          # Default behavior uses raw data
            
        # 4. Use df_plot for your actual plotting calls
        axs[0].plot(df_plot["time"], df_plot["volume_km3"], label=label, color=color)
        axs[1].plot(df_plot["time"], df_plot["elevation_m"], label=label, color=color)
        axs[2].plot(df_plot["time"], df_plot["area_km2"], label=label, color=color)
    

    colors = ["lightgray", "dimgray"]
   
    # Plot observations if provided
    if observations is not None:
        for i, obs in enumerate(observations):

            color = colors[i]
            # obs can be tuple (df, label)
            if isinstance(obs, tuple):
                df_obs, obs_label = obs
            elif isinstance(obs, pd.DataFrame):
                df_obs, obs_label = obs, "Observation"
            else:
                continue  # skip invalid

            if "elevation_m" not in df_obs.columns:
                continue

            df_obs = df_obs.copy()
            df_obs["volume_km3"] = df_obs["elevation_m"].apply(
                lambda h: float(v_of_h(h)) if pd.notna(h) else float("nan")
            )
            df_obs["area_km2"] = df_obs["elevation_m"].apply(
                lambda h: float(geometry.a_of_h(h)) if pd.notna(h) else float("nan")
            )

            axs[0].plot(
                df_obs["time"],
                df_obs["volume_km3"],
   #             marker=marker,
                color=color,
 #               s=25,
                label=obs_label,
            )
            axs[1].plot(
                df_obs["time"],
                df_obs["elevation_m"],
   #             marker=marker,
                color=color,
 #               s=25,
                label=obs_label,
            )
            axs[2].plot(
                df_obs["time"],
                df_obs["area_km2"],
   #             marker=marker,
                color=color,
    #            s=25,
                label=obs_label,
            )

    # Set titles and labels
    axs[0].set_ylabel("Volume (km³)", fontweight="bold")
    axs[0].set_title("Volume", fontsize=12, fontweight="bold")
    axs[1].set_ylabel("Elevation (m)",fontweight="bold")
    axs[1].set_title("Elevation", fontsize=12, fontweight="bold")
    axs[2].set_ylabel("Area (km²)", fontweight="bold")
    axs[2].set_title("Area", fontsize=12, fontweight="bold")

    for ax in axs:
        ax.set_xlabel("Time", fontweight="bold")
        ax.grid(alpha=0.3, linestyle="--")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        if legend:
            ax.legend(loc="lower left",fontsize="small")
    
    if title:
        fig.suptitle(title, fontsize=16, fontweight="bold")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Plot successfully saved to: {save_path}")
    plt.show()


# def plot_aral_elevation(results, labels=None, observations=None, plot_max_elevation_line=True, title="Aral Sea Elevation", legend=True):
#     """Plot only Aral Sea elevation time series, optionally with observations.

#     Parameters
#     ----------
#     results : pandas.DataFrame or list of pandas.DataFrame
#         Single simulation or a list of simulation results.
#         Each DataFrame must contain 'time' and 'elevation_m'.
#     labels : list of str, optional
#         Labels for each simulation. If None, default labels will be used.
#     observations : list of tuples (df, label), optional
#         Observation datasets to overlay. Each tuple: (DataFrame, label)
#         DataFrame must have columns 'time' and 'elevation_m'.

#     Returns:
#     -------
#     None
#         Displays a matplotlib figure.
#     """
#     if not isinstance(results, list):
#         results = [results]

#     n_results = len(results)

#     if labels is None:
#         labels = [f"Simulation {i+1}" for i in range(n_results)]

#     fig, ax = plt.subplots(1, 1, figsize=(9, 5))

#     colors = plt.cm.tab10.colors
#     colors = colors * ((n_results // 10) + 1)

#     for df, label, color in zip(results, labels, colors):
#         ax.plot(df["time"], df["elevation_m"], label=label, color=color)

    
#     #colors_obs = ["lightgray", "dimgray"]
#     colors_obs = ["black", "black"]
#     markers_obs = ["o", ""]

#     if observations is not None:
#         for i, obs in enumerate(observations):

#             color = colors_obs[i % len(colors_obs)]  # veilig bij meer observaties
#             marker = markers_obs[i % len(markers_obs)]

#             if isinstance(obs, tuple):
#                 df_obs, obs_label = obs
#             elif isinstance(obs, pd.DataFrame):
#                 df_obs, obs_label = obs, "Observation"
#             else:
#                 continue

#             # df_obs = df_obs.set_index(pd.to_datetime(df_obs["time"]))
#             # df_obs = df_obs.resample("ME").mean().reset_index(drop=True)

#             ax.plot(
#                 df_obs["time"],
#                 df_obs["elevation_m"],
#                 color=color,
#                 marker=marker,
#                 markersize=3,
#                 label=obs_label,
#             )

#     if plot_max_elevation_line:
#         ax.axhline(
#             y=64,
#             color="tab:red",
#             linestyle="--",
#             linewidth=2,
#             label="basin overflow threshold"
#         )

#     ax.set_xlabel("Time")
#     ax.set_ylabel("Elevation (m)")
#     if plt.title is not None:
#         ax.set_title(title)



#     ax.grid(alpha=0.3, linestyle="--")
#     ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
#     plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
#     if legend is not None:
#         ax.legend(
#             loc="best",
#             fontsize=8,
#             frameon=False,
#             handlelength=1.5,
#             handletextpad=0.5,
#             borderpad=0.3,
#         )

#     all_times = pd.concat([df["time"] for df in results])

#     ax.set_xlim(
#         all_times.min(),
#         all_times.max() + pd.DateOffset(years=6)
#     )
#     plt.tight_layout()
#     plt.show()
def model_color(name: str, index: int = 0) -> str:
    for key, color in MODEL_COLORS.items():
        if key in name:
            if color == DEFAULT_MODEL_COLOR:
                return plt.cm.tab10.colors[(index + 1) % 10]
            return color
    return plt.cm.tab10.colors[(index + 1) % 10]

def model_label(name: str) -> str:
    return MODEL_COLORS .get(name, {}).get("label", name)


def plot_aral_elevation(results, labels=None, observations=None, plot_max_elevation_line=True, title="Aral Sea Elevation", legend=True, save_path : str=None):
    if not isinstance(results, list):
        results = [results]
    n_results = len(results)
    if labels is None:
        labels = [f"Simulation {i+1}" for i in range(n_results)]

    fig, ax = plt.subplots(1, 1, figsize=(6, 4))
    colors = plt.cm.tab10.colors
    colors = colors * ((n_results // 10) + 1)

    for i, (df, label, color) in enumerate(zip(results, labels, colors)):
        color = model_color(label, index=i)
        ax.plot(df["time"], df["elevation_m"], label=label, color=color, linewidth=2)

    # Get time window from results
    all_times = pd.concat([df["time"] for df in results])
    t_min, t_max = all_times.min(), all_times.max()

    colors_obs = ["black", "black"]
    markers_obs = ["o", ""]

    if observations is not None:
        for i, obs in enumerate(observations):
            color = colors_obs[i % len(colors_obs)]
            marker = markers_obs[i % len(markers_obs)]
            if isinstance(obs, tuple):
                df_obs, obs_label = obs
            elif isinstance(obs, pd.DataFrame):
                df_obs, obs_label = obs, "Observation"
            else:
                continue

            # Fix index and resample
            # df_obs = df_obs.copy()
            # df_obs = df_obs.set_index(pd.to_datetime(df_obs["time"]))
            # df_obs = df_obs.resample("ME").mean()

            # Slice to results time window
            df_obs = df_obs[(df_obs["time"] >= t_min) & (df_obs["time"] <= t_max)]

            ax.plot(
                df_obs["time"],
                df_obs["elevation_m"],
                color=color,
                marker=marker,
                markersize=3,
                linestyle="-",      # explicitly draw the line
                label=obs_label,
            )

    if plot_max_elevation_line:
        ax.axhline(y=64, color="tab:red", linestyle="--", linewidth=1, label="basin overflow threshold")

    ax.set_xlabel("Time")
    ax.set_ylabel("Elevation (m)")
    ax.set_title(title)
    ax.set_ylim(0, 70)
    ax.grid(alpha=0.3, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    if legend is not None:
        ax.legend(loc="best", fontsize=8, frameon=False, handlelength=1.5, handletextpad=0.5, borderpad=0.3)

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Plot successfully saved to: {save_path}")
    #ax.set_xlim(t_min, t_max) # + pd.DateOffset(years=6))
    plt.tight_layout()
    plt.show()

def plot_aral_volume(results, labels=None, observations=None, ahv_csv=None):
    """Plot only Aral Sea volume time series, optionally with observations.

    Parameters
    ----------
    results : pandas.DataFrame or list of pandas.DataFrame
        Single simulation or a list of simulation results.
        Each DataFrame must contain 'time' and 'volume_km3'.
    labels : list of str, optional
        Labels for each simulation. If None, default labels will be used.
    observations : list of tuples (df, label), optional
        Observation datasets to overlay. Each tuple: (DataFrame, label)
        DataFrame must have columns 'time' and 'volume_km3'.

    Returns:
    -------
    None
        Displays a matplotlib figure.
    """
    if not isinstance(results, list):
        results = [results]

    n_results = len(results)

    if labels is None:
        labels = [f"Simulation {i+1}" for i in range(n_results)]
    
    geometry = LakeGeometry(ahv_csv or (BATHYMETRY / "ahv_curve.csv"))
    v_of_h = interp1d(
        geometry.df["elevation_m"],
        geometry.df["volume_km3"],
        bounds_error=False,
        fill_value="extrapolate",
    )

    fig, ax = plt.subplots(1, 1, figsize=(9, 5))

    colors = plt.cm.tab10.colors
    colors = colors * ((n_results // 10) + 1)

    for df, label, color in zip(results, labels, colors):
        ax.plot(df["time"], df["volume_km3"], label=label, color=color)

    
    #colors_obs = ["lightgray", "dimgray"]
    colors_obs = ["black", "black"]
    markers_obs = ["o", ""]

    if observations is not None:
        for i, obs in enumerate(observations):

            color = colors_obs[i % len(colors_obs)]  # veilig bij meer observaties
            marker = markers_obs[i % len(markers_obs)]

            if isinstance(obs, tuple):
                df_obs, obs_label = obs
            elif isinstance(obs, pd.DataFrame):
                df_obs, obs_label = obs, "Observation"
            else:
                continue
        
        
            df_obs = df_obs.copy()
            df_obs["volume_km3"] = df_obs["elevation_m"].apply(
                lambda h: float(v_of_h(h)) if pd.notna(h) else float("nan")
            )

            
            ax.plot(
                df_obs["time"],
                df_obs["volume_km3"],
                color=color,
                marker=marker,
                markersize=3,
                label=obs_label,
            )

    ax.axhline(
        y=1800,
        color="tab:red",
        linestyle="--",
        linewidth=2,
        label="basin overflow threshold"
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Volume (km³)")
    ax.set_title("Aral Sea Volume")
    ax.grid(alpha=0.3, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.legend(
        loc="best",
        fontsize=8,
        frameon=False,
        handlelength=1.5,
        handletextpad=0.5,
        borderpad=0.3,
    )

    all_times = pd.concat([df["time"] for df in results])

    ax.set_xlim(
        all_times.min(),
        all_times.max() + pd.DateOffset(years=6)
    )
    plt.tight_layout()
    plt.show()

    return fig


def plot_aral_ensemble_results(sim_results, groups=None, observations=None):
    """Plot ensemble Aral Sea simulation results with optional observations.

    Parameters
    ----------
    sim_results : list of pd.DataFrame
        List of simulation outputs from run_connected_aral_model.
        Each DataFrame must have columns: 'time', 'volume_km3', 'area_km2', 'elevation_m'.
    groups : list of str, optional
        Same length as sim_results. Group label for each simulation,
        e.g., ["ERA5"]*10 + ["CMIP"]*10.
        All simulations in the same group get the same color.
    observations : list of tuples (df, label), optional
        Observation datasets to overlay. Each tuple: (DataFrame, label)
        DataFrame must have columns 'time' and 'elevation_m'

    """
    import matplotlib.pyplot as plt

    if not isinstance(sim_results, list):
        sim_results = [sim_results]

    n_sims = len(sim_results)

    # Default groups
    if groups is None:
        groups = ["Sim"] * n_sims

    unique_groups = list(dict.fromkeys(groups))
    cmap = plt.cm.tab10
    group_colors = {g: cmap(i % 10) for i, g in enumerate(unique_groups)}

    fig, axs = plt.subplots(1, 3, figsize=(18, 5))

    # Plot each simulation
    for df, group in zip(sim_results, groups):
        color = group_colors[group]
        axs[0].plot(df["time"], df["volume_km3"], color=color, linewidth=1, alpha=0.7)
        axs[1].plot(df["time"], df["elevation_m"], color=color, linewidth=1, alpha=0.7)
        axs[2].plot(df["time"], df["area_km2"], color=color, linewidth=1, alpha=0.7)

    # Plot observations if provided (on elevation subplot only)
    if observations is not None:
        plotted_labels = set()
        for obs in observations:
            if isinstance(obs, tuple):
                df_obs, obs_label = obs
            elif isinstance(obs, pd.DataFrame):
                df_obs, obs_label = obs, "Historical"
            else:
                continue

            # Only plot once per label
            if obs_label in plotted_labels:
                axs[1].scatter(df_obs["time"], df_obs["elevation_m"], marker=".", color="k", s=25)
            else:
                axs[1].scatter(
                    df_obs["time"],
                    df_obs["elevation_m"],
                    marker=".",
                    color="k",
                    s=25,
                    label=obs_label,
                )
                plotted_labels.add(obs_label)

    # Set titles and labels
    axs[0].set_title("Aral Sea Volume (km³)")
    axs[0].set_ylabel("Volume (km³)")
    axs[1].set_title("Aral Sea Elevation (m)")
    axs[1].set_ylabel("Elevation (m)")
    axs[2].set_title("Aral Sea Area (km²)")
    axs[2].set_ylabel("Area (km²)")

    for ax in axs:
        ax.set_xlabel("Time")
        ax.grid(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # Legends
    for ax in axs:
        # Ensemble group legend
        for group, color in group_colors.items():
            ax.plot([], [], color=color, label=group)
        ax.legend()

    plt.setp(axs[0].get_xticklabels(), rotation=45, ha="right")
    plt.setp(axs[1].get_xticklabels(), rotation=45, ha="right")
    plt.setp(axs[2].get_xticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    plt.show()


def plot_aral_fluxes(df):
    """Plot yearly inflow, evaporation, and net flux for the Aral Sea simulation.

    Creates three side-by-side subplots with the same y-axis scale for inflow and evaporation.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing simulation results with columns:
        - 'time' : datetime-like
        - 'Q_in_km3day' : daily inflow in km³/day
        - 'evap_km3day' : daily evaporation in km³/day

    Returns:
    -------
    None
    """
    # Resample to yearly totals
    df_yearly = df.set_index("time").resample("YE").sum()

    # Net flux (inflow - evaporation)
    df_yearly["net_flux"] = (
        df_yearly["Q_in_km3day"] + df_yearly["precip_km3day"] - df_yearly["evap_km3day"]
    )

    # Determine shared y-axis limit for inflow and evaporation
    y_max = 1.1 * max(df_yearly["Q_in_km3day"].max(), df_yearly["evap_km3day"].max())
    # For net flux, allow both positive and negative values
    net_min = 1.1 * df_yearly["net_flux"].min()
    net_max = 1.1 * df_yearly["net_flux"].max()

    fig, axs = plt.subplots(1, 3, figsize=(20, 5))

    # Yearly inflow
    axs[0].bar(df_yearly.index.year, df_yearly["Q_in_km3day"], color="tab:blue")
    axs[0].set_title("Yearly River Inflow")
    axs[0].set_xlabel("Year")
    axs[0].set_ylabel("Inflow (km³/yr)")
    axs[0].set_ylim(0, y_max)
    axs[0].grid(True)

    # Yearly evaporation
    axs[1].bar(df_yearly.index.year, df_yearly["evap_km3day"], color="tab:red")
    axs[1].set_title("Yearly Evaporation")
    axs[1].set_xlabel("Year")
    axs[1].set_ylabel("Evaporation (km³/yr)")
    axs[1].set_ylim(0, y_max)
    axs[1].grid(True)

    # Yearly net flux
    axs[2].bar(df_yearly.index.year, df_yearly["net_flux"], color="tab:green")
    axs[2].set_title("Yearly Net Flux (Inflow - Evaporation)")
    axs[2].set_xlabel("Year")
    axs[2].set_ylabel("Net Flux (km³/yr)")
    axs[2].set_ylim(net_min, net_max)
    axs[2].grid(True)

    plt.tight_layout()
    plt.show()


def save_aral_simulation(aral_df, save_dir, prefix="aral_sim"):
    """Save Aral Sea simulation results in CSV, pickle, and NetCDF formats.

    Parameters
    ----------
    aral_df : pandas.DataFrame
        Simulation results containing a 'time' column.
    save_dir : str or Path
        Directory where files will be saved.
    prefix : str, default "aral_sim"
        Prefix for the saved files.

    Returns:
    -------
    dict
        Paths of the saved files.
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # CSV
    csv_path = save_dir / f"{prefix}.csv"
    aral_df.to_csv(csv_path, index=False)
    paths["csv"] = csv_path

    # Pickle
    pkl_path = save_dir / f"{prefix}.pkl"
    aral_df.to_pickle(pkl_path)
    paths["pkl"] = pkl_path

    # NetCDF via xarray
    nc_path = save_dir / f"{prefix}.nc"
    # Convert DataFrame to xarray
    ds = aral_df.set_index("time").to_xarray()
    ds.to_netcdf(nc_path)
    paths["nc"] = nc_path

    return paths


def load_grdc_monthly(grdc_id: int, q_col="Original", name="None") -> pd.DataFrame:
    """Load a GRDC monthly discharge file and return a clean DataFrame
    indexed by datetime with monthly frequency.

    Parameters
    ----------
    file : str or Path
        Path to the GRDC monthly text file
    q_col : str
        Column name to select as discharge

    Returns:
    -------
    pd.DataFrame
        DataFrame with datetime index (month start) and discharge column
    """
    df = pd.read_csv(
        GRDC / "Monthly" / f"{grdc_id}_Q_Month.txt",
        sep=";",
        comment="#",
        usecols=["YYYY-MM-DD", f" {q_col}"],  # original file may have leading space
        parse_dates=["YYYY-MM-DD"],
        encoding="latin1",
        na_values=-999.0,
    )

    df.columns = df.columns.str.strip()
    df = df[["YYYY-MM-DD", q_col]]

    # Set datetime index with monthly frequency
    df["YYYY-MM-DD"] = pd.to_datetime(df["YYYY-MM-DD"])
    df.set_index("YYYY-MM-DD", inplace=True)
    df.index = df.index.to_period("M").to_timestamp()

    # Set river name if not provided
    if name is None:
        name = f"GRDC {grdc_id}"

    # Return River object
    return River(df, q_col=q_col, name=name)


def load_rivers(station_name, scaling_era5=1.0, scaling_cmip=1.0):
    """Load River objects for a given station, both ERA5 and CMIP_HIST.

    Parameters
    ----------
    station_name : str
        Folder name of the station inside OUTPUT_HBV.
    scaling_era5 : float
        Scaling factor for ERA5 pickles.
    scaling_cmip : float
        Scaling factor for CMIP_HIST pickles.

    Returns:
    -------
    dict
        Dictionary with keys 'ERA5' and 'CMIP_HIST', values are lists of aral.River objects.
    """
    station_dir = OUTPUT_HBV / station_name

    # ERA5
    pkl_files_era5 = sorted(station_dir.glob(f"ERA5/{station_name}_ERA5_1940-2020_cmaes_*.pkl"))
    rivers_era5 = [River.from_pickle(pkl, scaling=scaling_era5) for pkl in pkl_files_era5]

    # CMIP_HIST
    pkl_files_cmip = sorted(
        station_dir.glob(f"CMIP_HIST/{station_name}_CMIP_HIST_1940-2014_cmaes_*.pkl")
    )
    rivers_cmip = [River.from_pickle(pkl, scaling=scaling_cmip) for pkl in pkl_files_cmip]

    return {"ERA5": rivers_era5, "CMIP_HIST": rivers_cmip}


def make_obs():  # csv_file: Path, nc_folder: Path):
    """Load historical CSV and DAHITI NetCDF water level observations
    and return a list of tuples (DataFrame, label).

    Parameters
    ----------

    Returns:
    -------
    obs_list : list of tuples
        Each tuple is (df, label), where df has columns ['time', 'elevation_m']
    """
    obs_list = []

    csv_file = BATHYMETRY / "Nachtnebel_table.csv"
    nc_folder = DAHITI

    # ---------- CSV (historical table) ----------
    if csv_file.exists():
        df_csv = pd.read_csv(csv_file, sep=";", decimal=",")

        if not {"Year", "elevation"}.issubset(df_csv.columns):
            raise ValueError(
                f"CSV must contain columns 'Year' and 'elevation'. Found: {df_csv.columns}"
            )

        df_csv = df_csv[["Year", "elevation"]].copy()
        df_csv["time"] = pd.to_datetime(df_csv["Year"], format="%Y")
        df_csv["elevation_m"] = df_csv["elevation"].astype(float)

        obs_list.append((df_csv[["time", "elevation_m"]], "Historical - Nachtnebel"))
    else:
        print(f"CSV file not found: {csv_file}")

    # --- Load all DAHITI NetCDF files ---
    nc_files = glob.glob(os.path.join(nc_folder, "**", "*.nc"), recursive=True)
    print(f"Found {len(nc_files)} NetCDF files in {nc_folder}")

    for nc_file in nc_files:
        ds = xr.open_dataset(nc_file)
        df_nc = pd.DataFrame(
            {"time": pd.to_datetime(ds["datetime"].values), "elevation_m": ds["water_level"].values}
        )
        obs_list.append((df_nc, "Historical - DAHITI"))

    return obs_list
