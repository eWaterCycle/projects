# Impact and uncertainty of Climate Change on future river discharge using the eWaterCycle platform

This repo contains a workflow that allows users to model the impact of climate change on river discharge for any river where observations of river discharge are available in the Caravan dataset [Katzert](todo:ref). The workflow is designed to be flexible and leverage the advantages of the eWaterCycle platform [ref: Hut 2022](todo:ref). The workflow is build to work with the HBV hydrological model to translate athomspheric forcing, but is easily adjustable to any hydroligcal model supported by eWaterCycle. As an example we run a climate change impact analysis for the Wallkill river in upstate New York, USA. As climate model we use the Max Planck Institute for Meteorology Earth System Model (MPI-ESM1.2, [Gutjahr 2019](https://doi.org/10.5194/gmd-12-3241-2019)). The choice of climate model is also easily changed to any model output available through ESGF [todo:ref](todo:ref).  

## Workflow description
The workflow consist of four major steps, spread out over seven jupyter notebooks. The workflow is designed such that the selection of region from caravan and climate models from ESGF are made a priori using a seperate notebook and stored in a json file. Each notebook in the workflow reads this json file. In this way no changes need to be made when the workflow is run for another region and/or another climate model. Selection of region and climate model and scenarios is done in the [step_0a_select_caravan_region_time_and_scenarios](step_0a_select_caravan_region_time_and_scenarios.ipynb) notebook. Selecting a climate model and scenarios can be daunting given the wide range of available models and scenarios. The [step_0b_select_CMIP_forcing](step_0b_select_CMIP_forcing.ipynb) provides a list of compatible models to choose from for the given model (HBV in our case).

After the selection of region and climate model in the notebook  is done, the three major steps of the workflow are generating forcing, calibrating HBV model and running HBV model. Finally, in step 4, the model output is analysed and graphs of expected impact of climate change on river discharge are made.

### Overview of the workflow
The figure below summarizes the workflow graphically.

### step 1: Generate forcing for HBV
The HBV model needs precipitation, temperature and potential evaporation information as input to calculate river discharge. These inputs are called 'forcing'. Furthermore, it has nine parameters that need to be calibrated for specific regions. Calibration is by comparing model output to observed streamflow measurements and optimizing the parameters. For calibration we use ERA5 as forcing. ERA5 is re-analyses data which has been constrained by observations to give best estimates of actual on earth weather. The climate data for histroical periods on the other hand are not constrained by observations: while climate models are made to be statistical correct, they can never match day to day values because of the chaotic nature of the athmospheric system. To analyse potential biases caused by using ERA5 for calibration and climate data for analyses, we need to analyse the differences in those data sources. Therefore, we generate:

- forcing for HBV model for the chosen region, for the period where we have discharge observations, from both ERA5 and from the historical runs of the climate model in [this](step_1a_generate_historical_forcing.ipynb) notebook.
- forcing for HBV model for the chosen region, for the future period of interest, for all climate scenarios of interest from chosen climate model in [this](step_1a_generate_future_forcing.ipynb) notebook.

Forcing is saved in a structured directory system on the users home directory for easy reading by the next steps of the workflow.

### step 2: calibrate the HBV model
Two different methods for calibration are provided. [This](step_2b_calibrate_HBV_montecarlo.ipynb) notebook provides a basic Monte Carlo calibration scheme. While this is not very computationally effective in finding the optimal paramters for a nine dimensional parameter space, it does provide a very clear overview of how the eWaterCycle platform, including the Data Assimilation extension to run ensembles of models, can be used.

A more effective way to calibrate is to use modern methods like Shuffle Complex Evolution (SCE) to systematically and efficiently work towards an optimal set of parameters. [This](step_2c_calibrate_HBV_SCE.ipynb) notebook does that. The code still leverages the eWaterCycle platforms flexibillity, but is a bit harder to read than the Monte Carlo example. The results, however, are much better and the parameters found using this method are used for the model runs. The resulting parameters are saved in a json file together with the forcing used, to make sure those stay together. 

### step 3: run HBV model to generate discharge estimates
The running of the HBV model, simple though it may be, is also split over two different notebooks. For the historical runs, where the model is forced either with ERA5 forcing data, or with climate model data, is done in [this](step_3a_model_run_historical.ipynb) notebook. This is a typical example of how the eWaterCycle platform can be used for a comparison study. The resulting estimation of river discharge is saved in netcdf files together with the forcing data so it can be easily read in the analyses step later on.

For generating the estimation of future river discharge under different climate scenarios we take a different approach in [this](step_3a_model_run_future.ipynb) notebook. Here I use the data assimilation extension to create an ensemble of model objects. This showcases how different models can be run using a single command with this extension. 

### step 4: analyse results
Finally, in [this](step_3a_model_run_historical.ipynb) notebook we load the results from the model runs and do statistical analyses to see the projected effect of climate change on the region of interest given the climate model of choice. To assess biases we first look at the statistical differences between the observed discharge, the projected discharge when using ERA5 forcing and when using climate model forcing. We use Metastatistical Extreme Value (MEV) to asses the differences in projected maximum values, which is relevant for flood forecasting. When these differences are small between discharge generated with ERA5 forcing and with climate models and when both are close to the observed values, this gives confidence that HBV model is well capable of generating accurate discharge estimations.

We than finalize by estimating the distrubtion of extreme events of river discharge for the different future climate predictions and compare these to the historical distributions. We can derive from this how much more likely we expect certain values of extreme discharge to become under different climate scenarios.

## running this workflow for a different region
To run this analysis for a different region:

- open [this step_0a](step_0a_select_caravan_region_time_and_scenarios.ipynb) notebook
- Read it through and follow the link to the online caravan map.
- Select a region of interest and copy the caravan ```basin_id```
- paste the ```basin_id``` into the right cell
- run all notebooks in order of steps.

## running this workflow for a different climate model
To run this analysis for a different (selection of) climate model(s)

- open [this step_0b](step_0b_select_CMIP_forcing.ipynb) notebook
- Change the experiments of interest if needed
- Run the notebook. Note that this can take quite some time (half an hour easily)
- choose which combination of climate model and ensemble member you want to run.
- open [this step_0a](step_0a_select_caravan_region_time_and_scenarios.ipynb) notebook
- change the cell with ```settings["CMIP_info"]``` to reflect your choices
- run all notebooks in order of steps. Note that although CMIP datasets might exist, not all servers are always online. It could be you get an error when generating climate data forcing because the server that is supposed to host the data from that particular climate model might be down.

## running this workflow for a different hydrological model
This is a bit more involved, but still doable because of the flexible nature of eWaterCycle. It is strongly suggested to first look at the 'run model' example for your model of choice, provided with the documentation of that models eWaterCycle plugin repo, before proceeding. After that:

### change settings
- in [this step_0a](step_0a_select_caravan_region_time_and_scenarios.ipynb) notebook change the base_path to reflect your model choice and to make sure you don't overwrite the output for HBV. 

### generate forcing
- Find out which parameters your model need for forcing. This should be documented in the model plugin repository. If your model can take ```lumpedmakking``` style ewatercycle forcing, skip to 'calibrate model' below
- Find out which climate models have the required parameters available using [this step_0b](step_0b_select_CMIP_forcing.ipynb) notebook.
- change the 1a and 1b notebooks to reflect your model choice. You will need to change the ```ewatercycle.foring.generate``` calls.

### calibrate model
If your model needs calibration:

- change the step 2b notebook to reflect your own model. It might be wise to first change the "run model" notebooks and subsequently change the calibration

If your model needs external parameter sets (most distributed models)

- rewrite step 2 to generate and point at the correct parameter set.

### run model
Adjust the 3a and 3b notebooks to run your model. For lumped models like HBV this might be as easy as only changing the call that generates the model object and changing the size of the parameters array. For distrubted models, usually parameter sets have to be externally provided (see above).

## Citing this work

- todo: get DOI, put citation info here
 