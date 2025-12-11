import numpy as np
import matplotlib.pyplot as plt
from ipywidgets import interact, FloatSlider, IntSlider, fixed, VBox, interactive_output, HTML, Button, HBox, Label
import pandas as pd
from pathlib import Path
import os
import geopandas as gpd
import xarray as xr
import numpy as np
import folium
from IPython.display import display

# General eWaterCycle
import ewatercycle
import ewatercycle.models
import ewatercycle.forcing


import shutil
import zipfile
from pathlib import Path

import fiona
import pandas as pd
import urllib3
import xarray as xr
from cartopy.io import shapereader

from ewatercycle.base.forcing import DefaultForcing
from ewatercycle.util import get_time

COMMON_URL = "ca13056c-c347-4a27-b320-930c2a4dd207"
OPENDAP_URL = f"https://opendap.4tu.nl/thredds/dodsC/data2/djht/{COMMON_URL}/2/"
SHAPEFILE_URL = (
    f"https://data.4tu.nl/file/{COMMON_URL}/bbe94526-cf1a-4b96-8155-244f20094719"
)

DIRECTORY = f"/data/shared/climate-data/caravan"

PROPERTY_VARS = [
    "timezone",
    "name",
    "country",
    "lat",
    "lon",
    "area",
    "p_mean",
    "pet_mean",
    "aridity",
    "frac_snow",
    "moisture_index",
    "seasonality",
    "high_prec_freq",
    "high_prec_dur",
    "low_prec_freq",
    "low_prec_dur",
]

RENAME_ERA5 = {
    "total_precipitation_sum": "pr",
    # "potential_evaporation_sum_ERA5_LAND": "evspsblpot",
    "potential_evaporation_sum": "evspsblpot",
    "temperature_2m_mean": "tas",
    "temperature_2m_min": "tasmin",
    "temperature_2m_max": "tasmax",
    "streamflow": "Q",
}


