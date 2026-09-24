"""
Plot discharge data for PCR-GLOBWB stations from NetCDF output.

This script loads a NetCDF discharge file and extracts discharge time series
for each station defined in STATIONS_PCR (from constants.py), then plots them.
"""

import sys
from pathlib import Path
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

# Add src to path to import constants
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from constants import STATIONS_PCR

# Load NetCDF file
ncfile = "/home/avandervee3/MSc_AralSea/book/thesis_projects/MSc/2025_Q1_AndreVanDerVeen_CEG/work_in_progress/outputs/model_runs/pcr-globwb/calibration_runs_5march/run_0004/netcdf/discharge_dailyTot_output.nc"

print(f"Loading NetCDF file: {ncfile}")
ds = xr.open_dataset(ncfile)

print("Dataset variables:", list(ds.data_vars))
print("Dataset coordinates:", list(ds.coords))
print("Dataset info:")
print(ds)

# Extract latitude and longitude coordinates
lat = ds.coords["lat"].values
lon = ds.coords["lon"].values

# Create a grid of coordinates
lon_grid, lat_grid = np.meshgrid(lon, lat)
points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])

# Build a KD-tree for nearest neighbor search
tree = cKDTree(points)

# Create figure
fig, axes = plt.subplots(len(STATIONS_PCR), 1, figsize=(14, 3 * len(STATIONS_PCR)))
if len(STATIONS_PCR) == 1:
    axes = [axes]

# Get discharge variable (should be 'discharge' or similar)
discharge_var = None
for var in ds.data_vars:
    if "discharge" in var.lower():
        discharge_var = var
        break

if discharge_var is None:
    print("Available variables:", list(ds.data_vars))
    raise ValueError("Could not find discharge variable in NetCDF file")

print(f"Using discharge variable: {discharge_var}")

# Extract and plot data for each station
for idx, (station_name, station_info) in enumerate(STATIONS_PCR.items()):
    station_lat = station_info["lat"]
    station_lon = station_info["lon"]
    
    # Find nearest grid cell
    query_point = np.array([[station_lon, station_lat]])
    distance, location = tree.query(query_point)
    
    # Convert flat index to 2D indices
    nearest_idx = location[0]
    lat_idx, lon_idx = np.unravel_index(nearest_idx, lon_grid.shape)
    
    nearest_lat = lat[lat_idx]
    nearest_lon = lon[lon_idx]
    
    print(f"\n{station_name}:")
    print(f"  Requested: lat={station_lat}, lon={station_lon}")
    print(f"  Nearest grid cell: lat={nearest_lat}, lon={nearest_lon}")
    print(f"  Distance: {distance[0]:.4f} degrees")
    
    # Extract discharge for this location
    discharge = ds[discharge_var].isel(lat=lat_idx, lon=lon_idx).values
    
    # Plot
    ax = axes[idx]
    ax.plot(discharge, linewidth=1.5)
    ax.set_title(f"{station_name} (Requested: {station_lat}, {station_lon} | Actual: {nearest_lat:.2f}, {nearest_lon:.2f})")
    ax.set_ylabel("Discharge (m³/s)")
    ax.grid(True, alpha=0.3)
    if idx == len(STATIONS_PCR) - 1:
        ax.set_xlabel("Time step (days)")

plt.tight_layout()
plt.savefig("/home/avandervee3/MSc_AralSea/book/thesis_projects/MSc/2025_Q1_AndreVanDerVeen_CEG/work_in_progress/discharge_plot.png", dpi=150, bbox_inches='tight')
print("\nPlot saved to: discharge_plot.png")
plt.show()

ds.close()
