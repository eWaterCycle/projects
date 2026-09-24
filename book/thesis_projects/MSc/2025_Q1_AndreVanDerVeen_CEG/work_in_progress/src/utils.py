"""Utility functions for hydrological modeling and geospatial data processing
within the eWaterCycle framework. Includes functions for:

- Catchment area calculation
- Unit conversion
- INI file comparison
- GRDC metadata table generation
"""

import configparser
import re
from collections.abc import Sequence
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Union

import fiona
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from pyproj import Geod
from shapely.geometry import shape

from src.constants import KOPPEN_DESCRIPTION
from src.paths import INI_COMPARISON, SHAPEFILES


def catchment_area_from_shapefile(shape_name, ellps="WGS84"):
    """Compute the area (in m²) of the first polygon in a shapefile.

    Parameters
    ----------
    shapefile_path : str
        Path to the shapefile (.shp)
    ellps : str, optional
        Ellipsoid for area calculation (default: WGS84)

    Returns:
    -------
    float
        Absolute area of the polygon in square meters
    """
    # Load polygon
    shapefile = SHAPEFILES / shape_name / f"{shape_name}.shp"

    with fiona.open(shapefile) as src:
        poly = shape(src[0]["geometry"])

    # Define ellipsoid
    geod = Geod(ellps=ellps)

    # Compute area and perimeter
    area, _ = geod.geometry_area_perimeter(poly)

    return abs(area)


def mmday_to_m3s(model_output: pd.Series, shape_name: str) -> pd.Series:
    """Convert HBV model output from mm/day to m³/s using catchment area.

    Parameters
    ----------
    model_output : pd.Series
        Modelled discharge in mm/day.
    shape_name : str
        Name of the shapefile defining the catchment. Used to compute catchment area.

    Returns:
    -------
    pd.Series
        Discharge converted to cubic meters per second (m³/s).

    Notes:
    -----
    Catchment area is obtained using `catchment_area_from_shapefile`.
    """
    # Compute catchment area in m²
    area_m2 = _get_catchment_area(shape_name)  # default returns m²
    # Conversion: 1 mm/day over 1 m² = 1e-3 m³/day
    # Then divide by 86400 s/day to get m³/s
    conversion_factor = 1e-3 / 86400 * area_m2
    model_output_m3s = model_output * conversion_factor
    return model_output_m3s


@cache
def _get_catchment_area(shape_name: str) -> float:
    """Cached helper to retrieve catchment area to avoid repeated computations."""
    return catchment_area_from_shapefile(shape_name)


def get_integer_multiple_bounds(
    shapefiles: Union[str, Path, Sequence[Union[str, Path]]],
    multiple: int = 3,
):
    """Get the bounding box of one or more shapefiles, expanded to the nearest integer
    multiples.
    Parameters
    ----------
    shapefiles : str, Path, or list of str/Path
        Path(s) to the shapefile(s).
    multiple : int, optional
        The multiple to which the bounds should be expanded (default is 3).

    Returns:
    -------
    tuple
        A tuple containing (lon_min, lat_min, lon_max, lat_max) expanded to the nearest multiples.
    """
    # make list
    if isinstance(shapefiles, (str, Path)):
        shapefiles = [shapefiles]

    # --- collect all bounds ---
    min_xs, min_ys, max_xs, max_ys = [], [], [], []

    for shp in shapefiles:
        with fiona.open(shp) as src:
            for feat in src:
                geom = shape(feat["geometry"])
                minx, miny, maxx, maxy = geom.bounds
                min_xs.append(minx)
                min_ys.append(miny)
                max_xs.append(maxx)
                max_ys.append(maxy)

    # original bounds
    lon_min = min(min_xs)
    lat_min = min(min_ys)
    lon_max = max(max_xs)
    lat_max = max(max_ys)
    # --- convert to integer bounds ---
    lon_min_i = int(np.floor(lon_min))
    lat_min_i = int(np.floor(lat_min))
    lon_max_i = int(np.ceil(lon_max))
    lat_max_i = int(np.ceil(lat_max))

    # --- helper to expand to multiple ---
    def expand_to_multiple(min_val, max_val, multiple):
        extent = max_val - min_val
        remainder = extent % multiple
        if remainder != 0:
            max_val += multiple - remainder
        return min_val, max_val

    lon_min_f, lon_max_f = expand_to_multiple(lon_min_i, lon_max_i, multiple)
    lat_min_f, lat_max_f = expand_to_multiple(lat_min_i, lat_max_i, multiple)

    return lon_min_f, lat_min_f, lon_max_f, lat_max_f