class CaravanForcing(DefaultForcing):
    """Retrieves specified part of the caravan dataset from the OpenDAP server.

    Examples:
        The caravan dataset is an already prepared set by Frederik Kratzert,
        (see https://doi.org/10.1038/s41597-023-01975-w).

        This retrieves it from the OpenDAP server of 4TU,
        (see https://doi.org/10.4121/bf0eaf7c-f2fa-46f6-b8cd-77ad939dd350.v4).

        This can be done by specifying the

        .. code-block:: python

            from pathlib import Path
            from ewatercycle.forcing import sources

            path = Path.cwd()
            forcing_path = path / "Forcing" / "Camels"
            forcing_path.mkdir(parents=True, exist_ok=True)
            experiment_start_date = "1997-08-01T00:00:00Z"
            experiment_end_date = "2005-09-01T00:00:00Z"
            HRU_id = 1022500

            camels_forcing = sources['CaravanForcing'].generate(
                                        start_time = experiment_start_date,
                                        end_time = experiment_end_date,
                                        directory = forcing_path,
                                        basin_id = f"camels_0{HRU_id}"
                                                                    )

        which gives something like:

        .. code-block:: python

            CaravanForcing(
            start_time='1997-08-01T00:00:00Z',
            end_time='2005-09-01T00:00:00Z',
            directory=PosixPath('/home/davidhaasnoot/eWaterCycle-WSL-WIP/Forcing/Camels'),
            shape=PosixPath('/home/davidhaasnoot/eWaterCycle-WSL-WIP/Forcing/Camels/shapefiles/camels_01022500.shp'),
            filenames={
                'tasmax':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tasmax.nc',
                'tasmin':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tasmin.nc',
                'evspsblpot':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_evspsblpot.nc',
                'pr': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_pr.nc',
                'tas': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tas.nc',
                'Q': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_Q.nc'
            }
            )


        More in depth notebook van be found here:
        https://gist.github.com/Daafip/ac1b030eb5563a76f4d02175f2716fd7
    """  # noqa: E501

    @classmethod
    def get_dataset(cls: type["CaravanForcing"], dataset: str, basin_id: str) -> xr.Dataset:
        """Opens specified dataset from data.4tu.nl OPeNDAP server.

        Args:
            dataset (str): name of dataset, choose from:
                'camels',
                'camelsaus',
                'camelsbr',
                'camelscl',
                'camelsgb',
                'hysets',
                'lamah'
        """
        # return xr.open_dataset(f"{DIRECTORY}/timeseries/netcdf/{dataset}/{basin_id}.nc")
        return xr.open_dataset(f"{DIRECTORY}/{dataset}.nc")

    @classmethod
    def get_basin_id(cls: type["CaravanForcing"], dataset: str) -> list[str]:
        """Gets a list of all the basin ids in provided dataset.

        Args:
            dataset (str): name of dataset, choose from:
                'camels',
                'camelsaus',
                'camelsbr',
                'camelscl',
                'camelsgb',
                'hysets',
                'lamah'

        Note:
            https://www.ewatercycle.org/caravan-map/ contains online a set of
            interactive maps which allows exploration of the available catchments and
            also contains the needed basin_ids.
            Alternatively, a zip with shapefiles is available at
            https://doi.org/10.4121/ca13056c-c347-4a27-b320-930c2a4dd207.v1 which also
            allows exploration of the dataset.
        """
        return [val.decode() for val in cls.get_dataset(dataset).basin_id.to_numpy()]

    @classmethod
    def generate(  # type: ignore[override]
        cls: type["CaravanForcing"],
        start_time: str,
        end_time: str,
        directory: str,
        variables: tuple[str, ...] = (),
        shape: str | Path | None = None,
        **kwargs,
    ) -> "CaravanForcing":
        """Retrieve caravan for a model.

        Args:
            start_time: Start time of forcing in UTC and ISO format string e.g.
                'YYYY-MM-DDTHH:MM:SSZ'.
            end_time: nd time of forcing in UTC and ISO format string e.g.
                'YYYY-MM-DDTHH:MM:SSZ'.
            directory: Directory in which forcing should be written.
            variables: Variables which are needed for model,
                if not specified will default to all.
            shape: (Optional) Path to a shape file.
                If none is specified, will be downloaded automatically.
            kwargs: Additional keyword arguments.
                basin_id: The ID of the desired basin. Data sets can be explored using
                `CaravanForcing.get_dataset(dataset_name)` or
                `CaravanForcing.get_basin_id(dataset_name)`
                where `dataset_name` is the name of a dataset in Caravan
                (for example, "camels" or "camelsgb").
                For more information do `help(CaravanForcing.get_basin_id)` or see
                https://www.ewatercycle.org/caravan-map/.
        """
        if "basin_id" not in kwargs:
            msg = (
                "You have to specify a basin ID to be able to generate forcing from"
                " Caravan."
            )
            raise ValueError(msg)
        basin_id = str(kwargs["basin_id"])

        dataset: str = basin_id.split("_")[0]
        ds = cls.get_dataset(dataset, basin_id)
        ds_basin = ds.sel(basin_id=basin_id)
        ds_basin_time = crop_ds(ds_basin, start_time, end_time)

        if shape is None:
            shape = get_shapefiles(Path(directory), basin_id)

        if len(variables) == 0:
            variables = ds_basin_time.data_vars.keys()  # type: ignore[assignment]

        # only return the properties which are also in property vars
        properties = set(variables).intersection(PROPERTY_VARS)
        non_property_vars = set(variables) - properties
        variable_names = non_property_vars.intersection(
            RENAME_ERA5.keys()
        )  # only take the vars also in Rename dict

        for prop in properties:
            ds_basin_time.coords.update({prop: ds_basin_time[prop].to_numpy()})

        ds_basin_time = ds_basin_time.rename(RENAME_ERA5)
        variables = tuple([RENAME_ERA5[var] for var in variable_names])

        # convert units to Kelvin for compatibility with CMOR MIP table units
        # for temp in ["tas", "tasmin", "tasmax"]:
        #     if temp not in ds_basin_time:
        #         continue
        
        #     ds_basin_time[temp].attrs.update({"height": "2m"})
        
        #     unit = ds_basin_time[temp].attrs.get("unit", None)
        #     if unit == "°C":
        #         ds_basin_time[temp].values = ds_basin_time[temp].to_numpy() + 273.15
        #         ds_basin_time[temp].attrs["unit"] = "K"

        # for var in ["evspsblpot", "pr"]:
        #     if var not in ds_basin_time:
        #         continue
        
        #     unit = ds_basin_time[var].attrs.get("unit", None)
        #     if unit == "mm":
        #         ds_basin_time[var].values = ds_basin_time[var].to_numpy() / 86400
        #         ds_basin_time[var].attrs["unit"] = "kg m-2 s-1"

        # convert units to Kelvin for compatibility with CMOR MIP table units
        for temp in ["tas", "tasmin", "tasmax"]:
            ds_basin_time[temp].attrs.update({"height": "2m"})
            if (ds_basin_time[temp].attrs["unit"]) == "°C":
                ds_basin_time[temp].values = ds_basin_time[temp].to_numpy() + 273.15
                ds_basin_time[temp].attrs["unit"] = "K"

        for var in ["evspsblpot", "pr"]:
            if (ds_basin_time[var].attrs["unit"]) == "mm":
                # mm/day --> kg m-2 s-1
                ds_basin_time[var].values = ds_basin_time[var].to_numpy() / (86400)
                ds_basin_time[var].attrs["unit"] = "kg m-2 s-1"

        
        start_time_name = start_time[:10]
        end_time_name = end_time[:10]

        # history_attrs = ds_basin_time.attrs.get("history", "")
        for var in variables:
            # ds_basin_time[var].attrs["history"] = history_attrs
            ds_basin_time[var].to_netcdf(
                Path(directory)
                / f"{basin_id}_{start_time_name}_{end_time_name}_{var}.nc"
            )

        forcing = cls(
            directory=Path(directory),
            start_time=start_time,
            end_time=end_time,
            shape=Path(shape),
            filenames={
                var: f"{basin_id}_{start_time_name}_{end_time_name}_{var}.nc"
                for var in variables
            },
        )
        forcing.save()
        return forcing


