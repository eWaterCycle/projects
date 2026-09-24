# GRDC reference data

## Overview
This folder contains reference discharge data from the Global Runoff Data Centre (GRDC) used in the hydrological analysis of the Aral Sea basin. The data support water balance evaluation and comparison with modelled river discharge from the Amu Darya and Syr Darya rivers.

## Data source
Data are obtained from the GRDC Data Portal:

https://portal.grdc.bafg.de/applications/public.html?publicuser=PublicUser#dataDownload/Subregions

Selected subregions:
- Syr Darya
- Amu Darya

## Contents
- `README.md`: documentation of dataset usage and provenance
- GRDC discharge if added by user

## Usage in workflow
GRDC data are used as observational reference data for:
- validation of simulated river discharge
- comparison with modelled discharge
- calibration

## Notes
- Data availability depends on selected GRDC stations and reporting periods.
- This folder is intended for reference data only and is not modified during model runs.
- workflow uses both the monthly and the daily data (.txt files)

## References
Global Runoff Data Centre (GRDC): https://grdc.bafg.de/