def _load_ini(path):
    """Load ini file into a dictionary-like structure."""
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # preserve case
    cp.read(path)
    return cp


def _generate_comparison_filename(file1, file2):
    """Generate a filename for the comparison output based on the two INI files being compared."""
    # use stem names of INI files
    name1 = Path(file1).stem
    name2 = Path(file2).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name1}_vs_{name2}_{timestamp}.txt"
    return INI_COMPARISON / filename


def compare_inis(file1, file2):  # , save_file=None):
    """Compare two PCR-GLOBWB2 INI files and report differences.

    Parameters
    ----------
    file1 : str or Path
        Path to the first INI file.
    file2 : str or Path
        Path to the second INI file.

    Returns:
    -------
    None
        Differences are printed to the console and also saved to a file
        named "diff_file1_file2.txt" in the current directory.

    Notes:
    -----
    Output file is automatically named based on the two input filenames.
    """
    cp1 = _load_ini(file1)
    cp2 = _load_ini(file2)

    output = []

    output.append(f"\nComparing:\n  A = {file1}\n  B = {file2}\n")

    # Compare sections
    sections1 = set(cp1.sections())
    sections2 = set(cp2.sections())

    missing_in_B = sections1 - sections2
    missing_in_A = sections2 - sections1

    if missing_in_B:
        output.append("Sections present in A but missing in B:")
        for s in sorted(missing_in_B):
            output.append(f"  - {s}")

    if missing_in_A:
        output.append("Sections present in B but missing in A:")
        for s in sorted(missing_in_A):
            output.append(f"  - {s}")

    # Compare keys for shared sections
    shared_sections = sections1 & sections2
    for section in sorted(shared_sections):
        keys1 = set(cp1[section].keys())
        keys2 = set(cp2[section].keys())

        missing_keys_in_B = keys1 - keys2
        missing_keys_in_A = keys2 - keys1

        if missing_keys_in_B or missing_keys_in_A:
            output.append(f"\n[Section: {section}]")

        if missing_keys_in_B:
            output.append("  Keys present in A but missing in B:")
            for k in sorted(missing_keys_in_B):
                output.append(f"    - {k}")

        if missing_keys_in_A:
            output.append("  Keys present in B but missing in A:")
            for k in sorted(missing_keys_in_A):
                output.append(f"    - {k}")

        # Compare values for keys present in both
        for key in sorted(keys1 & keys2):
            v1 = cp1[section][key].strip()
            v2 = cp2[section][key].strip()
            if v1 != v2:
                output.append(f"\n  Value differs for: {section}.{key}")
                output.append(f"    A: {v1}")
                output.append(f"    B: {v2}")

    # Print to console
    # print("\n".join(output))

    INI_COMPARISON.mkdir(parents=True, exist_ok=True)

    auto_filename = _generate_comparison_filename(file1, file2)

    # Optionally save to file
    with open(auto_filename, "w") as f:
        f.write("\n".join(output))


# =====================================================
# GRDC READER TO LATEX TABLE
# =====================================================


def _metadata_patterns() -> dict:
    """Return a dictionary of regex patterns to extract metadata from GRDC station files."""
    return {
        "GRDC-No.": r"GRDC-No\.\s*:\s*(\d+)",
        "Station": r"Station\s*:\s*(.+)",
        "Latitude (DD)": r"Latitude \(DD\)\s*:\s*([-\d\.]+)",
        "Longitude (DD)": r"Longitude \(DD\)\s*:\s*([-\d\.]+)",
        "Catchment area (km²)": r"Catchment area \(km²\)\s*:\s*([-\d\.]+)",
        "Time series": r"Time series\s*:\s*(.+)",
        "Data lines": r"Data lines\s*:\s*(\d+)",
        "Data Set Content": r"Data Set Content\s*:\s*(.+)",
    }