def get_shapefiles(directory: Path, basin_id: str) -> Path:
    """Retrieve shapefiles from data dcache ."""
    zip_path = directory / "shapefiles.zip"
    output_path = directory / "shapefiles"
    shape_path = directory / f"{basin_id}.shp"
    combined_shapefile_path = Path(f"{DIRECTORY}/shapefiles/combined.shp")
    
    if not shape_path.is_file():
        extract_basin_shapefile(basin_id, combined_shapefile_path, shape_path)

    return shape_path


def extract_basin_shapefile(
    basin_id: str,
    combined_shapefile_path: Path,
    shape_path: Path,
) -> None:
    """Extract single polygon from multipolygon shapefile."""
    shape_obj = shapereader.Reader(combined_shapefile_path)
    list_records = [record.attributes["gauge_id"] for record in shape_obj.records()]

    basins = pd.DataFrame(
        data=list_records, index=range(len(list_records)), columns=["basin_id"]
    )
    basin_index = basins[basins["basin_id"] == basin_id].index.array[0]

    with fiona.open(combined_shapefile_path) as src:
        dst_schema = src.schema  # Copy the source schema
        # Create a sink for processed features with the same format and
        # coordinate reference system as the source.
        with fiona.open(
            shape_path,
            mode="w",
            layer=basin_id,
            crs=src.crs,
            driver="ESRI Shapefile",
            schema=dst_schema,
        ) as dst:
            for i, feat in enumerate(src):
                # kind of clunky but it works: select filtered polygon
                if i == basin_index:
                    geom = feat.geometry
                    if geom.type != "Polygon":
                        msg = "Only polygons are supported"
                        raise ValueError(msg)

                    # Add the signed area of the polygon and a timestamp
                    # to the feature properties map.
                    props = fiona.Properties.from_dict(
                        **feat.properties,
                    )

                    dst.write(fiona.Feature(geometry=geom, properties=props))


def crop_ds(ds: xr.Dataset, start_time: str, end_time: str) -> xr.Dataset:
    """Crops dataset based on time."""
    start = pd.Timestamp(get_time(start_time)).tz_convert(None)
    end = pd.Timestamp(get_time(end_time)).tz_convert(None)
    return ds.isel(
        time=(ds["time"].to_numpy() >= start) & (ds["time"].to_numpy() <= end)
    )

# def crop_ds(ds: xr.Dataset, start_time: str, end_time: str) -> xr.Dataset:
#     """Crops dataset based on time, supporting both 'time' and 'date' coordinates."""
#     start = pd.Timestamp(get_time(start_time)).tz_convert(None)
#     end = pd.Timestamp(get_time(end_time)).tz_convert(None)

#     # Determine which time dimension exists
#     if "time" in ds.coords:
#         t = ds["time"].to_numpy()
#         return ds.isel(time=(t >= start) & (t <= end))
#     # elif "date" in ds.coords:
#     #     t = pd.to_datetime(ds["date"].to_numpy())  # original code
#     #     return ds.isel(date=(t >= start) & (t <= end))   # original code
#     elif "date" in ds.coords:
#         t = pd.to_datetime(ds["date"].to_numpy()) 
#         ds = ds.isel(date=(t >= start) & (t <= end))

#         # Convert 'date' → 'time'
#         ds = ds.rename({'date': 'time'})
#         ds = ds.assign_coords(time=pd.to_datetime(ds['time'].values))
        
#         return ds 
#         # extract date values
#         # date_values = ds["date"].values
    
#         # # convert to datetime if needed
#         # try:
#         #     time_values = pd.to_datetime(date_values)
#         # except Exception:
#         #     raise ValueError("Could not convert `date` to datetime64.")
    
#         # # assign new time coordinate and swap dimensions
#         # ds = ds.assign_coords(time=("date", time_values))
    
#         # # If date is a dimension, swap it out
#         # if "date" in ds.dims:
#         #     ds = ds.swap_dims({"date": "time"})
    
#         # # optionally drop the old date variable
#         # ds = ds.drop_vars("date")
#         # t = ds["time"].to_numpy()
#         # return ds.isel(time=(t >= start) & (t <= end))
#     else:
#         raise KeyError(f"Dataset has no 'time' or 'date' coordinate. Found coords: {list(ds.coords)}")

