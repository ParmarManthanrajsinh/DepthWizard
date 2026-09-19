import logging
from pathlib import Path
from typing import Dict, Any, Union

logger = logging.getLogger("depthwizard.pipeline.terrain_analysis")

def sample_elevation(
    raster_path: Union[str, Path],
    x: float,
    y: float,
    coordinate_system: str = "spatial"
) -> Dict[str, Any]:
    """
    Sample the absolute elevation from a GeoTIFF raster at a given (x, y) coordinate.
    
    Args:
        raster_path: Path to the calibrated DSM GeoTIFF.
        x: X-coordinate (longitude or easting if spatial, column if pixel).
        y: Y-coordinate (latitude or northing if spatial, row if pixel).
        coordinate_system: "spatial" for georeferenced coordinates, "pixel" for raw image indices.
        
    Returns:
        Dict with elevation, pixel coordinates, spatial coordinates, and nodata status.
    """
    try:
        import rasterio
    except ImportError:
        raise RuntimeError("rasterio is required for terrain analysis.")
        
    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster file not found: {raster_path}")
        
    with rasterio.open(raster_path) as src:
        # Determine the pixel coordinates (row, col)
        if coordinate_system.lower() == "spatial":
            # Convert spatial (x, y) to pixel (row, col)
            row, col = src.index(x, y)
            spatial_x, spatial_y = x, y
        elif coordinate_system.lower() == "pixel":
            row, col = int(round(y)), int(round(x))
            # Convert pixel (row, col) to spatial (x, y)
            spatial_x, spatial_y = src.xy(row, col)
        else:
            raise ValueError("coordinate_system must be 'spatial' or 'pixel'")
            
        # Check bounds
        if row < 0 or row >= src.height or col < 0 or col >= src.width:
            return {
                "elevation": None,
                "pixel_x": col,
                "pixel_y": row,
                "spatial_x": spatial_x,
                "spatial_y": spatial_y,
                "is_nodata": True,
                "error": "Coordinates out of bounds"
            }
            
        # Read exactly the 1x1 window
        window = rasterio.windows.Window(col, row, 1, 1)
        data = src.read(1, window=window)
        
        if data.size == 0:
            val = None
        else:
            import numpy as np
            val = float(data[0, 0])
            if np.isnan(val):
                val = None
            
        is_nodata = False
        if val is None or (src.nodata is not None and val == src.nodata):
            is_nodata = True
            val = None
            
        return {
            "elevation": round(val, 3) if val is not None else None,
            "pixel_x": col,
            "pixel_y": row,
            "spatial_x": round(spatial_x, 6),
            "spatial_y": round(spatial_y, 6),
            "is_nodata": is_nodata,
            "crs": str(src.crs) if src.crs else "local"
        }

def _calc_robust_gradients(elevation_arr: 'np.ndarray', res_y: float, res_x: float) -> tuple:
    """Calculate dz/drow and dz/dcol avoiding NaN propagation from boundaries."""
    import numpy as np
    
    # Left and right shifts
    left = np.roll(elevation_arr, 1, axis=1)
    right = np.roll(elevation_arr, -1, axis=1)
    
    dx_central = (right - left) / (2.0 * res_x)
    dx_forward = (right - elevation_arr) / res_x
    dx_backward = (elevation_arr - left) / res_x
    
    dx = np.where(np.isnan(dx_central),
                  np.where(np.isnan(dx_forward), dx_backward, dx_forward),
                  dx_central)
    # Fix column wrap-around edges
    dx[:, 0] = dx_forward[:, 0]
    dx[:, -1] = dx_backward[:, -1]
    
    # Up and down shifts
    up = np.roll(elevation_arr, 1, axis=0)
    down = np.roll(elevation_arr, -1, axis=0)
    
    dy_central = (down - up) / (2.0 * res_y)
    dy_forward = (down - elevation_arr) / res_y
    dy_backward = (elevation_arr - up) / res_y
    
    dy = np.where(np.isnan(dy_central),
                  np.where(np.isnan(dy_forward), dy_backward, dy_forward),
                  dy_central)
    # Fix row wrap-around edges
    dy[0, :] = dy_forward[0, :]
    dy[-1, :] = dy_backward[-1, :]
    
    return dy, dx

