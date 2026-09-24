"""module for plotting functions related to geospatial data and hydrological modeling. Used in thesis project. Might be extended later."""

# Standard library
from pathlib import Path

# Cartopy
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Geospatial
import fiona
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt

# Numerical / plotting
import numpy as np
import pandas as pd
import rasterio
from cartopy.feature import BORDERS, COASTLINE, LAKES, OCEAN, RIVERS, ShapelyFeature
from cartopy.io.shapereader import Reader
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import shape

# Local modules
from src.paths import SHAPEFILES
from src.utils import (
    compute_koppen_class_counts,
    extract_scenario_and_year,
    generate_koppen_tables,
    get_combined_extent,
    get_integer_multiple_bounds,
)


def plot_shapefile_overview(
    shapefile,
    title=None,
    padding=2,
    figsize=(10, 8),
    ax=None,
):
    """Plot a simple overview map of a shapefile (context / locator map).
    automatically extents to integer bounds as used in PCR-GLOBWB2 modelling

    Parameters
    ----------
    shapefile : pathlib.Path or str
        Path to the shapefile (.shp)
    title : str, optional
        Figure title
    padding : float, optional
        Padding (degrees) around shapefile extent
    figsize : tuple, optional
        Figure size if ax is not provided
    ax : cartopy.mpl.geoaxes.GeoAxes, optional
        Existing axes to plot on

    Returns:
    -------
    fig, ax
    """
    # Create figure/axes if needed
    if ax is None:
        fig = plt.figure(figsize=figsize)
        ax = plt.axes(projection=ccrs.PlateCarree())
    else:
        fig = ax.figure

    # Background features
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.COASTLINE, linewidth=1)
    ax.add_feature(cfeature.RIVERS, linewidth=1)
    ax.add_feature(cfeature.LAKES)
    ax.add_feature(cfeature.OCEAN, facecolor="#a2daff", edgecolor="none")
    ax.add_feature(
        cfeature.BORDERS,
        linewidth=0.5,
        linestyle="--",
        alpha=0.3,
    )

    # Plot shapefile geometries
    with fiona.open(shapefile) as src:
        for feat in src:
            geom = shape(feat["geometry"])
            ax.add_geometries(
                [geom],
                crs=ccrs.PlateCarree(),
                facecolor="blue",
                edgecolor="black",
                alpha=0.3,
            )

    lon_min, lat_min, lon_max, lat_max = get_integer_multiple_bounds(
        shapefile,
        multiple=3,
    )

    ax.set_extent(
        [
            lon_min - padding,
            lon_max + padding,
            lat_min - padding,
            lat_max + padding,
        ],
        crs=ccrs.PlateCarree(),
    )

    # Gridlines
    gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.5)
    gl.top_labels = False
    gl.right_labels = False

    # Title
    if title is None:
        stem = Path(shapefile).stem
        title = f"Shapefile overview: {stem}.shp"
    ax.set_title(title)

    return fig, ax


def plot_precipitation_map(
    da,  # xarray DataArray, e.g., pr resampled/averaged
    title="Average Yearly Precipitation (mm/year)",
    vmin=0,
    vmax=2000,
    n_levels=21,
    contour_lines=None,  # custom contour lines labels, e.g. [100,200,...]
    stations=None,  # list of dicts: [{"lat":..., "lon":..., "name":...}, ...]
    figsize=(5, 4),
    dpi=200,
    cmap="YlGnBu",
    savepath=None,
):
    """Plot a filled contour map of precipitation with optional stations and contour lines.

    Parameters
    ----------
    da : xarray.DataArray
        2D precipitation array (lat, lon)
    title : str
        Figure title
    vmin, vmax : float
        Min and max for color scale
    n_levels : int
        Number of contour levels
    contour_lines : list of float
        Specific contour levels to label
    stations : list of dict
        Each dict: {"lat": float, "lon": float, "name": str}
    figsize : tuple
        Figure size
    dpi : int
        Figure DPI
    cmap : str
        Colormap
    savepath : str or Path
        Path to save figure (optional)
    """
    levels = np.linspace(vmin, vmax, n_levels)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, subplot_kw={"projection": ccrs.PlateCarree()})

    # Filled contours
    im = ax.contourf(da["lon"], da["lat"], da, levels=levels, cmap=cmap, extend="both")

    # Contour lines
    cs = ax.contour(
        da["lon"], da["lat"], da, levels=levels, colors="k", linewidths=0.2, linestyles="--"
    )

    # Add contour labels
    if contour_lines is not None:
        ax.clabel(cs, levels=contour_lines, inline=True, fmt="%.0f", fontsize=6)

    # Plot stations
    if stations is not None:
        for s in stations:
            marker = Line2D(
                [s["lon"]],
                [s["lat"]],
                marker="o",
                color="tab:red",
                markersize=5,
                transform=ccrs.PlateCarree(),
                markeredgecolor="white",
                markeredgewidth=1,
            )
            ax.add_line(marker)

            ax.text(
                s["lon"] + 0.3,
                s["lat"],
                s["name"],
                transform=ccrs.PlateCarree(),
                fontsize=7,
                color="tab:red",
                path_effects=[pe.withStroke(linewidth=1, foreground="white")],
            )

    # Map features
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.LAKES, alpha=0.5)
    ax.add_feature(cfeature.OCEAN, facecolor="#a2daff", edgecolor="none", zorder=2)
    ax.add_feature(cfeature.RIVERS)

    ax.set_title(title)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, orientation="vertical", shrink=0.7, aspect=25, pad=0.02)
    cbar.set_label("mm/year")

    # Gridlines
    gl = ax.gridlines(draw_labels=True, linestyle="--", linewidth=0.5)
    gl.top_labels = False
    gl.right_labels = False

    fig.tight_layout(pad=0.1)

    # Save figure if path provided
    if savepath is not None:
        plt.savefig(savepath, bbox_inches="tight", pad_inches=0.05, dpi=dpi)

    plt.show()

    return fig, ax