def get_time_blocks_available_discharge_data(camel_id):

    dir_tmp = Path.home() / "tmp"
    dir_tmp.mkdir(exist_ok=True, parents=True)
    # Custom function to create a data object, which will work with eWaterCycle
    forcing_for_discharge_lookup =  CaravanForcing.generate(
        start_time="1950-01-01T00:00:00Z", 
        end_time="2020-01-01T00:00:00Z",
        directory=Path.home() / "tmp",
        basin_id=camel_id)
    
    # Rewrite the forcing for the interactive calibration plot, this is also used for the observed streamflow
    calibrate_forcing = load_data_HBV_local(forcing_for_discharge_lookup)
    
    Q = calibrate_forcing["Q"]
    valid = Q.notna()
    
    # Detect segments
    change_points = valid.ne(valid.shift()).cumsum()
    segments = Q[valid].groupby(change_points)
    
    # Collect blocks
    data_blocks = []
    for _, block in segments:
        start = block.index[0]
        end = block.index[-1]
        length = end - start
        data_blocks.append((start, end, length))
    
    # Sort blocks by length (descending)
    data_blocks = sorted(data_blocks, key=lambda x: x[2], reverse=True)
    
    # Print result
    for i, (start, end, length) in enumerate(data_blocks, 1):
        print(f"Block {i}: {start} → {end}  (Length: {length})")

    # Extract longest block
    longest_start, longest_end, _ = data_blocks[0]

    # Format ISO8601 with Z-suffix
    start_date = longest_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date   = longest_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    return start_date, end_date

def Weigfun(Tlag): 
    # WEIGFUN Summary of this function goes here
    #   Detailed explanation goes here
    nmax = int(np.ceil(Tlag))
    if nmax == 1: 
        Weigths = float(1)
    else:
        Weigths = np.zeros(nmax)

        th = Tlag / 2
        nh = int(np.floor(th))
        for i in range(0,nh): 
            Weigths[i] = (float(i + 1) - 0.5) / th        
            i = nh
            Weigths[i] = (1 + (float(i+1) - 1) / th) * (th -int(np.floor(th))) / 2 + (1 + (Tlag - float(i+1)) / th) * (int(np.floor(th)) + 1 - th) / 2
            
        for i in range(nh+1, int(np.floor(Tlag))):
            Weigths[i] = (Tlag - float(i+1) + .5) / th

        if Tlag > int(np.floor(Tlag)):
            Weigths[int(np.floor(Tlag))] = (Tlag - int(np.floor(Tlag))) ** 2 / (2 * th)

        Weigths = Weigths / sum(Weigths)

    return(Weigths)
    # plot(Weigths) 
 

# Initialize the global counter
param_change_counter = 0  
initial_run = True

def plot_hydrograph(I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks, FM, model, forcing):
    Sin = np.array([0,  100,  0,  5, 0])
    Par = np.array([I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks, FM])
    Qm = model(Par, forcing, Sin, hydrograph='FALSE')

    # Calculate NSE
    Qo = forcing['Q'].values
    ind = np.where(Qo >= 0)
    QoAv = np.mean(Qo[ind])
    ErrUp = np.sum((Qo[ind] - Qm[ind]) ** 2)
    ErrDo = np.sum((Qo[ind] - QoAv) ** 2)
    Obj = 1 - (ErrUp / ErrDo)

    # # New NSE
    # Obj = ErrUp

    # Plot hydrograph
    plt.figure(figsize=(10, 5))
    plt.plot(forcing.index, forcing['Q'], label='Observed Q')
    plt.plot(forcing.index, Qm, label='Simulated Q')

    plt.xlabel('Date')
    plt.ylabel('Flow')
    plt.title(f'Hydrograph - NSE = {Obj:.2f}')
    plt.legend()
    plt.grid(True)
    plt.show()



