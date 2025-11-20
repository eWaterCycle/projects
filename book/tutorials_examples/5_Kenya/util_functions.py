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

def get_station_names():
    directory =  "/data/shared/climate-data/camels_africa/kenya/camel_data"
    station_names = dict()

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith("Day.csv"):
                # print(file)
                camel_id = "AF_" + str(float(file[:7]))
                # print(camel_id)
                # print(root)
                filepath = os.path.join(root, "attributes/attributes_other_AF.csv")

                df = pd.read_csv(filepath)

                gauge_lookup = df.set_index('gauge_id')['gauge_name']
                # print(gauge_lookup.at[camel_id])
                station_name = gauge_lookup.at[camel_id]
                
                station_names[station_name] = camel_id

    return (dict(sorted(station_names.items())))

stations_dict = get_station_names()

def stations_map(stations_dict):
    # Your dictionary: station_name -> id
    station_names = stations_dict
    
    # Folder with shapefiles
    shapefile_dir = "/data/shared/climate-data/camels_africa/kenya/camel_data/shapefiles"
    
    # Load all shapefiles into one GeoDataFrame
    gdfs = []
    
    for name, sid in station_names.items():
        shapefile_path = shapefile_dir + f"/AF_{int(str(sid[3:-2]))}" + f"/AF_{int(str(sid[3:-2]))}.shp"
        # print(shapefile_path)
        gdf = gpd.read_file(shapefile_path)
        gdf["Station Name"] = name
        gdf["Station ID"] = sid
        gdfs.append(gdf)

    # print(gdfs)
    # Combine all into one GeoDataFrame
    all_gdf = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)

    # Get map center
    map_center = all_gdf.geometry.unary_union.centroid.coords[:][0][::-1]  # (lat, lon)
    
    # Create folium map
    m = folium.Map(location=map_center, zoom_start=6)
    
    # Add stations with popups
    for _, row in all_gdf.iterrows():
        geojson = folium.GeoJson(
            row.geometry,
            name=f"{row['Station Name']} ({row['Station ID']})",
            tooltip=folium.Tooltip(f"{row['Station Name']} ({row['Station ID']})"),
            popup=folium.Popup(f"<strong>{row['Station Name']}</strong><br>ID: {row['Station ID']}", max_width=300),
            style_function=lambda x: {
                'fillColor': '#3186cc',
                'color': '#3186cc',
                'weight': 2,
                'fillOpacity': 0.2
            }
        )
        geojson.add_to(m)

        folium.Marker(
            location=[row.lat_org, row.long_org],
            tooltip=f"{row['Station Name']} ({row['Station ID']})",
            popup=folium.Popup(f"<strong>{row['Station Name']}</strong><br>ID: <code>{row['Station ID']}</code>", max_width=300)
        ).add_to(m)
    
    display(m)

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

def plot_hydrograph(I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks, model, forcing):
    Sin = np.array([0,  100,  0,  5  ])
    Par = np.array([I_max, Ce, Su_max, beta, P_max, T_lag, Kf, Ks])
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

    # Create sliders with the specified min and max values
    sliders = {
        'I_max': FloatSlider(min=params['I_max']['min'], max=params['I_max']['max'], step=0.1, value=I_max),
        'Ce': FloatSlider(min=params['Ce']['min'], max=params['Ce']['max'], step=0.01, value=Ce),
        'Su_max': FloatSlider(min=params['Su_max']['min'], max=params['Su_max']['max'], step=1, value=Su_max),
        'beta': FloatSlider(min=params['beta']['min'], max=params['beta']['max'], step=0.1, value=beta),
        'P_max': FloatSlider(min=params['P_max']['min'], max=params['P_max']['max'], step=0.001, value=P_max),
        'T_lag': IntSlider(min=params['T_lag']['min'], max=params['T_lag']['max'], step=1, value=T_lag),
        'Kf': FloatSlider(min=params['Kf']['min'], max=params['Kf']['max'], step=0.01, value=Kf),
        'Ks': FloatSlider(min=params['Ks']['min'], max=params['Ks']['max'], step=0.0001, value=Ks, readout_format='.3f')
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
                model=model, 
                forcing=forcing
            )



