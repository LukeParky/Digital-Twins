# -*- coding: utf-8 -*-
"""
This script handles the reading of REC1 data from the NIWA REC1 dataset,
storing the data in the database, and retrieving the REC1 data from the database.
"""

import logging
import pathlib

import geopandas as gpd
import pandas as pd
from sqlalchemy.engine import Engine

from src import config
from src.digitaltwin.tables import check_table_exists
from src.dynamic_boundary_conditions.river.river_network_to_from_db import add_network_exclusions_to_db

log = logging.getLogger(__name__)


def get_niwa_rec1_data() -> gpd.GeoDataFrame:
    """
    Reads REC1 data from the NIWA REC1 dataset and returns a GeoDataFrame.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame containing the REC1 data from the NZ REC1 dataset.

    Raises
    ------
    FileNotFoundError
        If the REC1 data directory does not exist or if there are no Shapefiles in the specified directory.
    """
    # Get the REC1 data directory from the environment variable
    rec1_data_dir = config.get_env_variable("DATA_DIR_REC1", cast_to=pathlib.Path)
    # Check if the REC1 data directory exists
    if not rec1_data_dir.exists():
        raise FileNotFoundError(f"REC1 data directory not found: {rec1_data_dir}")
    # Check if there are any Shapefiles in the specified directory
    if not any(rec1_data_dir.glob("*.shp")):
        raise FileNotFoundError(f"REC1 data files not found: {rec1_data_dir}")
    # Find the path of the first file in `rec1_data_dir` that ends with .shp
    rec1_file_path = next(rec1_data_dir.glob('*.shp'))
    # Read the Shapefile into a GeoDataFrame
    rec1_nz = gpd.read_file(rec1_file_path)
    # Convert column names to lowercase for consistency
    rec1_nz.columns = rec1_nz.columns.str.lower()
    return rec1_nz


def store_rec1_data_to_db(engine: Engine) -> None:
    """
    Store REC1 data to the database.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.

    Returns
    -------
    None
        This function does not return any value.
    """
    # Define the table name for storing the REC1 data
    table_name = "rec1_data"
    # Check if the table already exists in the database
    if check_table_exists(engine, table_name):
        log.info(f"Table '{table_name}' already exists in the database.")
    else:
        # Get REC1 data from the NZ REC1 dataset
        rec1_nz = get_niwa_rec1_data()
        # Store the REC1 data to the database table
        rec1_nz.to_postgis(table_name, engine, index=False, if_exists="replace")
        log.info(f"Stored '{table_name}' data in the database.")


def get_sdc_data_from_db(engine: Engine, catchment_area: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Retrieve sea-draining catchment data from the database that intersects with the given catchment area.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    catchment_area : gpd.GeoDataFrame
        A GeoDataFrame representing the catchment area.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame containing sea-draining catchment data that intersects with the given catchment area.
    """
    # Extract the geometry of the catchment area
    catchment_polygon = catchment_area["geometry"][0]
    # Query to retrieve sea-draining catchments that intersect with the catchment polygon
    sea_drain_query = f"""
    SELECT *
    FROM sea_draining_catchments AS sdc
    WHERE ST_Intersects(sdc.geometry, ST_GeomFromText('{catchment_polygon}', 2193));
    """
    # Execute the query and create a GeoDataFrame from the result
    sdc_data = gpd.GeoDataFrame.from_postgis(sea_drain_query, engine, geom_col="geometry")
    return sdc_data


def get_rec1_data_with_sdc_from_db(
        engine: Engine,
        catchment_area: gpd.GeoDataFrame,
        river_network_id: int) -> gpd.GeoDataFrame:
    """
    Retrieve REC1 data from the database for the specified catchment area with an additional column that identifies
    the associated sea-draining catchment for each REC1 geometry.
    Simultaneously, identify the REC1 geometries that do not fully reside within sea-draining catchments and
    proceed to add these excluded REC1 geometries to the appropriate database table.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    catchment_area : gpd.GeoDataFrame
        A GeoDataFrame representing the catchment area.
    river_network_id : int
        An identifier for the river network associated with the current run.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame containing the retrieved REC1 data for the specified catchment area with an additional column
        that identifies the associated sea-draining catchment for each REC1 geometry.
    """
    # Get sea-draining catchment data from the database
    sdc_data = get_sdc_data_from_db(engine, catchment_area)
    # Unify the sea-draining catchment polygons into a single polygon
    sdc_polygon = sdc_data.unary_union
    # Create a GeoDataFrame representing the unified sea-draining catchment area
    sdc_area = gpd.GeoDataFrame(geometry=[sdc_polygon], crs=sdc_data.crs)
    # Combine the sea-draining catchment area with the input catchment area to create a final unified polygon
    combined_polygon = pd.concat([sdc_area, catchment_area]).unary_union
    # Query to retrieve REC1 data that intersects with the combined polygon
    rec1_query = f"""
    SELECT *
    FROM rec1_data AS rec
    WHERE ST_Intersects(rec.geometry, ST_GeomFromText('{combined_polygon}', 2193));
    """
    # Execute the query and retrieve the REC1 data from the database
    rec1_data = gpd.GeoDataFrame.from_postgis(rec1_query, engine, geom_col="geometry")
    # Determine the sea-draining catchment for each REC1 geometry (using the 'within' predicate)
    rec1_data_join_sdc = (
        gpd.sjoin(rec1_data, sdc_data[["catch_id", "geometry"]], how="left", predicate="within")
        .drop(columns=['index_right'])
    )
    # Get rows where REC1 geometries are fully contained within sea-draining catchments
    rec1_data_with_sdc = rec1_data_join_sdc[~rec1_data_join_sdc['catch_id'].isna()]
    # Remove any duplicate records and sort by the 'objectid' column
    rec1_data_with_sdc = rec1_data_with_sdc.drop_duplicates().sort_values(by="objectid").reset_index(drop=True)
    # Convert the 'catch_id' column to integers
    rec1_data_with_sdc['catch_id'] = rec1_data_with_sdc['catch_id'].astype(int)
    # Get the object IDs of REC1 geometries that are not fully contained within sea-draining catchments
    rec1_network_exclusions = rec1_data_join_sdc[rec1_data_join_sdc['catch_id'].isna()].reset_index(drop=True)
    # Add excluded REC1 geometries in the River Network to the relevant database table
    add_network_exclusions_to_db(engine, river_network_id, rec1_network_exclusions,
                                 exclusion_cause="crossing multiple sea-draining catchments")
    return rec1_data_with_sdc
