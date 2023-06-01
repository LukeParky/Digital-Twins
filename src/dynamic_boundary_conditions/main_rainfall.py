# -*- coding: utf-8 -*-
"""
@Description: Main rainfall script used to fetch and store rainfall data to the database, and generate the
              requested rainfall model input for BG-Flood etc.
@Author: pkh35, sli229
"""

import pathlib

import geopandas as gpd
from shapely.geometry import Polygon

from src import config
from src.digitaltwin import setup_environment
from src.dynamic_boundary_conditions import hirds_rainfall_data_to_db, hirds_rainfall_data_from_db
from src.dynamic_boundary_conditions import rainfall_sites, thiessen_polygons, hyetograph, model_input
from src.dynamic_boundary_conditions.rainfall_enum import RainInputType, HyetoMethod


def catchment_area_geometry_info(catchment_boundary: gpd.GeoDataFrame, to_crs=4326) -> Polygon:
    """
        Extract shapely geometry polygon from the catchment boundary in the given crs

        Parameters
        ----------
        catchment_boundary
            The data frame of the catchment boundary polygon
        """
    return catchment_boundary.to_crs(to_crs)["geometry"][0]


def main(selected_polygon_gdf: gpd.GeoDataFrame):
    # Catchment polygon
    catchment_polygon = catchment_area_geometry_info(selected_polygon_gdf)
    # Connect to the database
    engine = setup_environment.get_database()
    # Fetch rainfall sites data from the HIRDS website and store it to the database
    rainfall_sites.rainfall_sites_to_db(engine)
    # Calculate the area covered by each rainfall site across New Zealand and store it in the database
    nz_boundary_polygon = thiessen_polygons.get_new_zealand_boundary(engine)
    sites_in_nz = thiessen_polygons.get_sites_within_aoi(engine, nz_boundary_polygon)
    thiessen_polygons.thiessen_polygons_to_db(engine, nz_boundary_polygon, sites_in_nz)
    # Get all rainfall sites (thiessen polygons) coverage areas that are within the catchment area
    sites_in_catchment = thiessen_polygons.thiessen_polygons_from_db(engine, catchment_polygon)
    # Store rainfall data of all the sites within the catchment area in the database
    # Set idf to False for rain depth data and to True for rain intensity data
    hirds_rainfall_data_to_db.rainfall_data_to_db(engine, sites_in_catchment, idf=False)
    # Requested scenario
    rcp = 2.6
    time_period = "2031-2050"
    ari = 100
    # For a requested scenario, get all rainfall data for sites within the catchment area from the database
    # Set idf to False for rain depth data and to True for rain intensity data
    rain_depth_in_catchment = hirds_rainfall_data_from_db.rainfall_data_from_db(
        engine, sites_in_catchment, rcp, time_period, ari, idf=False)
    # Get hyetograph data for all sites within the catchment area
    hyetograph_data = hyetograph.get_hyetograph_data(
        rain_depth_in_catchment,
        storm_length_mins=2880,
        time_to_peak_mins=1440,
        increment_mins=10,
        interp_method="cubic",
        hyeto_method=HyetoMethod.ALT_BLOCK)
    # Create interactive hyetograph plots for sites within the catchment area
    # hyetograph.hyetograph(hyetograph_data, ari)
    # Get the intersection of rainfall sites coverage areas (thiessen polygons) and the catchment area

    # Write out mean catchment rainfall data in a text file (used as spatially uniform rainfall input into BG-Flood)
    sites_coverage = model_input.sites_coverage_in_catchment(sites_in_catchment, catchment_polygon)
    # Write out the requested rainfall model input for BG-Flood
    bg_flood_path = config.get_env_variable("FLOOD_MODEL_DIR", cast_to=pathlib.Path)
    model_input.generate_rain_model_input(
        hyetograph_data, sites_coverage, bg_flood_path, input_type=RainInputType.UNIFORM)
    model_input.generate_rain_model_input(
        hyetograph_data, sites_coverage, bg_flood_path, input_type=RainInputType.VARYING)


if __name__ == "__main__":
    sample_polygon = gpd.GeoDataFrame.from_file("selected_polygon.geojson")
    main(sample_polygon)
