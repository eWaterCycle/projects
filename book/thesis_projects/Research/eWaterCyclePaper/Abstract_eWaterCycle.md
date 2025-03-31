# The eWaterCycle platform for open and FAIR hydrological collaboration

## Abstract

Hutton et al. (2016) argued that computational hydrology can only be a proper science if the hydrological community makes sure that hydrological model studies are executed and presented in a reproducible manner. Hut, Drost and van de Giesen replied that to achieve this hydrologists should not “re-invent the water wheel” but rather use existing technology from other fields (such as containers and ESMValTool) and open interfaces (such as the Basic Model Interface, BMI) to do their computational science (Hut et al., 2017). 
With this paper and the associated release of the eWaterCycle platform and software package (available on [Zenodo](https://doi.org/10.5281/zenodo.5119389), Verhoeven et al., 2022), we are putting our money where our mouth is and providing the hydrological community with a “FAIR by design” (FAIR meaning findable, accessible, interoperable, and reproducible) platform to do science.

The eWaterCycle platform separates the experiments done on the model from the model code. In eWaterCycle, hydrological models are accessed through a common interface (BMI) in Python and run inside of software containers. In this way all models are accessed in a similar manner facilitating easy switching of models, model comparison and model coupling. 
Currently, the following models and model suites are available through eWaterCycle: PCR-GLOBWB 2.0, wflow, Hype, LISFLOOD, MARRMoT, and WALRUS While these models are written in different programming languages they can all be run and interacted with from the Jupyter notebook environment within eWaterCycle. Furthermore, the pre-processing of input data for these models has been streamlined by making use of ESMValTool. 
Forcing for the models available in eWaterCycle from well-known datasets such as ERA5 can be generated with a single line of code. To illustrate the type of research that eWaterCycle facilitates, this paper includes five case studies: from a simple “hello world” where only a hydrograph is generated to a complex coupling of models in different languages.

In this paper we stipulate the design choices made in building eWaterCycle and provide all the technical details to understand and work with the platform. 
For system administrators who want to install eWaterCycle on their infrastructure we offer a separate installation guide. 
For computational hydrologists that want to work with eWaterCycle we also provide a video explaining the platform from a user point of view (https://youtu.be/eE75dtIJ1lk, last access: 28 June 2022).

With the eWaterCycle platform we are providing the hydrological community with a platform to conduct their research that is fully compatible with the principles of both Open Science and FAIR science.

How to cite. 

Hut, R., Drost, N., van de Giesen, N., van Werkhoven, B., Abdollahi, B., Aerts, J., Albers, T., Alidoost, F., Andela, B., Camphuijsen, J., Dzigan, Y., van Haren, R., Hutton, E., Kalverla, P., van Meersbergen, M., van den Oord, G., Pelupessy, I., Smeets, S., Verhoeven, S., de Vos, M., and Weel, B.: The eWaterCycle platform for open and FAIR hydrological collaboration, Geosci. Model Dev., 15, 5371–5390, https://doi.org/10.5194/gmd-15-5371-2022, 2022.