def interactive_plot(model, forcing, params):
    global param_change_counter, initial_run

    # Create a display widget to show the counter
    #counter_display = HTML(value=f"<b>Parameter Changes: {param_change_counter}</b>")
    # Create a label to show recalculation status
    # recalculating_label = Label(value="")
    recalculating_label = HTML(value="")
    
    # Update recalculating status
    
    # Calculate average parameter values
    I_max = (params['I_max']['min'] + params['I_max']['max']) / 2
    Ce = (params['Ce']['min'] + params['Ce']['max']) / 2
    Su_max = (params['Su_max']['min'] + params['Su_max']['max']) / 2 
    beta = (params['beta']['min'] + params['beta']['max']) / 2
    P_max = (params['P_max']['min'] + params['P_max']['max']) / 2
    T_lag = (params['T_lag']['min'] + params['T_lag']['max']) / 2
    Kf = (params['Kf']['min'] + params['Kf']['max']) / 2
    Ks = (params['Ks']['min'] + params['Ks']['max']) / 2
    FM = (params['FM']['min'] + params['FM']['max']) / 2

    # Create sliders with the specified min and max values
    sliders = {
        'I_max': FloatSlider(min=params['I_max']['min'], max=params['I_max']['max'], step=0.1, value=I_max),
        'Ce': FloatSlider(min=params['Ce']['min'], max=params['Ce']['max'], step=0.01, value=Ce),
        'Su_max': FloatSlider(min=params['Su_max']['min'], max=params['Su_max']['max'], step=1, value=Su_max),
        'beta': FloatSlider(min=params['beta']['min'], max=params['beta']['max'], step=0.1, value=beta),
        'P_max': FloatSlider(min=params['P_max']['min'], max=params['P_max']['max'], step=0.001, value=P_max),
        'T_lag': IntSlider(min=params['T_lag']['min'], max=params['T_lag']['max'], step=1, value=T_lag),
        'Kf': FloatSlider(min=params['Kf']['min'], max=params['Kf']['max'], step=0.01, value=Kf),
        'Ks': FloatSlider(min=params['Ks']['min'], max=params['Ks']['max'], step=0.0001, value=Ks, readout_format='.3f'),
        'FM': FloatSlider(min=params['FM']['min'], max=params['FM']['max'], step=0.01, value=FM, readout_format='.3f')
    }

    # Combine sliders with their labels, and align them to the left
    slider_widgets = [HBox([Label(value=name, layout={'width': '150px'}), slider], layout={'align_items': 'flex-start'}) 
                      for name, slider in sliders.items()]

    def update_counter(change):
        global param_change_counter, initial_run
        if not initial_run:
            param_change_counter += 1
            #counter_display.value = f"<b>Parameter Changes: {param_change_counter}</b>"
            
        recalculating_label.value = "<b>Loading....</b>"

        out.clear_output(wait=True)
        with out:
            plot_hydrograph(
                I_max=sliders['I_max'].value, 
                Ce=sliders['Ce'].value, 
                Su_max=sliders['Su_max'].value, 
                beta=sliders['beta'].value, 
                P_max=sliders['P_max'].value, 
                T_lag=sliders['T_lag'].value, 
                Kf=sliders['Kf'].value, 
                Ks=sliders['Ks'].value,
                FM=sliders['FM'].value,
                model=model, 
                forcing=forcing
            )
    
        # Update recalculation status after completion
        recalculating_label.value = "<b>Recalculation Complete</b>"
    
    
    # Attach the change handler to each slider
    for slider in sliders.values():
        slider.observe(update_counter, names='value')

    
    # Create the interactive plot
    ui = VBox([recalculating_label] + slider_widgets) #+ list(sliders.values()))
    out = interactive_output(lambda **kwargs: None, {})  # Empty output placeholder

    display(ui, out)

    # Plot the first time without incrementing the counter
    if initial_run:
        out.clear_output(wait=True)
        initial_run = False
        with out:
            plot_hydrograph(
                I_max=sliders['I_max'].value, 
                Ce=sliders['Ce'].value, 
                Su_max=sliders['Su_max'].value, 
                beta=sliders['beta'].value, 
                P_max=sliders['P_max'].value, 
                T_lag=sliders['T_lag'].value, 
                Kf=sliders['Kf'].value, 
                Ks=sliders['Ks'].value,
                FM=sliders['FM'].value,
                model=model, 
                forcing=forcing
            )