def calculate_slope(raster_path: Union[str, Path], output_path: Union[str, Path]) -> Dict[str, Any]:
    """Calculate terrain slope (in degrees) from absolute elevation GeoTIFF."""
    import numpy as np
    import rasterio

    raster_path = Path(raster_path)
    output_path = Path(output_path)
    
    with rasterio.open(raster_path) as src:
        elevation = src.read(1)
        nodata = src.nodata
        res_x, res_y = src.res
        
        mask = np.isnan(elevation)
        if nodata is not None:
            mask = mask | (elevation == nodata)
            
        elev_nan = np.where(mask, np.nan, elevation)
        
        dz_drow, dz_dcol = _calc_robust_gradients(elev_nan, float(res_y), float(res_x))
        
        rise_run = np.sqrt(dz_drow**2 + dz_dcol**2)
        slope_deg = np.degrees(np.arctan(rise_run)).astype(np.float32)
        
        slope_deg[mask] = -9999.0
        
        profile = src.profile
        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(slope_deg, 1)
            
        valid_slope = slope_deg[~mask]
        
        return {
            "layer_path": str(output_path),
            "crs": str(src.crs) if src.crs else "local",
            "resolution": (res_x, res_y),
            "min_slope": float(valid_slope.min()) if valid_slope.size > 0 else None,
            "max_slope": float(valid_slope.max()) if valid_slope.size > 0 else None,
            "mean_slope": float(valid_slope.mean()) if valid_slope.size > 0 else None,
        }