def _read_text_file(path: Path) -> str:
    """Read a text file with UTF-8 encoding; fallback to Latin-1 if UTF-8 fails."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin1")


def _extract_metadata(content: str, patterns: dict) -> dict:
    """Extract metadata from a text string using provided regex patterns.

    Returns a dictionary with keys corresponding to pattern names.
    """
    metadata = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        metadata[key] = match.group(1).strip() if match else None
    return metadata


def _determine_frequency(content: str | None) -> str:
    """Determine time series frequency from content string ('Daily', 'Monthly', or '-')"""
    if not content:
        return "-"
    content = content.upper()
    if "DAILY" in content:
        return "Daily"
    if "MONTHLY" in content:
        return "Monthly"
    return "-"


def _collect_metadata(folder: Path, patterns: dict) -> pd.DataFrame:
    """Collect metadata from all .txt files in a folder and return as a DataFrame."""
    records = []

    for txt_file in folder.glob("*.txt"):
        text = _read_text_file(txt_file)
        metadata = _extract_metadata(text, patterns)
        metadata["Frequency"] = _determine_frequency(metadata.get("Data Set Content"))
        records.append(metadata)

    return pd.DataFrame(records)


def _convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric columns (Catchment area, Data lines) to proper types and formatted strings."""
    df["Data lines"] = df["Data lines"].astype("Int64")

    df["Catchment area (km²)"] = df["Catchment area (km²)"].apply(
        lambda x: int(float(x)) if pd.notna(x) else pd.NA
    )

    df["Data lines"] = df["Data lines"].map(lambda x: "-" if pd.isna(x) or x == 0 else f"{x:,}")

    return df


def _round_coordinates(df: pd.DataFrame, decimals: int = 2) -> pd.DataFrame:
    """Round latitude and longitude to specified decimals and convert to string format."""
    for col in ["Latitude (DD)", "Longitude (DD)"]:
        df[col] = (
            df[col]
            .astype(float)
            .round(decimals)
            .map(lambda x: f"{x:.{decimals}f}" if pd.notna(x) else "-")
        )
    return df


def _copy_nonempty_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """Filter DataFrame to include only stations with non-empty time series."""
    numeric = pd.to_numeric(
        df["Data lines"].str.replace(",", "").replace("-", ""),
        errors="coerce",
    )
    return df[numeric > 0].copy()