def HBV_snow(Par,forcing,S_in, hydrograph):
    # HBVpareto Calculates values of 3 objective functions for HBV model

    I_max = Par[0]
    Ce = Par[1]
    Su_max = Par[2]
    beta = Par[3]
    P_max = Par[4]
    T_lag = Par[5]
    Kf = Par[6]
    Ks = Par[7]
    FM = Par[8]
    

    Prec = forcing['P'].values
    Qo = forcing['Q'].values
    Etp = forcing['PE'].values
    Tmean = forcing['T'].values


    t_max = len(Prec)
    
    # Allocate Si, Su, Sf, Ss, Ei_dt, Ea_dt, Q_tot_dt
    
    Si = np.zeros(t_max)
    Su = np.zeros(t_max)
    Sf = np.zeros(t_max)
    Ss = np.zeros(t_max)
    Sp = np.zeros(t_max)
    Ei_dt = np.zeros(t_max)
    Ea_dt =  np.zeros(t_max)
    Q_tot_dt = np.zeros(t_max)
    Qs = np.zeros(t_max)
    Qf = np.zeros(t_max)
    
    # Initialize Si, Su, Sf, Ss Sp
    Si[0] = S_in[0]
    Su[0] = S_in[1]
    Sf[0] = S_in[2]
    Ss[0] = S_in[3]
    Sp[0] = S_in[4]  # Snow

    dt = 1

    # other constant for Snow:
    Tt = -0.5 + 273.15 # Threshold temperature set for now. Can be between -1 to 1
    
    #
    # Model 1 SOF1
    for i in range(0, t_max):
        P_dt = Prec[i] * dt
        Ep_dt = Etp[i] * dt
        T_dt = Tmean[i] * dt
        
        if T_dt <= Tt:  # Snowing
            Ps = P_dt
            P_dt = 0
            M_dt = 0  # No Melting
            Sp[i] += Ps
        else:  # Not snowing
            Ps = 0
            M_dt = min(Sp[i]/ dt, FM*(T_dt - Tt))
            Sp[i] -= M_dt
            P_dt += M_dt  # add snowmelt to precip

            
        # Interception Reservoir
        if P_dt > 0:
            Si[i] = Si[i] + P_dt 
            Pe_dt = np.maximum(0, (Si[i] - I_max) / dt)
            Si[i] = Si[i] - Pe_dt
            Ei_dt[i] = 0

        else:
        # Evaporation only when there is no rainfall
            Pe_dt = 0 # is zero, because of no rainfall
            Ei_dt[i] = np.minimum(Ep_dt, Si[i] / dt)
            Si[i] = Si[i] - Ei_dt[i]
        
        if i < t_max-1:
            Si[i+1] = Si[i]
            Sp[i+1] = Sp[i]
        
        
        # Split Pe into Unsaturated Reservoir and Preferential Reservoir
        if Pe_dt > 0:
            Cr = (Su[i] / Su_max) ** beta
            Qiu_dt = (1 - Cr) * Pe_dt # flux from Ir to Ur
            Su[i] = Su[i] + Qiu_dt
            Quf_dt = Cr * Pe_dt #flux from Su to Sf
        else:
            Quf_dt = 0
        
        # Transpiration
        Ep_dt = max(0, Ep_dt - Ei_dt[i])
        Ea_dt[i] = Ep_dt * (Su[i] / (Su_max * Ce))
        Ea_dt[i] = min(Su[i] / dt, Ea_dt[i])
        Su[i] = Su[i] - Ea_dt[i]
        
        # Percolation
        Qus_dt = P_max * (Su[i] / Su_max) * dt  # Flux from Su to Ss
        Su[i] = Su[i] - Qus_dt
        
        if i < t_max - 1:
            Su[i+1] = Su[i]
        
        # Fast Reservoir
        Sf[i] = Sf[i] + Quf_dt
        Qf_dt = max(0, dt * Kf * Sf[i])
        Sf[i] = Sf[i] - Qf_dt
        if i < t_max-1:
            Sf[i+1] = Sf[i]
        
        # Slow Reservoir
        Ss[i] = Ss[i] + Qus_dt
        Qs_dt = dt * Ks * Ss[i]
        Ss[i] = Ss[i] - Qs_dt
        if i < t_max-1:
            Ss[i+1] = Ss[i]
        
        Q_tot_dt[i] = Qs_dt + Qf_dt
        Qs[i] = Qs_dt 
        Qf[i] = Qf_dt 


    # Check Water Balance
    S_final = Si[-1] + Ss[-1] + Sf[-1] + Su[-1]  # final storage
    S_in = sum(S_in)  # initial storage
    WB = sum(Prec) - sum(Ei_dt) - sum(Ea_dt) - sum(Q_tot_dt) - S_final + S_in
    # print(WB)
    # Offset Q

    Weigths = Weigfun(T_lag)
    
    Qm = np.convolve(Q_tot_dt, Weigths)
    Qm = Qm[0:t_max]
    forcing['Qm'] = Qm
   
    if hydrograph == 'TRUE':
    ## Plot
    # hour=1:t_max\
        fig, ax = plt.subplots(figsize=(12,8))
        forcing['Q'].plot(label='Obserbed', ax=ax)
        forcing['Qm'].plot(label='Model',  ax=ax)
        ax.legend()
        

    return Qm



def load_data_HBV_local(HBV_data):

    # Load NetCDF variables
    P = xr.open_dataset(HBV_data['pr'], engine="netcdf4")['pr']
    PE = xr.open_dataset(HBV_data['evspsblpot'], engine="netcdf4")['evspsblpot']
    Q = xr.open_dataset(HBV_data['Q'], engine="netcdf4")['Q']  # Assuming variable is named 'Q'
    T = xr.open_dataset(HBV_data['tas'], engine="netcdf4")['tas']
    
    # Convert to pandas Series
    P_series = P.to_series() * 86400  # back to mm
    PE_series = PE.to_series() * 86400  # back to mm
    Q_series = Q.to_series()
    T_series = T.to_series()
    
    # Combine into a DataFrame
    calibrate_forcing = pd.DataFrame({
        'P': P_series,
        'PE': PE_series,
        'Q': Q_series,
        'T': T_series
    })

    return calibrate_forcing