def plot_dem_map(
    da,
    title=None,
    cmap="terrain",
    figsize=(10, 8),
    savepath=None,
    shapefile=None,
):
    """Plot a DEM (digital elevation) DataArray using Cartopy.

    Parameters
    ----------
    da : xarray.DataArray
        2D elevation data (lat, lon)
    title : str
        Figure title
    cmap : str
        Colormap
    figsize : tuple
        Figure size
    savepath : str or Path
        Optional path to save the figure
    """
    fig, ax = plt.subplots(figsize=figsize, subplot_kw={"projection": ccrs.PlateCarree()})

    im = ax.pcolormesh(
        da["lon"],
        da["lat"],
        da,
        cmap=cmap,
        shading="auto",
    )

    # Map features
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.LAKES)
    ax.add_feature(cfeature.OCEAN, facecolor="#a2daff", edgecolor="none", zorder=2)
    ax.add_feature(cfeature.RIVERS)

    # Overlay shapefile if provided
    if shapefile is not None:
        with fiona.open(shapefile) as src:
            for feat in src:
                geom = shape(feat["geometry"])
                ax.add_geometries(
                    [geom],
                    crs=ccrs.PlateCarree(),
                    facecolor="none",
                    # edgecolor=outline_color,
                    # alpha=outline_alpha,
                    # linewidth=outline_linewidth
                )

    if title is None:
        title = "DEM map"
    ax.set_title(title)

    cbar = fig.colorbar(im, ax=ax, orientation="vertical", shrink=0.7)
    cbar.set_label("Elevation (m)")

    if savepath is not None:
        plt.savefig(savepath, bbox_inches="tight", dpi=200)

    plt.show()

    return fig, ax