def calculate_aspect(raster_path: Union[str, Path], output_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Calculate terrain aspect (in degrees) from absolute elevation GeoTIFF.
    Convention: 0=North, 90=East, 180=South, 270=West.
    Flat terrain (slope < 1e-4) is explicitly marked as NoData (-9999.0).
    """
    import numpy as np
    import rasterio

    raster_path = Path(raster_path)
    output_path = Path(output_path)
    
    with rasterio.open(raster_path) as src:
        elevation = src.read(1)
        nodata = src.nodata
        res_x, res_y = src.res
        
        mask = np.isnan(elevation)
        if nodata is not None:
            mask = mask | (elevation == nodata)
            
        elev_nan = np.where(mask, np.nan, elevation)
        
        dz_drow, dz_dcol = _calc_robust_gradients(elev_nan, float(res_y), float(res_x))
        
        # Aspect compass bearing: downhill direction
        # row increases downward, so dz_drow is positive when sloping down to South
        aspect_deg = np.degrees(np.arctan2(-dz_dcol, dz_drow))
        aspect_deg = np.mod(aspect_deg, 360.0).astype(np.float32)
        
        # Undefined aspect for flat terrain
        rise_run = np.sqrt(dz_drow**2 + dz_dcol**2)
        flat_mask = rise_run < 1e-4
        
        aspect_deg[mask | flat_mask] = -9999.0
        
        profile = src.profile
        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(aspect_deg, 1)
            
        valid_aspect = aspect_deg[~(mask | flat_mask)]
        
        return {
            "layer_path": str(output_path),
            "crs": str(src.crs) if src.crs else "local",
            "resolution": (res_x, res_y),
            "min_aspect": float(valid_aspect.min()) if valid_aspect.size > 0 else None,
            "max_aspect": float(valid_aspect.max()) if valid_aspect.size > 0 else None,
            "mean_aspect": float(valid_aspect.mean()) if valid_aspect.size > 0 else None,
        }

def _haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate distance in meters between two geographic points."""
    import numpy as np
    R = 6371000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)
    a = np.sin(delta_phi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

def sample_elevation_profile(
    raster_path: Union[str, Path],
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    coordinate_system: str = "spatial",
    samples: int = None
) -> Dict[str, Any]:
    """Sample the absolute elevation along a line between two points."""
    import numpy as np
    import rasterio
    from scipy.ndimage import map_coordinates
    from rasterio.windows import Window
    
    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError("Raster file not found.")
        
    with rasterio.open(raster_path) as src:
        if coordinate_system.lower() == "spatial":
            start_row, start_col = src.index(start_x, start_y)
            end_row, end_col = src.index(end_x, end_y)
            start_spatial_x, start_spatial_y = start_x, start_y
            end_spatial_x, end_spatial_y = end_x, end_y
        elif coordinate_system.lower() == "pixel":
            start_row, start_col = start_y, start_x
            end_row, end_col = end_y, end_x
            start_spatial_x, start_spatial_y = src.xy(start_row, start_col)
            end_spatial_x, end_spatial_y = src.xy(end_row, end_col)
        else:
            raise ValueError("coordinate_system must be 'spatial' or 'pixel'")
            
        pixel_dist = np.sqrt((end_col - start_col)**2 + (end_row - start_row)**2)
        if samples is None:
            samples = max(2, int(np.ceil(pixel_dist)) + 1)
        samples = min(samples, 10000)
        
        if src.crs and src.crs.is_geographic:
            total_dist = _haversine_distance(start_spatial_x, start_spatial_y, end_spatial_x, end_spatial_y)
        else:
            total_dist = np.sqrt((end_spatial_x - start_spatial_x)**2 + (end_spatial_y - start_spatial_y)**2)
            
        distances = np.linspace(0, total_dist, samples)
        row_coords = np.linspace(start_row, end_row, samples)
        col_coords = np.linspace(start_col, end_col, samples)
        
        min_r, max_r = np.min(row_coords), np.max(row_coords)
        min_c, max_c = np.min(col_coords), np.max(col_coords)
        
        if max_r < 0 or min_r >= src.height or max_c < 0 or min_c >= src.width:
            return {
                "distances": [round(float(d), 3) for d in distances],
                "elevations": [None] * samples,
                "start": (round(float(start_spatial_x), 6), round(float(start_spatial_y), 6)),
                "end": (round(float(end_spatial_x), 6), round(float(end_spatial_y), 6)),
                "total_distance": round(float(total_dist), 3),
                "min_elevation": None,
                "max_elevation": None,
                "elevation_diff": None,
                "valid_samples": 0,
                "nodata_samples": samples,
            }
            
        w_min_r = max(0, int(np.floor(min_r)) - 2)
        w_max_r = min(src.height - 1, int(np.ceil(max_r)) + 2)
        w_min_c = max(0, int(np.floor(min_c)) - 2)
        w_max_c = min(src.width - 1, int(np.ceil(max_c)) + 2)
        
        window = Window(w_min_c, w_min_r, w_max_c - w_min_c + 1, w_max_r - w_min_r + 1)
        data = src.read(1, window=window).astype(np.float32)
        
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
            
        win_rows = row_coords - w_min_r
        win_cols = col_coords - w_min_c
        
        elevations = map_coordinates(data, [win_rows, win_cols], order=1, cval=np.nan, mode='constant')
        
        oob = (row_coords < 0) | (row_coords >= src.height) | (col_coords < 0) | (col_coords >= src.width)
        elevations[oob] = np.nan
        
        valid = ~np.isnan(elevations)
        valid_elevations = elevations[valid]
        
        min_e = float(np.min(valid_elevations)) if valid_elevations.size > 0 else None
        max_e = float(np.max(valid_elevations)) if valid_elevations.size > 0 else None
        
        return {
            "distances": [round(float(d), 3) for d in distances],
            "elevations": [round(float(e), 3) if v else None for e, v in zip(elevations, valid)],
            "start": (round(float(start_spatial_x), 6), round(float(start_spatial_y), 6)),
            "end": (round(float(end_spatial_x), 6), round(float(end_spatial_y), 6)),
            "total_distance": round(float(total_dist), 3),
            "min_elevation": round(min_e, 3) if min_e is not None else None,
            "max_elevation": round(max_e, 3) if max_e is not None else None,
            "elevation_diff": round(max_e - min_e, 3) if min_e is not None else None,
            "valid_samples": int(np.sum(valid)),
            "nodata_samples": int(np.sum(~valid)),
        }

def generate_contours(
    raster_path: Union[str, Path],
    interval: float,
    min_elevation: float = None,
    max_elevation: float = None,
    output_path: Union[str, Path] = None
) -> Dict[str, Any]:
    """
    Generate topographic contour lines from a GeoTIFF using contourpy.
    """
    import numpy as np
    import rasterio
    import json
    
    if interval <= 0 or not np.isfinite(interval):
        raise ValueError("Contour interval must be a positive finite number.")
        
    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError("Raster file not found.")
        
    try:
        import contourpy
    except ImportError:
        raise RuntimeError("contourpy is required to generate contours.")
        
    with rasterio.open(raster_path) as src:
        # Read the elevation data
        elevation = src.read(1)
        nodata = src.nodata
        
        mask = np.isnan(elevation)
        if nodata is not None:
            mask = mask | (elevation == nodata)
            
        valid_elevations = elevation[~mask]
        
        if valid_elevations.size == 0:
            actual_min = 0.0
            actual_max = 0.0
        else:
            actual_min = float(np.min(valid_elevations))
            actual_max = float(np.max(valid_elevations))
            
        if min_elevation is None:
            min_elevation = np.floor(actual_min / interval) * interval
        if max_elevation is None:
            max_elevation = np.ceil(actual_max / interval) * interval
            
        levels = np.arange(min_elevation, max_elevation + interval * 0.1, interval)
        
        # We need at least one level to generate something, but if levels is empty, it's fine.
        features = []
        
        if len(levels) > 0 and valid_elevations.size > 0:
            z_masked = np.ma.masked_array(elevation, mask=mask)
            # Use contourpy (z_masked natively handles NoData)
            cg = contourpy.contour_generator(z=z_masked, line_type=contourpy.LineType.Separate)
            
            transform = src.transform
            
            for level in levels:
                lines = cg.lines(level)
                
                # Each 'line' is an (N, 2) array of (col_idx, row_idx)
                for line in lines:
                    if len(line) < 2:
                        continue
                        
                    # contourpy returns (x, y) which is (col, row). 
                    # They are relative to the array indices. 
                    # rasterio's transform expects col, row. Center of pixel is + 0.5.
                    cols = line[:, 0] + 0.5
                    rows = line[:, 1] + 0.5
                    
                    spatial_xs, spatial_ys = transform * (cols, rows)
                    
                    coords = [[round(float(x), 6), round(float(y), 6)] for x, y in zip(spatial_xs, spatial_ys)]
                    
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords
                        },
                        "properties": {
                            "elevation": float(level)
                        }
                    })
                    
        geojson = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {
                    "name": str(src.crs) if src.crs else "local"
                }
            },
            "features": features
        }
        
        if output_path is not None:
            output_path = Path(output_path)
            with open(output_path, "w") as f:
                json.dump(geojson, f)
            
            # If huge, just return summary
            if len(features) > 1000:
                return {
                    "layer_path": str(output_path),
                    "interval": interval,
                    "min_elevation": min_elevation,
                    "max_elevation": max_elevation,
                    "crs": str(src.crs) if src.crs else "local",
                    "feature_count": len(features),
                    "features": features[:100] # Provide a preview
                }
                
        return {
            "layer_path": str(output_path) if output_path else None,
            "interval": interval,
            "min_elevation": min_elevation,
            "max_elevation": max_elevation,
            "crs": str(src.crs) if src.crs else "local",
            "feature_count": len(features),
            "features": features
        }