# def interactive_plot(model, forcing, params):
    # global param_change_counter, initial_run

    # # Create a display widget to show the counter
    # #counter_display = HTML(value=f"<b>Parameter Changes: {param_change_counter}</b>")
    # # Create a label to show recalculation status
    # # recalculating_label = Label(value="")
    # recalculating_label = HTML(value="")
    
    # # Update recalculating status
    
    # # Calculate average parameter values
    # I_max = (params['I_max']['min'] + params['I_max']['max']) / 2
    # Ce = (params['Ce']['min'] + params['Ce']['max']) / 2
    # Su_max = (params['Su_max']['min'] + params['Su_max']['max']) / 2 
    # beta = (params['beta']['min'] + params['beta']['max']) / 2
    # P_max = (params['P_max']['min'] + params['P_max']['max']) / 2
    # T_lag = (params['T_lag']['min'] + params['T_lag']['max']) / 2
    # Kf = (params['Kf']['min'] + params['Kf']['max']) / 2
    # Ks = (params['Ks']['min'] + params['Ks']['max']) / 2

    # # Create sliders with the specified min and max values
    # sliders = {
    #     'I_max': FloatSlider(min=params['I_max']['min'], max=params['I_max']['max'], step=0.1, value=I_max),
    #     'Ce': FloatSlider(min=params['Ce']['min'], max=params['Ce']['max'], step=0.01, value=Ce),
    #     'Su_max': FloatSlider(min=params['Su_max']['min'], max=params['Su_max']['max'], step=1, value=Su_max),
    #     'beta': FloatSlider(min=params['beta']['min'], max=params['beta']['max'], step=0.1, value=beta),
    #     'P_max': FloatSlider(min=params['P_max']['min'], max=params['P_max']['max'], step=0.001, value=P_max),
    #     'T_lag': IntSlider(min=params['T_lag']['min'], max=params['T_lag']['max'], step=1, value=T_lag),
    #     'Kf': FloatSlider(min=params['Kf']['min'], max=params['Kf']['max'], step=0.01, value=Kf),
    #     'Ks': FloatSlider(min=params['Ks']['min'], max=params['Ks']['max'], step=0.0001, value=Ks, readout_format='.3f')
    # }

    # # Combine sliders with their labels, and align them to the left
    # slider_widgets = [HBox([Label(value=name, layout={'width': '150px'}), slider], layout={'align_items': 'flex-start'}) 
    #                   for name, slider in sliders.items()]

    # def update_counter(change):
    #     global param_change_counter, initial_run
    #     if not initial_run:
    #         param_change_counter += 1
    #         #counter_display.value = f"<b>Parameter Changes: {param_change_counter}</b>"
            
    #     recalculating_label.value = "<b>Loading....</b>"

    #     out.clear_output(wait=True)
    #     with out:
    #         plot_hydrograph(
    #             I_max=sliders['I_max'].value, 
    #             Ce=sliders['Ce'].value, 
    #             Su_max=sliders['Su_max'].value, 
    #             beta=sliders['beta'].value, 
    #             P_max=sliders['P_max'].value, 
    #             T_lag=sliders['T_lag'].value, 
    #             Kf=sliders['Kf'].value, 
    #             Ks=sliders['Ks'].value,
    #             model=model, 
    #             forcing=forcing
    #         )
    
    #     # Update recalculation status after completion
    #     recalculating_label.value = "<b>Recalculation Complete</b>"
    
    
    # # Attach the change handler to each slider
    # for slider in sliders.values():
    #     slider.observe(update_counter, names='value')

    
    # # Create the interactive plot
    # ui = VBox([recalculating_label] + slider_widgets) #+ list(sliders.values()))
    # out = interactive_output(lambda **kwargs: None, {})  # Empty output placeholder

    # display(ui, out)

    # # Plot the first time without incrementing the counter
    # if initial_run:
    #     out.clear_output(wait=True)
    #     initial_run = False
    #     with out:
    #         plot_hydrograph(
    #             I_max=sliders['I_max'].value, 
    #             Ce=sliders['Ce'].value, 
    #             Su_max=sliders['Su_max'].value, 
    #             beta=sliders['beta'].value, 
    #             P_max=sliders['P_max'].value, 
    #             T_lag=sliders['T_lag'].value, 
    #             Kf=sliders['Kf'].value, 
    #             Ks=sliders['Ks'].value,
    #             model=model, 
    #             forcing=forcing
    #         )

# def plot_hydrograph(I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks, model, forcing):
#     Sin = np.array([0,  100,  0,  5  ])
#     Par = np.array([I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks])
#     Qm = model(Par, forcing, Sin, hydrograph='FALSE')

#     # Calculate NSE
#     Qo = forcing['Q'].values
#     ind = np.where(Qo >= 0)
#     QoAv = np.mean(Qo[ind])
#     ErrUp = np.sum((Qo[ind] - Qm[ind]) ** 2)
#     ErrDo = np.sum((Qo[ind] - QoAv) ** 2)
#     Obj = 1 - (ErrUp / ErrDo)

#     # # New NSE
#     # Obj = ErrUp

#     # Plot hydrograph
#     plt.figure(figsize=(10, 5))
#     plt.plot(forcing.index, forcing['Q'], label='Observed Q')
#     plt.plot(forcing.index, Qm, label='Simulated Q')

#     plt.xlabel('Date')
#     plt.ylabel('Flow')
#     plt.title(f'Hydrograph - NSE = {Obj:.2f}')
#     plt.legend()
#     plt.grid(True)
#     plt.show()
    