## make koppen-geiger figure
def plot_koppen_geiger(
    path_to_file, savefig=False, save_dir=None, show_legend=True, show_plot=True, show_title=True
):
    """Plot Köppen-Geiger climate zones from a raster file.

    Parameters
    ----------
    path_to_file : str or Path
        Path to the Köppen-Geiger raster file.
    savefig : bool, default False
        If True, save the figure to disk.
    save_dir : str or Path, optional
        Directory to save the figure if savefig is True. Defaults to current directory.
    show_legend : bool, default True
        Display the legend on the plot.
    show_plot : bool, default True
        Display the plot interactively.
    show_title : bool, default True
        Display the default title on the plot.

    Returns:
    -------
    None
        Figure is displayed or saved to disk depending on parameters.

    Notes:
    -----
    If both savefig=False and show_plot=False, no figure is output.
    """
    path_to_file = Path(path_to_file)  # <-- make sure this is here
    parts = path_to_file.parts  # <-- now parts is defined

    with rasterio.open(path_to_file) as src:
        data = src.read(1)

    class_names = [
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

    rgb_colors = (
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
            ]
        )
        / 255
    )

    cmap = ListedColormap(rgb_colors)
    norm = BoundaryNorm(np.arange(0.5, 31.5, 1), cmap.N)

    # --- Shapefiles ---
    shapefiles = {
        # "Amu Darya": {"path": SHAPEFILES/"Chatly_GRDC/Chatly_GRDC.shp", "edgecolor": "blue", "linewidth": 2},
        # "Syr Darya": {"path": SHAPEFILES/"Kazalinsk_GRDC/Kazalinsk_GRDC.shp", "edgecolor": "red", "linewidth": 2},
        "Aral Sea Basin": {
            "path": SHAPEFILES / "AralSea_basin/AralSea_basin.shp",
            "edgecolor": "black",
            "linewidth": 1,
            "linestyle": "-",
        }
    }

    # --- Cartopy figure ---
    fig = plt.figure(figsize=(10, 10), dpi=300)
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([54, 82, 33, 53], crs=ccrs.PlateCarree())

    # --- Plot raster ---
    ax.imshow(
        data,
        cmap=cmap,
        norm=norm,
        origin="upper",
        extent=[-180, 180, -90, 90],  # full raster extent
        # extent=[54, 82, 33, 53],  # full raster extent
        transform=ccrs.PlateCarree(),
    )

    # --- Add map features ---
    ax.add_feature(COASTLINE, linewidth=1, edgecolor="black")
    ax.add_feature(BORDERS, linewidth=1, edgecolor="black", linestyle=":")
    ax.add_feature(LAKES, facecolor="lightblue", edgecolor="blue", zorder=19)
    ax.add_feature(RIVERS, edgecolor="blue", linewidth=1)
    ax.add_feature(OCEAN, facecolor="lightblue", edgecolor="blue", zorder=20)

    legend_handles = []

    # Köppen classes for legend
    for i, name in enumerate(class_names):
        patch = Patch(facecolor=rgb_colors[i], edgecolor="k", label=f"{i+1}: {name}")
        legend_handles.append(patch)

    # Add shapefiles and legend handles
    for label, cfg in shapefiles.items():
        feature = ShapelyFeature(
            Reader(cfg["path"]).geometries(),
            ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=cfg["edgecolor"],
            linewidth=cfg["linewidth"],
            linestyle=cfg["linestyle"],
        )
        ax.add_feature(feature)
        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=cfg["edgecolor"],
                linewidth=2,
                label=label,
                linestyle=cfg["linestyle"],
            )
        )

    # --- Gridlines and labels ---
    gl = ax.gridlines(draw_labels=True, linewidth=0.5, color="gray", alpha=0.5, linestyle="--")
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 10}
    gl.ylabel_style = {"size": 10}

    # --- Combined legend ---
    if show_legend:
        plt.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)

    # # --- Title ---
    # # plt.title("Köppen-Geiger Map for Aral Sea Basin", fontsize=14)

    # --- Build dynamic title ---
    if len(parts) >= 2 and parts[-2].startswith("ssp"):  # future scenario
        scenario = parts[-2]
        year_range = parts[-3]
        title_str = f"Köppen-Geiger Map ({year_range}, {scenario})"
    else:  # historical
        year_range = parts[-2]
        title_str = f"Köppen-Geiger Map ({year_range})"

    if show_title:
        plt.title(title_str, fontsize=14)

    plt.tight_layout()

    # --- Auto filename ---
    if savefig:
        # Extract parts from path
        parts = path_to_file.parts
        # Look for historical (1 folder) vs future (2 folders before filename)
        if len(parts) >= 2 and parts[-2].startswith("ssp"):  # future
            scenario = parts[-2]
            year_range = parts[-3]
            fname = f"koppen_{year_range}_{scenario}.png"
        else:  # historical
            year_range = parts[-2]
            fname = f"koppen_{year_range}.png"

        # Save directory
        if save_dir:
            save_path = Path(save_dir) / fname
        else:
            save_path = Path(fname)

        plt.savefig(save_path, dpi=300, bbox_inches="tight")

    if show_plot:
        plt.show()
        return fig, ax
    plt.close(fig)
    return None


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
        extent = (54, 33, 82, 53)
    lon_min, lat_min, lon_max, lat_max = extent

    # --- Load raster ---
    import rasterio

    with rasterio.open(path_to_file) as src:
        data = src.read(1)

    # --- Defaults ---
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
    if rgb_colors is None:
        rgb_colors = (
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
        extent=[-180, 180, -90, 90],
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
    rgb_colors = (
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
            ]
        )
        / 255
    )

    def counts_to_percent(counts):
        total = np.sum(counts)
        if total == 0:
            return np.zeros_like(counts, dtype=float)
        return [c / total * 100 for c in counts]

    # Map extent (first column)
    map_col = df_percent.columns[0]
    plt.figure(figsize=(12, 4))
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
    else:
        plt.close()

    # Remaining columns (shapefiles)
    for col in df_percent.columns[1:]:
        plt.figure(figsize=(12, 4))
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
        else:
            plt.close()


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
    return df_percent, top_df


def plot_climate_class_timeseries(topdf_all, climate_class, hist_ref_period="1991_2020"):
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
        hist_line["year_start"],
        hist_line["Plotted Area"],
        color="black",
        marker="o",
        label="HIST",
        zorder=20,
    )

    # SSP lines
    for ssp, g in ssp_plot_df[ssp_plot_df["climate_class"] == climate_class].groupby("ssp"):
        ax.plot(g["year_start"], g["Plotted Area"], marker="o", label=ssp)

    ax.set_xlabel("Year")
    ax.set_ylabel("Area (%)")
    ax.set_title(f"{climate_class} ({desc}) area fraction over time")
    ax.legend(title="Scenario")
    ax.grid(linestyle="--", alpha=0.5)
    plt.tight_layout()

    return fig, ax
