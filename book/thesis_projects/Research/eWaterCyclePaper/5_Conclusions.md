# Conclusions

We have introduced the eWaterCycle platform for FAIR and open hydrological modeling. Using eWaterCycle, hydrologists can easily build on each other's work by using each other's models, data and experiments in a manner that is “FAIR by design”. Using the online eWaterCycle platform, hydrologists do not have to install, download or pre-process anything before they can start computational hydrological experiments.

The eWaterCycle platform implements the “FAIR” principles as follows.

- Findable. The data and models must be findable. Through the explorer, all available models and datasets are exposed in an easily findable manner. The documentation (Verhoeven et al., 2021b) further specifies all available models, datasets and their properties.
- Accessible. The data and models must be accessible. By making the entire software-stack of the eWaterCycle platform open source and by only including models and datasets that are also openly available, it is possible for anyone with sufficient computational infrastructure to install and run an instance of the eWaterCycle platform. For those without these resources, the eWaterCycle team (i.e., the authors of this paper) currently hosts an instance of the eWaterCycle platform on demonstration hardware provided by SURF. Access to this version can be obtained through contact with the authors. In the near future, the eWaterCycle team is hoping to acquire funds to more sustainably offer an instance of eWaterCycle to the entire hydrological community.
- Interoperable. The data and models must be interoperable. The eWaterCycle platform uses open interfaces between the different parts of the platform (e.g., grpc4bmi) to communicate between experiments in Jupyter notebooks and the hydrological models in containers. The use of open interfaces and containers makes it easy to connect to a dataset or a model and use it for a different study.
- Reusable. The data and models must be reusable. The experiments in eWaterCycle, as contained in Jupyter notebooks, are separate entities from the models and datasets. Because of this separation and the open interfaces between components, reuse of data, models or (parts of) experiments is facilitated.
As laid out in Sect. 1, currently an ecosystem of services is emerging that makes it easier for hydrologists to do computational research, with each service focusing on different parts of the hydrological research cycle (Tucker et al., 2022; Tarboton et al., 2014). In this ecosystem, eWaterCycle is developed as a platform on which hydrologists can execute their computational hydrological experiments. In this paper, we have presented the core components of the eWaterCycle platform, the explorer, the notebook environment, and the underlying technology to deal with models and datasets in a FAIR manner. The hydrological community can install the openly and freely available eWaterCycle platform on their own infrastructure. The eWaterCycle team (i.e., the authors of this paper) are attracting sustainable funding to provide an online place where more researchers will be able to execute their computational hydrological research and education.

For future development, integration with other platforms that facilitate hydrological research is foreseen, most notably coupling to models from CSDMS, sharing and retrieving data from Hydroshare, integrating higher-level interfaces to models, such as PyMT, and giving access to libraries that facilitate additional types of research such as the data assimilation software OpenDA.

The use cases presented in this paper give an overview of the type of research that the eWaterCycle platform can facilitate, from model selection to coupling and calibration. The eWaterCycle platform is set up as a modular collection of services that together form a complete platform. By making sure that the individual modules contain as few assumptions about hydrology as possible (those are represented in the models and experiments), we are working towards the goal of making the technologies developed for the eWaterCycle platform portable to other domains of (geo)science where researchers work with each other's models and datasets.

Hutton et al. (2016) argued that computational hydrology can only be a proper science if the hydrological community makes sure that hydrological model studies are executed and presented in a reproducible manner. We replied that to improve current practices for hydrologists using hydrological models in their work, hydrologists should not “re-invent the water wheel” but instead use existing technology from other fields, such as containers and the ESMValTool, and open interfaces, such as BMI, to do their computational science (Hut et al., 2017). With this paper and the release of the eWaterCycle platform, we are putting our money where our mouth is and providing the hydrological community with a “FAIR by design” platform to do science.

## Code and data availability
The eWaterCycle platform is fully open source. In this paper we have first and foremost introduced the eWaterCycle package itself, which is available through Verhoeven et al. (2021b) (DOI: https://doi.org/10.5281/zenodo.5119390). The notebooks used as case studies in this paper are available through Hut et al. (2021) (DOI: https://doi.org/10.5281/zenodo.5543899). Instructions on how to install the eWaterCycle platform on one's own infrastructure, aimed at system administrators, is available through Verhoeven et al. (2021a) (DOI: https://doi.org/10.5281/zenodo.5356689).

## Video supplement
For scientists who want to work with the platform as users, a separate video where a hands-on demonstration of the models is given is available on YouTube (https://youtu.be/eE75dtIJ1lk, last access: 28 June 2022), and for archiving purposes it is also available on Zenodo (https://doi.org/10.5281/zenodo.5556433, Hut, 2021).

## Author contributions
All authors have jointly implemented and tested the various components of the eWaterCycle platform. RH, ND, BvW, NvdG, JA, FA, BoA​​​​​​​, JC, YD, RvH​​​​​​​, PK and SV designed the eWaterCycle platform. RH, ND, JA, FA, BoA, JC, YD, RvH, TS, PK, SV, EH, MvM, GvdO, IP, StS, MdV and BW contributed code, models or datasets to the eWaterCycle package. RH designed the use cases, with TA contributing his BSc thesis work to use case 3. RH drafted the first version of this paper with input from ND, NvdG, BW and JA. RH, ND, BvW and NvdG are co-PIs of the eWaterCycle II project.

## Competing interests
The contact author has declared that neither they nor their co-authors have any competing interests.

## Disclaimer
Publisher's note: Copernicus Publications remains neutral with regard to jurisdictional claims in published maps and institutional affiliations.

## Acknowledgements
We thank all the participants of the Lorentz Center workshop “FAIR Hydrological Models”, whose input as members of the hydrological community has shaped the eWaterCycle platform. We furthermore want to thank the members of the eScience Advisory Committee (eSAC) for their continued feedback during the eWaterCycle project.

## Financial support
This research has been supported by the Netherlands eScience Center (grant no. 027.017.F01).

## Review statement
This paper was edited by Andrew Wickert and reviewed by two anonymous referees.




