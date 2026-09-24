"""Köppen-Geiger climate classification plotting and analysis.

This module provides tools for:
- Plotting Köppen-Geiger climate zone maps
- Computing climate class statistics for regions
- Generating LaTeX, Markdown, Pickle tables
- Analyzing climate zone changes over time

Constants
---------
KOPPEN_CLASSES : list
    30 Köppen-Geiger climate class codes
KOPPEN_RGB_COLORS : np.ndarray
    RGB colors for each climate class (0-1 normalized)
KOPPEN_DESCRIPTION : dict
    Mapping of class codes to full descriptions
"""

# Path library
import gc

import re
from pathlib import Path

# Cartopy
import cartopy.crs as ccrs

# Geospatial
import fiona
import matplotlib.pyplot as plt

# Numerical / plotting
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from cartopy.feature import BORDERS, COASTLINE, LAKES, OCEAN, RIVERS, ShapelyFeature
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import shape

# ==============================================================================
# Koppen-Geiger
# ==============================================================================
KOPPEN_CLASSES = [
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

KOPPEN_RGB_COLORS = (
    np.array(
        [
            [0, 0, 255],
            [0, 120, 255],
            [70, 170, 250],
            [255, 0, 0],
            [255, 150, 150],
            [245, 165, 0],
            [255, 220, 100],
            [255, 255, 0],
            [200, 200, 0],
            [150, 150, 0],
            [150, 255, 150],
            [100, 200, 100],
            [50, 150, 50],
            [200, 255, 80],
            [100, 255, 80],
            [50, 200, 0],
            [255, 0, 255],
            [200, 0, 200],
            [150, 50, 150],
            [150, 100, 150],
            [170, 175, 255],
            [90, 120, 220],
            [75, 80, 180],
            [50, 0, 135],
            [0, 255, 255],
            [55, 200, 255],
            [0, 125, 125],
            [0, 70, 95],
            [178, 178, 178],
            [102, 102, 102],
        ],
        dtype=float,
    )
    / 255
)

KOPPEN_DESCRIPTION = {
    "Af": "Tropical rainforest",
    "Am": "Tropical monsoon",
    "Aw": "Tropical savanna",
    "BWh": "Hot desert",
    "BWk": "Cold desert",
    "BSh": "Hot steppe",
    "BSk": "Cold steppe",
    "Csa": "Mediterranean, hot summer",
    "Csb": "Mediterranean, warm summer",
    "Csc": "Mediterranean, cold summer",
    "Cwa": "Temperate, dry winter, hot summer",
    "Cwb": "Temperate, dry winter, warm summer",
    "Cwc": "Temperate, dry winter, cold summer",
    "Cfa": "Temperate, no dry season, hot summer",
    "Cfb": "Temperate, no dry season, warm summer",
    "Cfc": "Temperate, no dry season, cold summer",
    "Dsa": "Snow, dry summer, hot summer",
    "Dsb": "Snow, dry summer, warm summer",
    "Dsc": "Snow, dry summer, cold summer",
    "Dsd": "Snow, dry summer, very cold summer",
    "Dwa": "Snow, dry winter, hot summer",
    "Dwb": "Snow, dry winter, warm summer",
    "Dwc": "Snow, dry winter, cold summer",
    "Dwd": "Snow, dry winter, very cold winter",
    "Dfa": "Snow, no dry season, hot summer",
    "Dfb": "Snow, no dry season, warm summer",
    "Dfc": "Snow, no dry season, cold summer",
    "Dfd": "Snow, no dry season, very cold winter",
    "ET": "Tundra",
    "EF": "Ice cap",
}

FALLBACK_EXTENT = (54, 33, 82, 53)


def analyse_koppen_geiger(
    path_to_file,
    shapefiles=None,
    koppen_description=None,
    plot_map=True,
    plot_hist=True,
    generate_table=True,
    save_dir=None,
    show_plot=False,
    return_fig=False,
):
    """High-level wrapper: compute counts, plot raster map, histograms, and generate tables.

    Returns:
    -------
    fig, ax : matplotlib objects (or None)
    df_percent : DataFrame of class percentages
    top_df : processed top-N DataFrame
    """
    # --- Compute extent once ---
    extent = get_combined_extent(shapefiles) if shapefiles else None

    # --- Compute counts ---
    df_counts, df_percent = compute_koppen_class_counts(
        path_to_file, shapefiles=shapefiles, extent=extent
    )

    fig, ax = (None, None)
    top_df = None

    # extract range and scenario from file path
    year_range, scenario = extract_scenario_and_year(path_to_file)
    year_range_str = year_range.replace("_", "-")
    title = f"Köppen-Geiger Map ({year_range_str}"
    if scenario:
        title += f", {scenario}"
    title += ")"

    suffix = f"{year_range}"
    if scenario:
        suffix += f"_{scenario}"

    caption = "Percentage coverage of dominant Köppen-Geiger climate classes " f"({year_range_str}"
    if scenario:
        caption += f", {scenario}"
    caption += ")"

    label = f"tab:koppen_geiger_{year_range}"
    if scenario:
        label += f"_{scenario}"

    save_dir = Path(save_dir or ".")
    analysis_dir = Path(save_dir or ".") / suffix
    analysis_dir.mkdir(parents=True, exist_ok=True)

    analysis_dir / f"koppen_map_{suffix}.png"
    analysis_dir / f"koppen_hist_{suffix}.png"
    tex_file = analysis_dir / f"koppen_table_{suffix}.tex"
    md_file = analysis_dir / f"koppen_table_{suffix}.md"
    pkl_file = analysis_dir / f"koppen_table_{suffix}.pkl"

    # --- Map ---
    if plot_map:
        fig, ax = plot_koppen_geiger_map(
            path_to_file,
            shapefiles=shapefiles,
            extent=extent,
            title=title,
            savefig=True,
            save_dir=analysis_dir,
            filename=f"koppen_map_{suffix}.png",
            show_plot=show_plot,
        )
        if not return_fig and not show_plot:
            plt.close(fig)
            fig, ax = None, None  # Clear references

    # --- Histograms ---
    if plot_hist:
        plot_koppen_histograms(
            df_percent,
            shapefiles=shapefiles,
            save_dir=analysis_dir,
            prefix=suffix,
            show_plot=show_plot,
            title_prefix=f"Köppen-Geiger Class Distribution ({year_range_str}"
            + (f", {scenario}" if scenario else "")
            + ")",
        )

        # prevent memory leak issues?
        gc.collect()

    # --- Table ---
    if generate_table:
        top_df = generate_koppen_tables(
            df_percent,
            koppen_description=koppen_description,
            save_tex=tex_file,
            save_md=md_file,
            save_pkl=pkl_file,
            caption=caption,
            label=label,
        )

    # --- Return ---
    if return_fig:
        return fig, ax, df_percent, top_df
    if fig is not None:
        plt.close(fig)
    gc.collect()
    return df_percent, top_df


def plot_koppen_geiger_map(
    path_to_file,
    shapefiles=None,
    show_plot=True,
    show_legend=True,
    show_title=True,
    savefig=False,
    save_dir=None,
    class_names=None,
    rgb_colors=None,
    extent=None,
    filename=None,
    title=None,
):
    """Plot Köppen-Geiger raster map with optional shapefiles.
    Returns fig, ax.
    """
    path_to_file = Path(path_to_file)

    # Compute extent if not provided
    if extent is None and shapefiles:
        extent = get_combined_extent(shapefiles, padding=1.0)
    elif extent is None:
        # fallback extent
        extent = FALLBACK_EXTENT
    lon_min, lat_min, lon_max, lat_max = extent

    # --- Load raster ---
    import rasterio

    with rasterio.open(path_to_file) as src:
        window = src.window(
            lon_min, lat_min, lon_max, lat_max
        )  # don't need to load the whole thing
        data = src.read(1, window=window)
        # data = src.read(1)

    # --- Defaults ---
    class_names = class_names or KOPPEN_CLASSES
    if rgb_colors is None:
        rgb_colors = KOPPEN_RGB_COLORS

    cmap = ListedColormap(np.array(rgb_colors))
    norm = BoundaryNorm(np.arange(0.5, len(class_names) + 0.5, 1), cmap.N)

    # --- Figure ---
    fig = plt.figure(figsize=(10, 10), dpi=300)
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    ax.imshow(
        data,
        cmap=cmap,
        norm=norm,
        origin="upper",
        extent=[lon_min, lon_max, lat_min, lat_max],
        transform=ccrs.PlateCarree(),
    )

    # --- Features ---
    ax.add_feature(COASTLINE)
    ax.add_feature(BORDERS, linestyle=":")
    ax.add_feature(LAKES, facecolor="lightblue", edgecolor="blue")
    ax.add_feature(RIVERS, edgecolor="blue")
    ax.add_feature(OCEAN, facecolor="blue")

    # --- Shapefiles ---
    legend_handles = [
        Patch(facecolor=rgb_colors[i], edgecolor="k", label=f"{i+1}: {name}")
        for i, name in enumerate(class_names)
    ]

    if shapefiles:
        for label, cfg in shapefiles.items():
            # Load shapefile geometries with fiona
            with fiona.open(cfg["path"]) as src:
                geoms = [shape(feat["geometry"]) for feat in src]

            # Create Cartopy feature
            feature = ShapelyFeature(
                geoms,
                ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=cfg.get("edgecolor", "black"),
                linewidth=cfg.get("linewidth", 1),
                linestyle=cfg.get("linestyle", "-"),
            )
            ax.add_feature(feature)

            # Add to legend
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    color=cfg.get("edgecolor", "black"),
                    linewidth=2,
                    label=label,
                    linestyle=cfg.get("linestyle", "-"),
                )
            )

    if show_legend:
        ax.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)

    if show_title:
        if title is None:
            ax.set_title(f"Köppen-Geiger Map ({path_to_file.stem})", fontsize=14)
        else:
            ax.set_title(title, fontsize=14)

    plt.tight_layout()

    if savefig:
        fname = filename or f"{path_to_file.stem}.png"
        save_path = Path(save_dir or ".") / fname
        plt.savefig(save_path, dpi=300, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax


def plot_koppen_histograms(
    df_percent,
    class_names=None,
    shapefiles=None,
    show_plot=True,
    save_dir=None,
    prefix="",
    title_prefix="",
):
    """Plot percentage bar charts for map and shapefiles."""
    class_names = class_names or df_percent.index.tolist()
    rgb_colors = KOPPEN_RGB_COLORS

    def counts_to_percent(counts):
        total = np.sum(counts)
        if total == 0:
            return np.zeros_like(counts, dtype=float)
        return [c / total * 100 for c in counts]

    # Map extent (first column)
    map_col = df_percent.columns[0]
    fig = plt.figure(figsize=(12, 4))
    try:
        plt.bar(class_names, counts_to_percent(df_percent[map_col]), color=rgb_colors)
        plt.xticks(rotation=90)
        plt.ylabel("Percentage (%)")
        title_str = (
            f"{title_prefix} ({map_col})"
            if title_prefix
            else f"Köppen-Geiger Class Distribution ({map_col})"
        )
        plt.title(title_str)
        plt.grid(axis="y", linestyle="--", alpha=0.5)
        if save_dir:
            plt.savefig(Path(save_dir) / f"{map_col}_hist.png", dpi=300, bbox_inches="tight")
        if show_plot:
            plt.show()
    finally:  # fix memory leak issues
        plt.close(fig)
        del fig

    # Remaining columns (shapefiles)
    for col in df_percent.columns[1:]:
        fig = plt.figure(figsize=(12, 4))
        try:
            plt.bar(class_names, counts_to_percent(df_percent[col]), color=rgb_colors)
            plt.xticks(rotation=90)
            plt.ylabel("Percentage (%)")
            title_str = (
                f"{title_prefix} ({col})"
                if title_prefix
                else f"Köppen-Geiger Class Distribution ({col})"
            )
            plt.title(title_str)
            plt.grid(axis="y", linestyle="--", alpha=0.5)
            if save_dir:
                plt.savefig(
                    Path(save_dir) / f"koppen_hist_{prefix}_{col}.png", dpi=300, bbox_inches="tight"
                )
            if show_plot:
                plt.show()
        finally:  # fix memory leak issues
            plt.close(fig)
            del fig

        # memory leak issues
        gc.collect()


def plot_climate_class_timeseries(
    topdf_all,
    climate_class,
    column_name="Plotted Area",
    hist_ref_period="1991_2020",
    plot_period="year_middle",
):
    """Plot HIST and SSP lines for a given climate class over time.

    Parameters
    ----------
    topdf_all : pd.DataFrame
        Concatenated topdf_all DataFrame with columns:
        - climate_class
        - period
        - ssp
        - year_start
        - Plotted Area
        - description
    climate_class : str
        Köppen-Geiger climate class to plot, e.g., "Cfb".
    hist_ref_period : str, optional
        Period row in HIST data to use as reference for SSPs, default "1991_2020".

    Returns:
    -------
    fig, ax : matplotlib Figure and Axes
    """
    # HIST dataframe
    hist_df = topdf_all[topdf_all["ssp"] == "HIST"].copy()

    # future SSPs
    ssps = topdf_all["ssp"].unique()
    ssps = [s for s in ssps if s != "HIST"]
    future_df = topdf_all[topdf_all["ssp"].isin(ssps)].copy()

    # HIST reference row
    hist_ref = hist_df[hist_df["period"] == hist_ref_period].copy()

    combined_ssp = []
    for ssp in ssps:
        df_ssp = future_df[future_df["ssp"] == ssp].copy()
        # add HIST reference
        hist_point = hist_ref.copy()
        hist_point["ssp"] = ssp
        df_ssp = pd.concat([hist_point, df_ssp], ignore_index=True)
        combined_ssp.append(df_ssp)

    # all SSP lines combined
    ssp_plot_df = pd.concat(combined_ssp, ignore_index=True)
    ssp_plot_df = ssp_plot_df.sort_values(["ssp", "year_start"])

    # Grab description
    desc = topdf_all.loc[topdf_all["climate_class"] == climate_class, "description"].iloc[0]

    # Plot
    fig, ax = plt.subplots(figsize=(8, 4))

    # HIST line
    hist_line = hist_df[hist_df["climate_class"] == climate_class].sort_values("year_start")
    ax.plot(
        hist_line[plot_period],
        hist_line[column_name],
        color="black",
        marker="o",
        label="HIST",
        zorder=20,
    )

    # SSP lines
    for ssp, g in ssp_plot_df[ssp_plot_df["climate_class"] == climate_class].groupby("ssp"):
        ax.plot(g[plot_period], g[column_name], marker="o", label=ssp)

    ax.set_xlabel("Year")
    ax.set_ylabel("Area (%)")
    ax.set_title(f"{climate_class} ({desc}) area fraction over time for {column_name}")
    ax.legend(title="Scenario")
    ax.grid(linestyle="--", alpha=0.5)
    plt.tight_layout()

    return fig, ax


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
    class_names = class_names or KOPPEN_CLASSES

    df_counts = pd.DataFrame(index=class_names)
    # df_counts["Plotted Area"] = [np.sum(flat_data == i+1) for i in range(len(class_names))]

    with rasterio.open(path_to_file) as src:
        nodata = src.nodata  # ALWAYS get nodata, it is the value the map uses as NoData (sea etc)

    if extent:
        lon_min, lat_min, lon_max, lat_max = extent

        with rasterio.open(path_to_file) as src:  # read only the extent
            window = src.window(lon_min, lat_min, lon_max, lat_max)
            data = src.read(1, window=window)

        flat_data = data.flatten()  # remove the NoData
        if nodata is not None:
            flat_data = flat_data[flat_data != nodata]

        df_counts["Plotted Area"] = [np.sum(flat_data == i + 1) for i in range(len(class_names))]

        # OPTIMIZATION: delete data
        del data, flat_data
        gc.collect()

        # --- Shapefile counts ---
    if shapefiles:
        for label, cfg in shapefiles.items():
            with fiona.open(cfg["path"]) as shp:  # open the shapefiles
                geoms = [shape(feat["geometry"]) for feat in shp]  # list of Shapely geometries

            with rasterio.open(path_to_file) as src:  # open the koppen-geiger map
                masked, _ = rasterio.mask.mask(
                    src, geoms, crop=True
                )  # keep only the pixels in the shapefile

            masked_flat = masked[0].flatten()
            if nodata is not None:
                masked_flat = masked_flat[masked_flat != nodata]  # removes NoData

            df_counts[label] = [
                np.sum(masked_flat == i + 1) for i in range(len(class_names))
            ]  # count number of cells for each climate class

            del masked, masked_flat, geoms  # fix memory leak issues
            gc.collect()

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
    def period_to_year_start(p):
        return int(p.split("_")[0])

    def period_to_year_middle(p):
        start, end = p.split("_")
        return (int(start) + int(end)) // 2

    def period_to_year_end(p):
        return int(p.split("_")[1])

    topdf_all["year_start"] = topdf_all["period"].apply(period_to_year_start)
    topdf_all["year_middle"] = topdf_all["period"].apply(period_to_year_middle)
    topdf_all["year_end"] = topdf_all["period"].apply(period_to_year_end)

    # Sort
    topdf_all.sort_values(by=["year_start", "ssp", "climate_class"], inplace=True)

    # Add description
    topdf_all["description"] = topdf_all["climate_class"].map(KOPPEN_DESCRIPTION)

    return topdf_all
