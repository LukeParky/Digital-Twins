# Digital-Twins

## Introduction

The digitaltwin repository is designed to store APIs and local copy of data for the required Area of Interest provided by LINZ, ECAN, Stats NZ, KiwiRail, and LRIS in PostgreSQL.
User needs to pass values to the api_records function: 
1. Name of the dataset e.g. 104400-lcdb-v50-land-cover, 101292-nz-building-outlines. **Note:** make sure the names are unique.
2. name of the region which is by default set to New Zealand but can be changed to regions e.g. Canterbury, Otago, etc. (regions can be further extended to other countries in future)
3. Geometry column name of the dateset, if required. for isntance, for all LDS property and ownership, street address and geodetic data the geometry column is ‘shape’. For most other layers including Hydrographic and Topographic data, the column name is 'GEOMETRY'. For more info: https://www.linz.govt.nz/data/linz-data-service/guides-and-documentation/wfs-spatial-filtering 
4. If user is interested in a recent copy of the data, name of website must be specified to get the recent modified date of the dataset. See instructions.json
5. finally enter the api which you want to store in a database.
![image](https://user-images.githubusercontent.com/86580534/133012962-86d117f9-7ee7-4701-9497-c50484d5cdc7.png)

Currently the tables store vector data only but will be extended to LiDAR and raster data.It allows a user to download the vector data from different data providers where data is publicly available and store data from an area of interest (Polygon) into a database. Currently data is fetched from LINZ, ECAN, Stats NZ, KiwiRail, and LRIS but will be extended to other sources.

## Requirements
* [Python3](https://www.python.org/downloads/)
* [pip](https://pypi.org/project/pip/) (**P**ip **I**nstalls **P**ackages - Python package manager)
* [PostgreSQL](https://www.postgresql.org/download/) 

## Required Credentials:
* Stats NZ API KEY: https://datafinder.stats.govt.nz/my/api/

## Create extensions in PostgreSQL:
* Install Postgresql and selet PostGIS application to install along with PostgreSQL 
* ![image](https://user-images.githubusercontent.com/86580534/133153382-3a5c1069-2e65-4938-933f-5c305515fc58.png)
* Open pgAdmin 4 and set your password which will be used for connecting to PostgreSQL using Python
* Create Database 'datasourceapis' as shown below:
* ![image](https://user-images.githubusercontent.com/86580534/133153639-3b21aec0-1eb3-45de-8f73-b5caa5b102ee.png)          ![image](https://user-images.githubusercontent.com/86580534/133153696-fc992bbb-2de4-443a-beaa-a92a5c176bc1.png)
* Within a created a database, create PostGIS extension as shown below:
* ![image](https://user-images.githubusercontent.com/86580534/133153968-0d65230f-2b5d-4686-b115-2c354f66f04e.png)          ![image](https://user-images.githubusercontent.com/86580534/133154073-4e1702f8-866c-45a3-a8aa-4c1a505cf9b4.png)
* Once the extension is created, spatial_ref_sys table will appear under tables as shown below:
* ![image](https://user-images.githubusercontent.com/86580534/133154207-a8e5c181-7a8d-4a4a-81ce-aeae930e9593.png)

## Create environment to run the packages

In order to run the codes, run the following command in your Anaconda Powershell Prompt. 

```bash
conda env create -f create_new_env_window.yml
conda activate digitaltwin
pip install git+https://github.com/Pooja3894/Digital-Twins.git
```
### run codes locally

1. Open Anaconda Powershell Prompt
2. run the command 
```bash 
conda activate digitaltwin
spyder
```
3. In Spyder IDE: Go to 'Run>Configuration per file>Working directory settings
   Select 'The following directory:' option and speicify the root of the directory 
   
   ![image](https://user-images.githubusercontent.com/86580534/133013167-c7e4541a-5723-4a76-9344-25f9f835b986.png)

