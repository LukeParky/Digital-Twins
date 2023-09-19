# -*- coding: utf-8 -*-
"""
Store the rainfall data for all the sites within the catchment area in the database.
"""

import logging
from typing import List

import pandas as pd
import geopandas as gpd
from sqlalchemy.engine import Engine

from src.digitaltwin import tables
from src.dynamic_boundary_conditions import rainfall_data_from_hirds

log = logging.getLogger(__name__)


def db_rain_table_name(idf: bool) -> str:
    """
    Return the relevant rainfall data table name used in the database.

    Parameters
    ----------
    idf : bool
        Set to False for rainfall depth data, and True for rainfall intensity data.

    Returns
    -------
    str
        The relevant rainfall data table name.
    """
    # Determine the table name based on the idf parameter
    table_name = "rainfall_depth" if idf is False else "rainfall_intensity"
    return table_name


def get_sites_id_in_catchment(sites_in_catchment: gpd.GeoDataFrame) -> List[str]:
    """
    Get the rainfall site IDs within the catchment area.

    Parameters
    ----------
    sites_in_catchment : gpd.GeoDataFrame
        Rainfall site coverage areas (Thiessen polygons) that intersect or are within the catchment area.

    Returns
    -------
    List[str]
        The rainfall site IDs within the catchment area.
    """
    # Extract the site IDs from the "site_id" column of the sites_in_catchment GeoDataFrame
    sites_id_in_catchment = sites_in_catchment["site_id"].tolist()
    return sites_id_in_catchment


def get_sites_id_not_in_db(engine: Engine, sites_id_in_catchment: List[str], idf: bool) -> List[str]:
    """
    Get the list of rainfall site IDs that are within the catchment area but not in the database.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    sites_id_in_catchment : List[str]
        Rainfall site IDs within the catchment area.
    idf : bool
        Set to False for rainfall depth data, and True for rainfall intensity data.

    Returns
    -------
    List[str]
        The rainfall site IDs within the catchment area but not present in the database.
    """
    # Get the relevant rainfall data table name from the idf parameter
    rain_table_name = db_rain_table_name(idf)
    # Construct the query to retrieve the distinct site IDs from the rainfall data table
    query = f"SELECT DISTINCT site_id FROM {rain_table_name};"
    # Execute the query and retrieve the site IDs in the database as a DataFrame
    sites_id_in_db = pd.read_sql_query(query, engine)
    # Convert the DataFrame to a list of site IDs in the database
    sites_id_in_db = sites_id_in_db["site_id"].tolist()
    # Find the site IDs in sites_id_in_catchment that are not present in sites_id_in_db
    sites_id_not_in_db = list(set(sites_id_in_catchment).difference(sites_id_in_db))
    return sites_id_not_in_db


def add_rainfall_data_to_db(engine: Engine, site_id: str, idf: bool) -> None:
    """
    Store the rainfall data for a specific site in the database.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    site_id : str
        HIRDS rainfall site ID.
    idf : bool
        Set to False for rainfall depth data, and True for rainfall intensity data.

    Returns
    -------
    None
        This function does not return any value.
    """
    # Get the relevant rainfall data table name from the idf parameter
    rain_table_name = db_rain_table_name(idf)
    # Retrieve the rainfall data for the specified site from HIRDS
    site_data = rainfall_data_from_hirds.get_data_from_hirds(site_id, idf)
    # Extract the layout structure of the data
    layout_structure = rainfall_data_from_hirds.get_layout_structure_of_data(site_data)

    # Iterate over each block structure in the layout structure
    for block_structure in layout_structure:
        # Convert the data to a tabular format
        rain_data = rainfall_data_from_hirds.convert_to_tabular_data(site_data, site_id, block_structure)
        # Store the tabular data in the relevant rainfall data table in the database
        rain_data.to_sql(rain_table_name, engine, index=False, if_exists="append")
    # Log a message to indicate the successful addition of the data to the database
    log.info(f"Added {rain_table_name} data for site {site_id} to database")


def add_each_site_rainfall_data(engine: Engine, sites_id_list: List[str], idf: bool) -> None:
    """
    Add rainfall data for each site in the sites_id_list to the database.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    sites_id_list : List[str]
        List of rainfall sites' IDs.
    idf : bool
        Set to False for rainfall depth data, and True for rainfall intensity data.

    Returns
    -------
    None
        This function does not return any value.
    """
    for site_id in sites_id_list:
        add_rainfall_data_to_db(engine, site_id, idf)


def rainfall_data_to_db(engine: Engine, sites_in_catchment: gpd.GeoDataFrame, idf: bool) -> None:
    """
    Store rainfall data of all the sites within the catchment area in the database.

    Parameters
    ----------
    engine : Engine
        The engine used to connect to the database.
    sites_in_catchment : gpd.GeoDataFrame
        Rainfall sites coverage areas (Thiessen polygons) that intersect or are within the catchment area.
    idf : bool
        Set to False for rainfall depth data, and True for rainfall intensity data.

    Returns
    -------
    None
        This function does not return any value.
    """
    # Get the IDs of the sites within the catchment area
    sites_id_in_catchment = get_sites_id_in_catchment(sites_in_catchment)
    # Determine the table name based on idf
    table_name = db_rain_table_name(idf)
    # Check if the table already exists in the database
    if tables.check_table_exists(engine, table_name):
        # Get the IDs of sites not in the database
        sites_id_not_in_db = get_sites_id_not_in_db(engine, sites_id_in_catchment, idf)
        # Check if there are sites not in the database
        if sites_id_not_in_db:
            # Add rainfall data for sites not in the database
            add_each_site_rainfall_data(engine, sites_id_not_in_db, idf)
        else:
            log.info(f"{table_name} data for sites in the requested catchment already available in the database.")
    else:
        # Check if there are sites within the catchment area
        if sites_id_in_catchment:
            # Add rainfall data for all sites within the catchment area
            add_each_site_rainfall_data(engine, sites_id_in_catchment, idf)
        else:
            log.info("No rainfall sites found within the requested catchment area.")