# def HBV(Par,forcing,S_in, hydrograph):
#     # HBVpareto Calculates values of 3 objective functions for HBV model

#     I_max = Par[0]
#     Ce = Par[1]
#     Su_max = Par[2]
#     beta = Par[3]
#     P_max = Par[4]
#     T_lag = Par[5]
#     Kf = Par[6]
#     Ks = Par[7]
    

#     Prec = forcing['P'].values
#     Qo = forcing['Q'].values
#     Etp = forcing['PE'].values


#     t_max = len(Prec)
    
#     # Allocate Si, Su, Sf, Ss, Ei_dt, Ea_dt, Q_tot_dt
    
#     Si = np.zeros(t_max)
#     Su = np.zeros(t_max)
#     Sf = np.zeros(t_max)
#     Ss = np.zeros(t_max)
#     Ei_dt = np.zeros(t_max)
#     Ea_dt =  np.zeros(t_max)
#     Q_tot_dt = np.zeros(t_max)
#     Qs = np.zeros(t_max)
#     Qf = np.zeros(t_max)
    
#     # Initialize Si, Su, Sf, Ss
#     Si[0] = S_in[0]
#     Su[0] = S_in[1]
#     Sf[0] = S_in[2]
#     Ss[0] = S_in[3]

#     dt = 1
    
#     #
#     # Model 1 SOF1
#     for i in range(0, t_max):
#         P_dt = Prec[i] * dt
#         Ep_dt = Etp[i] * dt
        
#         # Interception Reservoir
#         if P_dt > 0:
#             Si[i] = Si[i] + P_dt 
#             Pe_dt = np.maximum(0, (Si[i] - I_max) / dt)
#             Si[i] = Si[i] - Pe_dt
#             Ei_dt[i] = 0
#         else:
#         # Evaporation only when there is no rainfall
#             Pe_dt = np.maximum(0, (Si[i] - I_max) / dt) #is zero, because of no rainfall
#             Ei_dt[i] = np.minimum(Ep_dt, Si[i] / dt)
#             Si[i] = Si[i] - Pe_dt - Ei_dt[i]
        
#         if i < t_max-1:
#             Si[i+1] = Si[i]
        
        
#         # Split Pe into Unsaturated Reservoir and Preferential Reservoir
#         if Pe_dt > 0:
#             Cr = (Su[i] / Su_max) ** beta
#             Qiu_dt = (1 - Cr) * Pe_dt # flux from Ir to Ur
#             Su[i] = Su[i] + Qiu_dt
#             Quf_dt = Cr * Pe_dt #flux from Su to Sf
#         else:
#             Quf_dt = 0
        
#         # Transpiration
#         Ep_dt = max(0, Ep_dt - Ei_dt[i])
#         Ea_dt[i] = Ep_dt * (Su[i] / (Su_max * Ce))
#         Ea_dt[i] = min(Su[i] / dt, Ea_dt[i])
#         Su[i] = Su[i] - Ea_dt[i]
        
#         # Percolation
#         Qus_dt = P_max * (Su[i] / Su_max) * dt  # Flux from Su to Ss
#         Su[i] = Su[i] - Qus_dt
        
#         if i < t_max - 1:
#             Su[i+1] = Su[i]
        
#         # Fast Reservoir
#         Sf[i] = Sf[i] + Quf_dt
#         Qf_dt = dt * Kf * Sf[i]
#         Sf[i] = Sf[i] - Qf_dt
#         if i < t_max-1:
#             Sf[i+1] = Sf[i]
        
#         # Slow Reservoir
#         Ss[i] = Ss[i] + Qus_dt
#         Qs_dt = dt * Ks * Ss[i]
#         Ss[i] = Ss[i] - Qs_dt
#         if i < t_max-1:
#             Ss[i+1] = Ss[i]
        
#         Q_tot_dt[i] = Qs_dt + Qf_dt
#         Qs[i] = Qs_dt 
#         Qf[i] = Qf_dt 


#     # Check Water Balance
#     Sf = Si[-1] + Ss[-1] + Sf[-1] + Su[-1]  # final storage
#     S_in = sum(S_in)  # initial storage
#     WB = sum(Prec) - sum(Ei_dt) - sum(Ea_dt) - sum(Q_tot_dt) - Sf + S_in
#     # print(WB)
#     # Offset Q

#     Weigths = Weigfun(T_lag)
    
#     Qm = np.convolve(Q_tot_dt, Weigths)
#     Qm = Qm[0:t_max]
#     forcing['Qm'] = Qm
   
#     if hydrograph == 'TRUE':
#     ## Plot
#     # hour=1:t_max\
#         fig, ax = plt.subplots(figsize=(12,8))
#         forcing['Q'].plot(label='Obserbed', ax=ax)
#         forcing['Qm'].plot(label='Model',  ax=ax)
#         ax.legend()
        

#     return Qm



if __name__ == "__main__":
    print("loaded util functions")