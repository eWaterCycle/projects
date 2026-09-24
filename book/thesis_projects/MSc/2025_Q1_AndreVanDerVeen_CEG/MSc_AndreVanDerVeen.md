# Aral Sea — André van der Veen

This repository contains the codebase, data-processing workflows, model experiments, and analysis developed for my MSc thesis in Hydrology at [TU Delft](https://www.tudelft.nl/).

* **Full Thesis:** [TU Delft Repository Link](https://repository.tudelft.nl/record/uuid:fab4adbf-1519-4648-b6f6-e9b4f6232f78)

## Abstract & Scope

The project investigates how climate change, CMIP6 future projections, and human water use affect river discharge and the water balance of the Aral Sea basin. 

It combines:
1. **Meteorological Forcing:** Processing and correction of historical and CMIP6 climate datasets.
2. **Hydrological Modeling:** **PCR-GLOBWB2** river-discharge simulations.
3. **Basin Scale Modeling:** An Aral Sea volume-balance model.

*Note: The complete thesis analysis is not yet fully automated or end-to-end reproducible from this repository alone.*

- [Overview](#overview)
- [Workflow status](#workflow-status)
- [Examples](#examples)
- [Contact](#contact)

## Overview

There are two distinct parts of this project. They serve different purposes and
should not be treated as interchangeable workflows.

### `work_in_progress/`: exploratory development

[`work_in_progress/`](./work_in_progress/) is the exploratory research
workspace. It contains intermediate, experimental, and development material,
including:

- [`data/`](./work_in_progress/data/) – raw and processed data, including
	GRDC, DAHITI, bathymetry, Karakum, and shapefile data;
- [`forcing/`](./work_in_progress/forcing/) – forcing-generation notebooks and
	generated forcing experiments;
- [`model_runs/`](./work_in_progress/model_runs/) – calibration, optimization,
	HBV, LeakyBucket, and PCR-GLOBWB experiments;
- [`notebooks/`](./work_in_progress/notebooks/) – exploratory notebooks for
	forcing, calibration, bias mapping, modelling, plotting, and utilities. These form the basis for the later final workflow.
- [`outputs/`](./work_in_progress/outputs/) – intermediate figures, tables, and
	model outputs;
- [`src/`](./work_in_progress/src/) – development Python modules for forcing,
	models, calibration, plotting, I/O, and utilities;
- [`Test_Aral/`](.//work_in_progress/Test_Aral/) – initial exploratory Aral Sea simulations and diagnostic experiments, oldest code, can be mostly disregarded;


This folder is useful for understanding the research process and finding
experimental code, but it is not the canonical reproduction path.

### `Report/`: structured thesis workflow

[`Report/`](./Report/) contains the structured workflow used for the thesis
report. Its main entrypoints and components are:

- [`README.md`](./Report/README.md) – setup, configuration, execution, outputs,
	and current limitations;
- [`Snakefile`](./Report/Snakefile) – Snakemake workflow orchestration;
- [`config_aral.yaml`](./Report/config_aral.yaml) – project paths, scenarios,
	simulation periods, parameter sets, and stations;
- [`environment.yaml`](./Report/environment.yaml) – Conda environment
	definition;
- [`config/`](./Report/config/) – experiment-planning configuration;
- [`workflow/`](./Report/workflow/) – Snakemake scripts for forcing processing
	and PCR-GLOBWB workflow steps;
- [`src/`](./Report/src/) – workflow and model helper modules;
- [`tests/`](./Report/tests/) – focused tests for workflow helpers;
- [`data/`](./Report/data/) – workflow inputs and generated forcing;
- [`results/`](./Report/results/) – workflow results and derived outputs.

The Report workflow is the recommended starting point for the documented
pipeline. It automates forcing generation, CMIP6 processing, PCR-GLOBWB
experiments, and discharge extraction. The later Aral Sea volume-balance and
final-analysis stages remain represented by incomplete example notebooks rather
than a complete set of Snakemake rules.



## Workflow status

Start with [`Report/README.md`](./Report/README.md) for the documented setup
and execution instructions. The workflow requires external datasets, model
parameter sets, and a PCR-GLOBWB container, and its configuration currently
contains machine-specific paths.

The notebooks in [`Report/notebooks/`](./Report/notebooks/) are examples of the
intended workflow. They are incomplete and may require manual edits, local
inputs, or code that has not yet been converted into Snakemake rules. Their
numbering indicates the intended order, not a guaranteed end-to-end execution
path.

## Examples

The Report notebooks provide examples of the intended analysis stages:

1. [`00_setup.ipynb`](./Report/notebooks/00_setup.ipynb)
2. [`01_forcing_generation.ipynb`](./Report/notebooks/01_forcing_generation.ipynb)
3. [`02_pcr_globwb_experiments.ipynb`](./Report/notebooks/02_pcr_globwb_experiments.ipynb)
4. [`03a_aral_sea_model_forcing_generation.ipynb`](./Report/notebooks/03a_aral_sea_model_forcing_generation.ipynb)
5. [`03b_aral_sea_model_simulation.ipynb`](./Report/notebooks/03b_aral_sea_model_simulation.ipynb)
6. [`04_figures_and_results.ipynb`](./Report/notebooks/04_figures_and_results.ipynb)


> [!NOTE]
> These notebooks serve as reference material and exploratory code samples. They are as of now incomplete and do not constitute a fully automated or complete reproducible workflow. For standard workflow execution, use the Snakemake pipeline.


## Author

* **A.B. van der Veen**
  * **ORCID:** [0009-0009-5611-8888](https://orcid.org/0009-0009-5611-8888)
  * **GitHub:** [@andrevdv](https://github.com/andrevdv)
  * **Project:** [Aral Sea Hydrology Thesis](https://github.com/andrevdv/MSc_AralSea)  
