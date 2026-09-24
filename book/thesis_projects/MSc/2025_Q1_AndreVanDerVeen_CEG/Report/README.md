# Aral Sea Modelling — Reproducable Automated Modelling Workflow for PCR-GLOBWB2 

This repository contains the workflow developed for an MSc thesis at Delft
University of Technology to model historical and future changes in Aral Sea
water levels. It combines climate forcing, PCR-GLOBWB2 river discharge
simulations, and an Aral Sea volume-balance model.

The current executable Snakemake workflow generates forcing, prepares and runs
PCR-GLOBWB experiments, and extracts and aggregates discharge results. The
notebooks in `notebooks/` are incomplete examples of the intended workflow and
analysis; they are provided as working material rather than a complete,
guaranteed-reproducible pipeline.

## Workflow

The current workflow is organised as follows:

1. Generate ERA5 forcing for the Aral Sea basin.
2. Generate CMIP6 historical and future forcing for the configured models,
	 ensemble, and SSP scenarios.
3. Regrid CMIP6 forcing to the ERA5 grid and apply bias correction.
4. Run PCR-GLOBWB2 experiments for the Amu Darya and Syr Darya catchments.
5. Extract, merge, and aggregate modelled discharge at configured stations.
6. Use the resulting discharge in the example Aral Sea volume-balance
	notebooks.
7. Produce figures and tables with the example analysis notebooks.

The first five stages are represented in the `Snakefile`. The later stages are
not yet complete Snakemake targets, and the notebooks do not provide a
complete implementation of them. Do not interpret `snakemake` completion or
successful notebook execution as completion of the entire thesis analysis.

## Repository structure

| Path | Purpose |
| --- | --- |
| `Snakefile` | Main workflow and rule dependencies |
| `config_aral.yaml` | Paths, scenarios, periods, stations, and model settings |
| `environment.yaml` | Conda environment definition |
| `config/` | Experiment planner and related configuration files |
| `src/` | Python workflow and model helpers |
| `workflow/` | Snakemake scripts for regridding and bias correction |
| `scripts/` | Supporting scripts |
| `notebooks/` | Setup, experiments, Aral Sea modelling, and figures |
| `data/` | Input data and generated forcing |
| `results/` | Run tables, model outputs, and derived results |
| `logs/` | Rule-specific logs |
| `tests/` | Unit tests for workflow helpers |



## Requirements and Installation

Install the project environment using the `environment.yaml` file:

```bash
conda env create -f environment.yaml
conda activate aral_env activate aral_env
```

The workflow also requires:

- An eWaterCycle-compatible PCR-GLOBWB container image. In my case that was definied in
	`runtime.pcrglobwb_container_image` in `config_aral.yaml`. (Current version v0.2.2 should work as well. might require slight refactoring)
- The PCR-GLOBWB parameter set referenced by the workflow, including the
	required local `.ini` files.
- The experiment planner at `config/experiment_planner.csv`.
- Basin shapefiles, GRDC observations, clone maps, and other project data in
	the locations configured under `paths`.

These resources are not all committed to this repository. Their provenance,
licences, and local paths must be recorded before sharing a fully reproducible
run.

## Configuration

Before running the workflow, edit `config_aral.yaml` for the machine being
used. In particular, update:

- `paths.project_root` and all data directories if the project is moved;
- `runtime.pcrglobwb_container_image`;
- `forcing.models`, `forcing.ensemble`, and `forcing.scenarios`;
- the simulation periods and `active_time_blocks`;
- the parameter-set paths and discharge-station configuration.

The committed configuration contains absolute paths from the development
machine and should not be copied unchanged to another environment.

## Input data

The workflow expects the following inputs:

- ERA5 and CMIP6 data obtained through the configured eWaterCycle tooling;
- the Aral Sea basin shapefile under `data/shapefiles`;
- GRDC discharge observations under `data/grdc`;
- PCR-GLOBWB clone maps and parameter files under the configured `data/`
	directories;
- any bathymetry, altimetry, or DAHITI data used by the notebooks.

The `data/` directory is the input-data location; there is no `input_data/`
directory in this project. Some input data is provided. For other data the readme files in their respective folders provide the releavant information to acquire the data.

## Running the workflow

The main workflow for forcing generation, forcing correction, and PCR-GLOBWB2 model runs is fully standardized with Snakemake, guaranteeing reproducible results across runs. 

Run the Snakemake workflow using the following commands:

Run commands from this directory. First check that the configuration and all
preflight inputs are available:

```bash
snakemake -n
```

Run the default target with four cores:

```bash
snakemake --cores 4
```

Useful targeted rules include:

```bash
snakemake --cores 4 generate_era5_forcing
snakemake --cores 4 bias_correct_future
snakemake --cores 4 expand_runs
snakemake --cores 4 pcrglobwb_experiments
snakemake --cores 4 all_karakum
```

Use `--rerun-incomplete` after an interrupted run. Rule logs are written below
`logs/`. Scripts in `workflow/` expect Snakemake's injected `snakemake` object,
so they should be executed through a Snakemake rule rather than run directly
with Python.

## Outputs

Important outputs include:

- generated forcing and completion flags under `data/forcing/`;
- the expanded experiment table at `results/runs/expanded_runs.csv`;
- PCR-GLOBWB outputs under `results/runs/pcrglobwb/`;
- merged and final station NetCDF files under `results/`;
- workflow logs under `logs/`;
- figures under `figures/` or `results/figures/`, depending on the producing
	rule or notebook.

The `.flag` files are workflow completion markers, not the forcing or model
data themselves. Inspect the corresponding NetCDF, CSV, and figure outputs for
the actual results.

For more information on Snakemake, refer to the official [Snakemake Documentation](https://snakemake.readthedocs.io/).

## Notebooks

The notebooks are examples of the intended workflow and are incomplete. 

1. [`00_setup.ipynb`](notebooks/00_setup.ipynb)
2. [`01_forcing_generation.ipynb`](notebooks/01_forcing_generation.ipynb)
3. [`02_pcr_globwb_experiments.ipynb`](notebooks/02_pcr_globwb_experiments.ipynb)
4. [`03a_aral_sea_model_forcing_generation.ipynb`](notebooks/03a_aral_sea_model_forcing_generation.ipynb)
5. [`03b_aral_sea_model_simulation.ipynb`](notebooks/03b_aral_sea_model_simulation.ipynb)
6. [`04_figures_and_results.ipynb`](notebooks/04_figures_and_results.ipynb)

The Aral Sea volume-balance simulation and final analysis are therefore not
fully automated or reproducible from this repository alone.



## Citation and licence

Please cite the thesis and the datasets and software used by a particular run.
Project citation metadata is available in [`CITATION.cff`](CITATION.cff). The
repository-level [`LICENSE`](../../../../../LICENSE) applies to the repository;
third-party datasets and model software may have separate terms that must be
followed.

Relevant external resources include ERA5, CMIP6, PCR-GLOBWB, eWaterCycle,
GRDC, and any DAHITI or bathymetry products used in the analysis.



## Author

* **A.B. van der Veen**
  * **ORCID:** [0009-0009-5611-8888](https://orcid.org/0009-0009-5611-8888)
  * **GitHub:** [@andrevdv](https://github.com/andrevdv)