import xarray as xr

# Check NorESM2-LM calendar
ds = xr.open_dataset("/home/avandervee3/aral_sea_full_project/data/forcing/CMIP6/historical/raw/NorESM2-LM/r1i1p1f1/1940-2014/AralSea_basin/work/diagnostic/script/pcrglobwb_CMIP6_NorESM2-LM_day_historical_r1i1p1f1_tas_gn_1940-2014_AralSea_basin.nc")
print("---------------------- \n")
print("CMIP6 NorESM2-LM encoding:")
print(ds.time.encoding)
print("calendar: = " + str(ds.time.dt.calendar) if hasattr(ds.time.dt, 'calendar') else "Calendar not found")
print("---------------------- \n")
# Check ERA5 calendar
era5 = xr.open_dataset("/home/avandervee3/aral_sea_full_project/data/forcing/ERA5/raw/1940-2020/AralSea_basin/work/diagnostic/script/pcrglobwb_OBS6_ERA5_reanaly_1_day_tas_1940-2020_AralSea_basin.nc")
print("ERA5 encoding:")
print(era5.time.encoding)
print("calendar: = " + str(era5.time.dt.calendar) if hasattr(era5.time.dt, 'calendar') else "Calendar not found")