def _select_and_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select relevant columns and rename them for GRDC metadata table."""
    columns = {
        "GRDC-No.": "GRDC No.",
        "Station": "Station",
        "Latitude (DD)": "Lat (°N)",
        "Longitude (DD)": "Lon (°E)",
        "Catchment area (km²)": "Catchment (km²)",
        "Time series": "Time Series",
        "Data lines": "Data Lines",
        "Frequency": "Freq",
    }

    return df[list(columns.keys())].rename(columns=columns)


def _sanitize_latex(value):
    """Escape LaTeX special characters in a string (e.g., _, &, %)."""
    if isinstance(value, str):
        return value.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")
    return value


def _sanitize_dataframe_for_latex(df: pd.DataFrame) -> pd.DataFrame:
    """Apply LaTeX sanitization to all string entries in the DataFrame."""
    return df.map(_sanitize_latex)


def _export_to_latex(
    df: pd.DataFrame,
    output_path: Path,
    caption: str,
    label: str,
    column_format: str,
):
    """Export a DataFrame to a LaTeX file with longtable, caption, and label."""
    latex = df.to_latex(
        index=False,
        caption=caption,
        label=label,
        longtable=True,
        escape=False,
        column_format=column_format,
    )
    output_path.write_text(latex, encoding="utf-8")


def _simplify_daily_timeseries(ts):
    """Simplify daily time series string to 'start_year - end_year' format."""
    if pd.isna(ts):
        return "-"
    match = re.findall(r"(\d{4})", ts)
    if match and len(match) >= 2:
        return f"{match[0]} - {match[-1]}"
    return ts


def _split_by_frequency(df: pd.DataFrame):
    """Split metadata DataFrame into daily and monthly DataFrames and clean columns."""
    df_daily = df[df["Freq"] == "Daily"].copy()
    df_monthly = df[df["Freq"] == "Monthly"].copy()

    # Daily: simplify time series, remove Freq
    if not df_daily.empty:
        df_daily["Time Series"] = df_daily["Time Series"].apply(_simplify_daily_timeseries)
        df_daily.drop(columns=["Freq"], inplace=True)

    # Monthly: just remove Freq
    if not df_monthly.empty:
        df_monthly.drop(columns=["Freq"], inplace=True)

    return df_daily, df_monthly


def _export_daily_monthly_tables(
    df_daily: pd.DataFrame,
    df_monthly: pd.DataFrame,
    export_dir: Path,
    base_filename: str,
):
    """Export daily and monthly metadata DataFrames to separate LaTeX tables."""
    if not df_monthly.empty:
        latex_monthly = df_monthly.to_latex(
            index=False,
            caption="Selected GRDC Station Metadata (Monthly)",
            label="tab:grdc_selected_metadata_monthly",
            longtable=True,
            escape=False,
            column_format="lp{4.3cm}llrlr",
        )
        (export_dir / f"{base_filename}_monthly.tex").write_text(latex_monthly, encoding="utf-8")

    if not df_daily.empty:
        latex_daily = df_daily.to_latex(
            index=False,
            caption="Selected GRDC Station Metadata (Daily)",
            label="tab:grdc_selected_metadata_daily",
            longtable=True,
            escape=False,
            column_format="lp{4.3cm}llrlr",
        )
        (export_dir / f"{base_filename}_daily.tex").write_text(latex_daily, encoding="utf-8")


def build_grdc_metadata_table(
    folder_path: Path,
    export_dir: Path | None = None,
    split_daily_monthly: bool = True,
    base_filename: str = "grdc_selected_metadata",
) -> pd.DataFrame:
    """Build cleaned GRDC station metadata tables from raw text files.

    This function reads all GRDC station .txt files in a folder, extracts metadata,
    formats numeric and coordinate columns, filters non-empty time series, sanitizes
    strings for LaTeX, and optionally exports separate daily and monthly LaTeX tables.

    Parameters
    ----------
    folder_path : Path
        Directory containing GRDC station .txt files.
    export_dir : Path, optional
        Directory where LaTeX tables will be written.
    split_daily_monthly : bool, default True
        If True, exports separate daily and monthly tables.
    base_filename : str, default "grdc_selected_metadata"
        Base name for exported LaTeX files (without suffix).

    Returns:
    -------
    pd.DataFrame
        Cleaned metadata table for all stations.
    """
    patterns = _metadata_patterns()

    df = _collect_metadata(folder_path, patterns)
    df = _convert_numeric_columns(df)
    df = _round_coordinates(df)
    df = _copy_nonempty_timeseries(df)
    df = _select_and_rename_columns(df)
    df = _sanitize_dataframe_for_latex(df)

    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)

        if split_daily_monthly:
            df_daily, df_monthly = _split_by_frequency(df)
            _export_daily_monthly_tables(
                df_daily,
                df_monthly,
                export_dir,
                base_filename,
            )

    return df


def compute_koppen_class_counts(path_to_file, shapefiles=None, class_names=None, extent=None):
    """Compute pixel counts for Köppen-Geiger classes for raster and optional shapefiles.

    Parameters
    ----------
    path_to_file : str or Path
        Path to Köppen-Geiger raster.
    shapefiles : dict, optional
        Dictionary of shapefile configurations:
            {"Label": {"path": Path(...), "edgecolor": "...", "linewidth": ...}}
    class_names : list of str, optional
        List of Köppen class names. Defaults to 30 standard classes.

    Returns:
    -------
    df_counts : pandas.DataFrame
        Raw counts for raster and shapefiles.
    df_percent : pandas.DataFrame
        Percent coverage of each class.
    """
    path_to_file = Path(path_to_file)
    class_names = class_names or [
        "Af",
        "Am",
        "Aw",
        "BWh",
        "BWk",
        "BSh",
        "BSk",
        "Csa",
        "Csb",
        "Csc",
        "Cwa",
        "Cwb",
        "Cwc",
        "Cfa",
        "Cfb",
        "Cfc",
        "Dsa",
        "Dsb",
        "Dsc",
        "Dsd",
        "Dwa",
        "Dwb",
        "Dwc",
        "Dwd",
        "Dfa",
        "Dfb",
        "Dfc",
        "Dfd",
        "ET",
        "EF",
    ]

    with rasterio.open(path_to_file) as src:
        nodata = src.nodata  # ALWAYS get nodata

        data = src.read(1)

        if extent is not None:
            lon_min, lat_min, lon_max, lat_max = extent
            # Convert lon/lat to row/col indices
            row_start, col_start = src.index(lon_min, lat_max)  # upper-left
            row_stop, col_stop = src.index(lon_max, lat_min)  # lower-right

            # Ensure indices are within raster bounds
            row_start = max(0, row_start)
            row_stop = min(src.height, row_stop)
            col_start = max(0, col_start)
            col_stop = min(src.width, col_stop)

            # Slice the array
            data = data[row_start:row_stop, col_start:col_stop]
    flat_data = data.flatten()
    if nodata is not None:
        flat_data = flat_data[flat_data != nodata]

    df_counts = pd.DataFrame(index=class_names)
    df_counts["Plotted Area"] = [np.sum(flat_data == i + 1) for i in range(len(class_names))]

    # --- Shapefile counts ---
    if shapefiles:
        for label, cfg in shapefiles.items():
            with fiona.open(cfg["path"]) as shp:
                geoms = [shape(feat["geometry"]) for feat in shp]  # list of Shapely geometries

            with rasterio.open(path_to_file) as src:
                masked, _ = rasterio.mask.mask(src, geoms, crop=True)

            masked_flat = masked[0].flatten()
            if nodata is not None:
                masked_flat = masked_flat[masked_flat != nodata]

            df_counts[label] = [np.sum(masked_flat == i + 1) for i in range(len(class_names))]
    # --- Percentages ---
    df_percent = df_counts.div(df_counts.sum(axis=0), axis=1) * 100

    return df_counts, df_percent


def generate_koppen_tables(
    df_percent,
    koppen_description=None,
    top_n=10,
    save_tex=None,
    save_md=None,
    save_pkl=None,
    caption=None,
    label=None,
):
    """Produce top-N class table with 'Other', optionally save as LaTeX / Markdown.

    Parameters
    ----------
    df_percent : pandas.DataFrame
        Percent coverage for classes.
    koppen_description : dict, optional
        Mapping class_name -> description
    top_n : int, default 10
        Number of top classes to keep, others grouped as "Other".
    save_tex : str or Path, optional
        Path to save LaTeX table.
    save_md : str or Path, optional
        Path to save Markdown table.

    Returns:
    -------
    top_df : pandas.DataFrame
        Processed top-N table with percentages.
    """
    df_subset = df_percent.drop(columns=["total_raster"], errors="ignore")
    df_sorted = df_subset.sort_values(df_subset.columns[0], ascending=False)  # sort by first column
    top_df = df_sorted.head(top_n)
    other = df_sorted.iloc[top_n:].sum()
    other.name = "Other"
    top_df = pd.concat([top_df, other.to_frame().T])

    top_df = top_df.copy()

    # Add descriptions
    if koppen_description:
        top_df.insert(
            0,
            "Climate description",
            [koppen_description.get(idx, "Other classes") for idx in top_df.index],
        )

    # Save LaTeX
    if save_tex:
        latex_table = top_df.to_latex(
            float_format="%.1f",
            index=True,
            caption=caption or "Percentage coverage of dominant Köppen-Geiger climate classes",
            label=label or "tab:koppen_geiger_percent",
            column_format="ll" + "r" * len(top_df.columns[1:]),
            bold_rows=True,
            escape=False,
        )
        with open(save_tex, "w") as f:
            f.write(latex_table)

    # --- Save Markdown ---
    if save_md:
        top_df = top_df.reset_index()  # move index into a column
        top_df.rename(columns={"index": "Climate code"}, inplace=True)

        # Identify numeric columns and round
        numeric_cols = top_df.select_dtypes(include="number").columns
        top_df[numeric_cols] = top_df[numeric_cols].round(2)  # 2 decimal places

        # --- Add (%) to numeric column headers ---
        new_columns = []
        for col in top_df.columns:
            if col in numeric_cols:
                new_columns.append(f"{col} (%)")
            else:
                new_columns.append(col)
        top_df.columns = new_columns

        try:
            # Use tabulate/pandas Markdown export if available
            markdown_table = top_df.to_markdown(
                index=False,
                tablefmt="pipe",
                numalign="right",  # right-align numeric columns
            )
        except ImportError:
            # Fallback if tabulate is missing
            header = "| " + " | ".join(top_df.columns) + " |"
            # Right-align numeric columns using :---:
            separator = (
                "| "
                + " | ".join(
                    "---:" if col in [f"{c} (%)" for c in numeric_cols] else "---"
                    for col in top_df.columns
                )
                + " |"
            )
            rows = ["| " + " | ".join(map(str, row)) + " |" for row in top_df.values]
            markdown_table = "\n".join([header, separator] + rows)

        # Save to file
        with open(save_md, "w", encoding="utf-8") as f:
            f.write(markdown_table)

    if save_pkl:
        df_percent.to_pickle(save_pkl)

    return top_df


def get_combined_extent(shapefiles, padding=1.0):
    """Return combined lon/lat bounds of multiple shapefiles with optional padding.

    Parameters
    ----------
    shapefiles : dict
        {"label": {"path": Path, ...}, ...}
    padding : float
        Degrees to extend bounds

    Returns:
    -------
    lon_min, lat_min, lon_max, lat_max : float
    """
    if not shapefiles:
        # fallback extent
        return 54, 33, 82, 53

    lon_min, lat_min = float("inf"), float("inf")
    lon_max, lat_max = float("-inf"), float("-inf")

    for cfg in shapefiles.values():
        with fiona.open(cfg["path"]) as src:
            for feat in src:
                geom = shape(feat["geometry"])
                bx, by, Bx, By = geom.bounds
                lon_min = min(lon_min, bx)
                lat_min = min(lat_min, by)
                lon_max = max(lon_max, Bx)
                lat_max = max(lat_max, By)

    return lon_min - padding, lat_min - padding, lon_max + padding, lat_max + padding


def extract_scenario_and_year(path):
    """Extract year range and scenario (if any) from raster path."""
    parts = Path(path).parts
    # Year folder is assumed to be immediately under KOPPEN_GEIGER
    try:
        year_range = next(p for p in parts if re.match(r"\d{4}_\d{4}", p))
    except StopIteration:
        year_range = "unknown_year"
    # Scenario is next folder after year_range (if exists)
    year_index = parts.index(year_range)
    scenario = parts[year_index + 1] if (year_index + 1 < len(parts) - 1) else None
    return year_range, scenario


def load_koppen_pickles_from_folder(pkl_folder):
    """Load all Köppen-Geiger pickle outputs from a folder, add period, SSP, year, and description.

    Parameters
    ----------
    pkl_folder : str or Path
        Path to folder containing pickle files for one shapefile.

    Returns:
    -------
    pd.DataFrame
        Concatenated DataFrame with columns:
        - climate_class
        - period
        - ssp
        - year_start
        - year_middle
        - description
        - original percentage columns
    """
    pkl_folder = Path(pkl_folder)
    all_topdfs = []

    # find all .pkl files
    for pkl_file in sorted(pkl_folder.rglob("koppen_table_*.pkl")):
        df = pd.read_pickle(pkl_file)

        # Ensure climate_class is a column
        df = df.copy()
        df["climate_class"] = df.index

        # Extract period and ssp from folder name
        parent_name = pkl_file.parents[0].name

        if "ssp" in parent_name.lower():
            period_part, ssp_part = parent_name.split("_ssp")
            period = period_part
            ssp = f"SSP{ssp_part}"
        else:
            period = parent_name
            ssp = "HIST"

        df["period"] = period
        df["ssp"] = ssp

        all_topdfs.append(df)

    # Concatenate
    topdf_all = pd.concat(all_topdfs, ignore_index=True)

    # Convert period to numeric years
    def period_to_year(p):
        return int(p.split("_")[0])

    def period_to_year_middle(p):
        start, end = p.split("_")
        return (int(start) + int(end)) // 2

    topdf_all["year_start"] = topdf_all["period"].apply(period_to_year)
    topdf_all["year_middle"] = topdf_all["period"].apply(period_to_year_middle)

    # Sort
    topdf_all.sort_values(by=["year_start", "ssp", "climate_class"], inplace=True)

    # Add description
    topdf_all["description"] = topdf_all["climate_class"].map(KOPPEN_DESCRIPTION)

    return topdf_all
