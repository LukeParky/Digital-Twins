# -*- coding: utf-8 -*-
"""
Created on Thu Jan 20 16:36:59 2022.

@author: pkh35
"""

import pandas as pd
import pathlib
from src.dynamic_boundary_conditions import hirds_depth_data_to_db


def get_each_site_hirds_depth_data(
        ari, duration, site, engine, rcp=None, time_period=None
):
    """Get hirds rainfall depth data from the database."""
    if (rcp is None and time_period is not None) or (
            rcp is not None and time_period is None
    ):
        raise ValueError(
            "check the arguments of get_hirds_depth_data if rcp is None,time"
            " period should be None and vice-versa"
        )
    elif rcp is not None and time_period is not None:
        query = f"""select site_id, "{duration}h" from hirds_rain_depth where
                site_id='{site}' and ari={ari} and\
                rcp='{rcp}' and time_period='{time_period}'"""
    else:
        query = f"""select site_id, "{duration}h" from hirds_rain_depth where
                site_id='{site}' and ari={ari} and\
                rcp is null and time_period is null"""
    rain_depth = engine.execute(query)
    rain_depth = list(rain_depth.fetchone())
    return rain_depth


def hirds_depths_from_db(
        engine, catchment_area, ari, duration, rcp=None, time_period=None
):
    """Get the list of depths and site's id of each site and return in
    dataframe format."""
    sites_in_catchment = hirds_depth_data_to_db.get_sites_in_catchment(
        catchment_area, engine
    )

    depths_list = []
    for site_id in sites_in_catchment:
        rain_depth = get_each_site_hirds_depth_data(
            ari, duration, site_id, engine, rcp, time_period
        )
        depths_list.append(rain_depth)
    rain_depth_data = pd.DataFrame(depths_list, columns=["site_id", "depth"])
    return rain_depth_data


if __name__ == "__main__":
    from src.digitaltwin import setup_environment
    from src.dynamic_boundary_conditions import hyetograph

    catchment_file = pathlib.Path(
        r"C:\Users\sli229\Projects\Digital-Twins\src\dynamic_boundary_conditions\catchment_polygon.shp")
    ari = 100
    duration = 24
    rcp = "2.6"
    time_period = "2031-2050"

    engine = setup_environment.get_database()
    catchment_polygon = hyetograph.catchment_area_geometry_info(catchment_file)
    depths_data = hirds_depths_from_db(engine, catchment_polygon, ari, duration, rcp, time_period)