def export_analysis_package(
    job_id: str,
    dsm_path: Union[str, Path]
) -> Path:
    """
    Generate a ZIP archive containing all available terrain analysis artifacts for a job.
    Uses existing generated files where possible.
    """
    import zipfile
    import json
    import os
    import rasterio
    import numpy as np
    from pathlib import Path
    
    dsm_path = Path(dsm_path)
    if not dsm_path.exists():
        raise FileNotFoundError(f"DSM file not found: {dsm_path}")
        
    parent_dir = dsm_path.parent
    zip_path = parent_dir / f"{job_id}_export.zip"
    
    slope_path = parent_dir / f"{job_id}_slope.tif"
    aspect_path = parent_dir / f"{job_id}_aspect.tif"
    contours_path = parent_dir / f"{job_id}_contours.geojson"
    
    # If safe/inexpensive, generate missing slope and aspect
    if not slope_path.exists():
        from app.pipeline.terrain_analysis import calculate_slope
        calculate_slope(dsm_path, output_path=slope_path)
        
    if not aspect_path.exists():
        from app.pipeline.terrain_analysis import calculate_aspect
        calculate_aspect(dsm_path, output_path=aspect_path)
        
    # Check modification times for cache invalidation
    files_to_check = [f for f in [dsm_path, slope_path, aspect_path, contours_path] if f.exists()]
    
    if zip_path.exists():
        zip_mtime = zip_path.stat().st_mtime
        if all(f.stat().st_mtime <= zip_mtime for f in files_to_check):
            # Cache is still valid
            return zip_path
            
    # Gather metadata
    metadata = {
        "job_id": job_id,
        "dsm_included": True,
        "slope_included": slope_path.exists(),
        "aspect_included": aspect_path.exists(),
        "contours_included": contours_path.exists()
    }
    
    with rasterio.open(dsm_path) as src:
        metadata["crs"] = str(src.crs) if src.crs else "local"
        metadata["raster_dimensions"] = [src.width, src.height]
        metadata["raster_resolution"] = src.res
        metadata["bounds"] = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
        
        elev = src.read(1)
        nodata = src.nodata
        valid = ~np.isnan(elev)
        if nodata is not None:
            valid &= (elev != nodata)
            
        valid_elevs = elev[valid]
        if valid_elevs.size > 0:
            metadata["elevation_min"] = float(np.min(valid_elevs))
            metadata["elevation_max"] = float(np.max(valid_elevs))
            
    if slope_path.exists():
        with rasterio.open(slope_path) as src:
            slope_data = src.read(1)
            valid = ~np.isnan(slope_data)
            if src.nodata is not None:
                valid &= (slope_data != src.nodata)
            valid_slope = slope_data[valid]
            if valid_slope.size > 0:
                metadata["slope_min"] = float(np.min(valid_slope))
                metadata["slope_max"] = float(np.max(valid_slope))
                metadata["slope_mean"] = float(np.mean(valid_slope))
                
    if aspect_path.exists():
        metadata["aspect_format"] = "degrees_clockwise_from_north"
        
    if contours_path.exists():
        with open(contours_path, 'r') as f:
            try:
                cdata = json.load(f)
                features = cdata.get("features", [])
                metadata["contour_feature_count"] = len(features)
                if features:
                    elevs = set(f.get("properties", {}).get("elevation") for f in features)
                    metadata["contour_levels"] = sorted(list(elevs))
            except json.JSONDecodeError:
                pass
                
    metadata_path = parent_dir / f"{job_id}_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    # Create ZIP
    # ZIP_STORED for GeoTIFFs (already compressed/efficient), ZIP_DEFLATED for JSON/GeoJSON
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(dsm_path, arcname=dsm_path.name, compress_type=zipfile.ZIP_STORED)
        
        if slope_path.exists():
            zf.write(slope_path, arcname=slope_path.name, compress_type=zipfile.ZIP_STORED)
            
        if aspect_path.exists():
            zf.write(aspect_path, arcname=aspect_path.name, compress_type=zipfile.ZIP_STORED)
            
        if contours_path.exists():
            zf.write(contours_path, arcname=contours_path.name, compress_type=zipfile.ZIP_DEFLATED)
            
        zf.write(metadata_path, arcname=metadata_path.name, compress_type=zipfile.ZIP_DEFLATED)
        
    return zip_path



