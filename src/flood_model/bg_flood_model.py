# -*- coding: utf-8 -*-
"""
Created on Fri Jan 14 14:05:35 2022

@author: pkh35, sli229
"""

import logging
import pathlib
import os
import subprocess
from datetime import datetime
from typing import Tuple, Union, Optional

import geopandas as gpd
import xarray as xr
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base

from src import config
from src.digitaltwin import setup_environment
from src.digitaltwin.tables import BGFloodModelOutput, create_table, execute_query
from src.flood_model.serve_model import add_model_output_to_geoserver
from src.lidar import dem_metadata_in_db

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(levelname)s:%(asctime)s:%(name)s:%(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

log.addHandler(stream_handler)

Base = declarative_base()


def get_valid_bg_flood_dir() -> pathlib.Path:
    bg_flood_dir = config.get_env_variable("FLOOD_MODEL_DIR", cast_to=pathlib.Path)
    if bg_flood_dir.exists() and bg_flood_dir.is_dir():
        return bg_flood_dir
    raise FileNotFoundError(f"BG-Flood Model not found at: '{bg_flood_dir}'.")


def get_valid_model_output_path() -> pathlib.Path:
    model_output_dir = config.get_env_variable("DATA_DIR_MODEL_OUTPUT", cast_to=pathlib.Path)
    # Create model output folder if it does not already exist
    model_output_dir.mkdir(parents=True, exist_ok=True)
    dt_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    model_output_path = (model_output_dir / f"output_{dt_string}.nc")
    return model_output_path


def get_model_output_metadata(
        model_output_path: pathlib.Path,
        catchment_area: gpd.GeoDataFrame) -> Tuple[str, str, str]:
    """Get bg flood model output metadata"""
    output_name = model_output_path.name
    output_path = model_output_path.as_posix()
    catchment_geom = catchment_area["geometry"].to_wkt().iloc[0]
    return output_name, output_path, catchment_geom


def store_model_output_metadata_to_db(
        engine: Engine,
        model_output_path: pathlib.Path,
        catchment_area: gpd.GeoDataFrame) -> None:
    """Store metadata of the bg flood model output in the database."""
    create_table(engine, BGFloodModelOutput)
    output_name, output_path, geometry = get_model_output_metadata(model_output_path, catchment_area)
    query = BGFloodModelOutput(file_name=output_name, file_path=output_path, geometry=geometry)
    execute_query(engine, query)
    log.info("BG-Flood model output metadata successfully stored in the database.")


def latest_model_output_from_db() -> pathlib.Path:
    """Retrieve the latest model output file path, by querying the database"""
    engine = setup_environment.get_database()
    row = engine.execute("SELECT * FROM bg_flood_model_output ORDER BY created_at DESC LIMIT 1 ").fetchone()
    return pathlib.Path(row["file_path"])


def add_crs_to_latest_model_output() -> None:
    """
    Add CRS to the latest BG-Flood Model Output.
    """
    latest_file = latest_model_output_from_db()
    with xr.open_dataset(latest_file, decode_coords="all") as latest_output:
        latest_output.load()
        if latest_output.rio.crs is None:
            latest_output.rio.write_crs("epsg:2193", inplace=True)
    latest_output.to_netcdf(latest_file)


def process_tide_input_files(tide_input_file_path: pathlib.Path) -> Tuple[str, str]:
    tide_position = tide_input_file_path.stem.split('_')[0]
    tide_file = tide_input_file_path.name
    return tide_position, tide_file


def process_river_input_files(river_input_file_path: pathlib.Path) -> str:
    file_name_parts = river_input_file_path.stem.split('_')
    file_name = file_name_parts[0] + river_input_file_path.suffix
    extents = ','.join(file_name_parts[1:])
    river = f"{file_name},{extents}"
    new_file_path = river_input_file_path.with_name(file_name)
    river_input_file_path.rename(new_file_path)
    return river


def get_bg_flood_model_inputs(
        bg_flood_dir: pathlib.Path,
        model_output_path: pathlib.Path,
        dem_path: pathlib.Path,
        resolution: Union[int, float],
        output_timestep: Union[int, float],
        end_time: Union[int, float],
        mask: Union[int, float] = 9999,
        gpu_device: int = 0,
        small_nc: int = 0) -> None:
    """
    Set parameters to run the flood model.
    mask is used for visualising all the values larger than 9999 by default.
    If we are using the gpu then set to 0 (if no gpu type -1).
    small_nc = 0 means Level of refinement to apply to resolution based on the adaptive resolution trigger
    """
    with xr.open_dataset(dem_path) as dem_file:
        elev_var = list(dem_file.data_vars)[1]
    bg_param_path = bg_flood_dir / "BG_param.txt"
    outfile = model_output_path.as_posix()
    with open(bg_param_path, "w+") as param_file:
        param_file.write(f"topo = {dem_path.as_posix()}?{elev_var};\n"
                         f"dx = {resolution};\n"
                         f"outputtimestep = {output_timestep};\n"
                         f"endtime = {end_time};\n"
                         f"mask = {mask};\n"
                         f"gpudevice = {gpu_device};\n"
                         f"smallnc = {small_nc};\n"
                         f"outfile = {outfile};\n"
                         f"outvars = h, hmax, zb, zs, u, v;\n")
        for rain_input_file_path in bg_flood_dir.glob('rain_forcing.*'):
            file_extension = rain_input_file_path.suffix[1:]
            if file_extension == "txt":
                param_file.write(f"rain = {rain_input_file_path.name};\n")
            else:
                param_file.write(f"rain = {rain_input_file_path.name}?rain_intensity_mmhr;\n")
        for tide_input_file_path in bg_flood_dir.glob('*_bnd.txt'):
            tide_position, tide_file = process_tide_input_files(tide_input_file_path)
            param_file.write(f"{tide_position} = {tide_file},2;\n")
        for river_input_file_path in bg_flood_dir.glob('river[0-9]*_*.txt'):
            river = process_river_input_files(river_input_file_path)
            param_file.write(f"river = {river};\n")


def run_bg_flood_model(
        engine: Engine,
        catchment_area: gpd.GeoDataFrame,
        output_timestep: Union[int, float],
        end_time: Union[int, float],
        resolution: Optional[Union[int, float]] = None,
        mask: Union[int, float] = 9999,
        gpu_device: int = 0,
        small_nc: int = 0) -> None:
    # Get valid bg-flood model directory
    bg_flood_dir = get_valid_bg_flood_dir()
    # Get valid model output path
    model_output_path = get_valid_model_output_path()
    # Get hydro DEM file path and resolution used
    dem_path = dem_metadata_in_db.get_catchment_hydro_dem_filepath(engine, catchment_area)
    if resolution is None:
        _, resolution = dem_metadata_in_db.get_hydro_dem_data_and_resolution(engine, catchment_area)

    get_bg_flood_model_inputs(
        bg_flood_dir=bg_flood_dir,
        model_output_path=model_output_path,
        dem_path=dem_path,
        resolution=resolution,
        output_timestep=output_timestep,
        end_time=end_time,
        mask=mask,
        gpu_device=gpu_device,
        small_nc=small_nc)

    cwd = pathlib.Path.cwd()
    os.chdir(bg_flood_dir)
    subprocess.run([bg_flood_dir / "BG_flood.exe"], check=True)
    os.chdir(cwd)

    store_model_output_metadata_to_db(engine, model_output_path, catchment_area)
    add_crs_to_latest_model_output()
    add_model_output_to_geoserver(model_output_path)


def main(selected_polygon_gdf: gpd.GeoDataFrame) -> None:
    # Connect to the database
    engine = setup_environment.get_database()
    # Run BG-Flood Model
    run_bg_flood_model(
        engine=engine,
        catchment_area=selected_polygon_gdf,
        output_timestep=100,  # Saving the outputs after each `outputtimestep` seconds
        end_time=900  # Saving the outputs till `endtime` number of seconds
    )


if __name__ == "__main__":
    sample_polygon = gpd.GeoDataFrame.from_file("selected_polygon.geojson")
    main(sample_polygon)