def HBV(Par,forcing,S_in, hydrograph):
    # HBVpareto Calculates values of 3 objective functions for HBV model

    I_max = Par[0]
    Ce = Par[1]
    Su_max = Par[2]
    beta = Par[3]
    P_max = Par[4]
    T_lag = Par[5]
    Kf = Par[6]
    Ks = Par[7]
    

    Prec = forcing['P'].values
    Qo = forcing['Q'].values
    Etp = forcing['PE'].values


    t_max = len(Prec)
    
    # Allocate Si, Su, Sf, Ss, Ei_dt, Ea_dt, Q_tot_dt
    
    Si = np.zeros(t_max)
    Su = np.zeros(t_max)
    Sf = np.zeros(t_max)
    Ss = np.zeros(t_max)
    Ei_dt = np.zeros(t_max)
    Ea_dt =  np.zeros(t_max)
    Q_tot_dt = np.zeros(t_max)
    Qs = np.zeros(t_max)
    Qf = np.zeros(t_max)
    
    # Initialize Si, Su, Sf, Ss
    Si[0] = S_in[0]
    Su[0] = S_in[1]
    Sf[0] = S_in[2]
    Ss[0] = S_in[3]

    dt = 1

    #
    # Model 1 SOF1
    for i in range(0, t_max):
        P_dt = Prec[i] * dt
        Ep_dt = Etp[i] * dt
        
        # Interception Reservoir
        if P_dt > 0:
            Si[i] = Si[i] + P_dt 
            Pe_dt = np.maximum(0, (Si[i] - I_max) / dt)
            Si[i] = Si[i] - Pe_dt
            Ei_dt[i] = 0
        else:
        # Evaporation only when there is no rainfall
            Pe_dt = np.maximum(0, (Si[i] - I_max) / dt) #is zero, because of no rainfall
            Ei_dt[i] = np.minimum(Ep_dt, Si[i] / dt)
            Si[i] = Si[i] - Pe_dt - Ei_dt[i]
        
        if i < t_max-1:
            Si[i+1] = Si[i]
        
        
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
        Qf_dt = dt * Kf * Sf[i]
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
    Sf = Si[-1] + Ss[-1] + Sf[-1] + Su[-1]  # final storage
    S_in = sum(S_in)  # initial storage
    WB = sum(Prec) - sum(Ei_dt) - sum(Ea_dt) - sum(Q_tot_dt) - Sf + S_in
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

def create_forcing_data_HBV_from_nc(start_date, end_date, camel_id):
    central_path =  "/data/shared/climate-data/camels_africa/kenya/camel_data"
    path_to_save = Path.home() / "my_data/workshop_kenya"
    path_to_save.mkdir(exist_ok=True, parents=True)
    shape_file = central_path + "/shapefiles" + f"/{str(camel_id[:-2])}" + f"/{str(camel_id[:-2])}.shp"
    data_file_nc = central_path + (f"/{camel_id}.nc")

    my_data_nc = xr.open_dataset(data_file_nc, engine="netcdf4")
    
    start_date_nc = pd.to_datetime(start_date.split("T")[0])
    end_date_nc = pd.to_datetime(end_date.split("T")[0])
    
    my_data_nc = my_data_nc.sel(date=slice(start_date_nc, end_date_nc))
    my_data_nc = my_data_nc.rename({
        'total_precipitation_sum': 'pr',
        'surface_net_solar_radiation_mean': 'rsds',
        'temperature_2m_mean': 'tas',
        'date': 'time',
        'potential_evaporation_sum_ERA5_LAND': 'evspsblpot',
        'streamflow': 'Q'
    })
    
    my_data_nc_pr = my_data_nc["pr"]
    my_data_nc_rsds = my_data_nc["rsds"]
    my_data_nc_tas = my_data_nc["tas"]
    my_data_nc_potevap = my_data_nc["evspsblpot"]
    my_data_nc_discharge = my_data_nc["Q"]
    
    # print(my_data_nc_rsds)
    my_data_nc_pr.to_netcdf(path_to_save / "pr.nc")
    my_data_nc_rsds.to_netcdf(path_to_save / "rsds.nc")
    my_data_nc_tas.to_netcdf(path_to_save / "tas.nc")
    my_data_nc_potevap.to_netcdf(path_to_save / "evspsblpot.nc")
    my_data_nc_discharge.to_netcdf(path_to_save / "Q.nc")

    forcing_dict = dict()
    forcing_dict["pr"] = str(path_to_save / "pr.nc")
    forcing_dict["rsds"] = str(path_to_save / "rsds.nc")
    forcing_dict["tas"] = str(path_to_save / "tas.nc")
    forcing_dict["evspsblpot"] = str(path_to_save / "evspsblpot.nc")
    forcing_dict["Q"] = str(path_to_save / "Q.nc")

    forcing = ewatercycle.forcing.sources["LumpedMakkinkForcing"](
        directory=path_to_save,
        start_time=start_date,
        end_time=end_date,
        shape=shape_file,
        # Additional information about the external forcing data needed for the model configuration
        filenames=forcing_dict,
        # postprocessor=derive_e_pot,  # post-processing function that adds e_pot
    )
    
    return forcing

def load_data_HBV_local(HBV_data):
    central_path = Path.home() / "my_data/workshop_kenya"
    # forcing = pd.DataFrame()
    # print( HBV_data['Q'] )

    # Load NetCDF variables
    P = xr.open_dataset(HBV_data['pr'], engine="netcdf4")['pr']
    PE = xr.open_dataset(HBV_data['evspsblpot'], engine="netcdf4")['evspsblpot']
    Q = xr.open_dataset(HBV_data['Q'], engine="netcdf4")['Q']  # Assuming variable is named 'Q'
    
    # Convert to pandas Series
    P_series = P.to_series()
    PE_series = PE.to_series()
    Q_series = Q.to_series()
    
    # Combine into a DataFrame
    calibrate_forcing = pd.DataFrame({
        'P': P_series,
        'PE': PE_series,
        'Q': Q_series
    })

    
    # forcing['P'] = xr.open_dataset(HBV_data['pr'], engine="netcdf4")
    # forcing['PE'] = xr.open_dataset(HBV_data['evspsblpot'], engine="netcdf4")
    # forcing['Q'] = xr.open_dataset(HBV_data['Q'], engine="netcdf4")

    # print(calibrate_forcing)
    return calibrate_forcing


if __name__ == "__main__":
    print("loaded util functions")