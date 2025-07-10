![](almos/icons/almos_logo.png)
#
## <p align="center"> ALMOS (Active Learning Molecular Selection)</p>

[![CircleCI](https://img.shields.io/circleci/build/github/MiguelMartzFdez/almos?label=Circle%20CI&logo=circleci)](https://app.circleci.com/pipelines/github/MiguelMartzFdez/almos)
[![Codecov](https://img.shields.io/codecov/c/github/MiguelMartzFdez/almos?label=Codecov&logo=codecov)](https://codecov.io/gh/MiguelMartzFdez/almos)
[![Downloads](https://pepy.tech/badge/almos-kit)](https://pepy.tech/project/almos-kit)
[![Read the Docs](https://img.shields.io/readthedocs/almos?label=Read%20the%20Docs&logo=readthedocs)](https://almos.readthedocs.io/)
[![PyPI](https://img.shields.io/pypi/v/almos-kit)](https://pypi.org/project/almos-kit/)

## Recommended installation
1. (Only once) Create new conda environment: `conda create -n almos python=3.10` 
2. Activate conda environment: `conda activate almos`  
3. Install ALMOS using pip: `pip install almos-kit`
4. Install libraries necesaries for ROBERT `conda install -y -c conda-forge glib gtk3 pango mscorefonts`
5. (Only for AQME workflow uses) Install libraries necesaries for AQME `conda install -y -c conda-forge openbabel=3.1.1 xtb=6.7.1`
6. (Only for compatible devices) Install Intelex accelerator: `pip install scikit-learn-intelex==2025.2.0` 
* Inexperienced users should visit the *Users with no Python experience* section in [Read the Docs](https://almos.readthedocs.io).

## Quick installation using Conda environment file

You can install ALMOS and all required dependencies in one step using the provided Conda environment file:

```bash
curl -O https://raw.githubusercontent.com/MiguelMartzFdez/almos/miguel/install/almos.yaml
conda env create -f almos.yaml
conda activate almos

## Update the program
1. Update to the latest version: `pip install almos-kit --upgrade`

## Developers and help desk  
List of main developers and contact emails:
  - [ ] [Miguel Martinez Fernandez](https://orcid.org/0009-0002-8538-7250). Contact [miguel.martinez@csic.es](mailto:miguel.martinez@csic.es)
  - [ ] [Susana P. García Abellán](https://orcid.org/0000-0002-3138-5527). Contact [sg.abellan@csic.es](mailto:sg.abellan@csic.es)
  - [ ] [David Dalmau Ginesta](https://orcid.org/0000-0002-2506-6546). Contact: [ddalmau@unizar.es](mailto:ddalmau@unizar.es)
  - [ ] [Juan V. Alegre-Requena](https://orcid.org/0000-0002-0769-7168). Contact: [jv.alegre@csic.es](mailto:jv.alegre@csic.es)  

For suggestions and improvements of the code (greatly appreciated!), please reach out through the issues and pull requests options of Github.  

## License
ALMOS is freely available under an [MIT](https://opensource.org/licenses/MIT) License
