import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.config import POTSDAM_ROOT, RESULTS_DIR

DSM_DIR = POTSDAM_ROOT / "1_DSM"
RGB_DIR = POTSDAM_ROOT / "2_Ortho_RGB"

def extract_tile_id_rgb(filename: str) -> str:
    m = re.search(r'top_potsdam_0?(\d+)_0?(\d+)_RGB', filename, re.IGNORECASE)
    if m:
        return f"{int(m.group(1))}_{int(m.group(2))}"
    return ""

def extract_tile_id_dsm(filename: str) -> str:
    m = re.search(r'dsm_potsdam_0?(\d+)_0?(\d+)', filename, re.IGNORECASE)
    if m:
        return f"{int(m.group(1))}_{int(m.group(2))}"
    return ""

def validate_potsdam_dataset(potsdam_root: Path = POTSDAM_ROOT) -> Dict[str, Any]:
    dsm_dir = potsdam_root / "1_DSM"
    rgb_dir = potsdam_root / "2_Ortho_RGB"

    rgb_files = list(rgb_dir.glob("*.tif"))
    dsm_files = list(dsm_dir.glob("*.tif"))

    rgb_map: Dict[str, Path] = {}
    for f in rgb_files:
        tid = extract_tile_id_rgb(f.name)
        if tid:
            rgb_map[tid] = f

    dsm_map: Dict[str, Path] = {}
    for f in dsm_files:
        tid = extract_tile_id_dsm(f.name)
        if tid:
            dsm_map[tid] = f

    all_tile_ids = sorted(set(rgb_map.keys()) | set(dsm_map.keys()), key=lambda x: [int(v) for v in x.split("_")])
    valid_pairs = sorted(set(rgb_map.keys()) & set(dsm_map.keys()), key=lambda x: [int(v) for v in x.split("_")])
    missing_rgb = sorted(set(dsm_map.keys()) - set(rgb_map.keys()))
    missing_dsm = sorted(set(rgb_map.keys()) - set(dsm_map.keys()))

    report = {
        "potsdam_root": str(potsdam_root),
        "total_rgb_files": len(rgb_files),
        "total_dsm_files": len(dsm_files),
        "total_unique_tiles": len(all_tile_ids),
        "valid_pairs_count": len(valid_pairs),
        "missing_rgb_count": len(missing_rgb),
        "missing_dsm_count": len(missing_dsm),
        "missing_rgb_tiles": missing_rgb,
        "missing_dsm_tiles": missing_dsm,
        "sample_inspections": [],
        "all_pairs_verified": False
    }

    print("=" * 65)
    print("ISPRS POTSDAM DATASET VALIDATION REPORT")
    print("=" * 65)
    print(f"Source Root:        {potsdam_root}")
    print(f"RGB Files Found:    {len(rgb_files)}")
    print(f"DSM Files Found:    {len(dsm_files)}")
    print(f"Valid Paired Tiles: {len(valid_pairs)}")
    print(f"Missing RGB:        {len(missing_rgb)}")
    print(f"Missing DSM:        {len(missing_dsm)}")
    print("-" * 65)

    # Detailed inspection of valid pairs
    dimension_mismatches = []
    read_errors = []
    crs_list = set()
    sample_details = []

    for idx, tid in enumerate(valid_pairs):
        r_path = rgb_map[tid]
        d_path = dsm_map[tid]

        try:
            with rasterio.open(r_path) as src_rgb:
                rgb_w, rgb_h = src_rgb.width, src_rgb.height
                rgb_count = src_rgb.count
                rgb_dtype = src_rgb.dtypes[0]
                rgb_crs = str(src_rgb.crs)
                rgb_bounds = src_rgb.bounds

            with rasterio.open(d_path) as src_dsm:
                dsm_w, dsm_h = src_dsm.width, src_dsm.height
                dsm_count = src_dsm.count
                dsm_dtype = src_dsm.dtypes[0]
                dsm_crs = str(src_dsm.crs)
                dsm_bounds = src_dsm.bounds
                dsm_nodata = src_dsm.nodata

            if (rgb_w, rgb_h) != (dsm_w, dsm_h):
                dimension_mismatches.append((tid, (rgb_w, rgb_h), (dsm_w, dsm_h)))

            crs_list.add(dsm_crs)

            # Record sample details for first 5 tiles
            if idx < 5:
                # Read a small window to check values
                with rasterio.open(d_path) as src_dsm:
                    dsm_sample = src_dsm.read(1, window=rasterio.windows.Window(0, 0, 512, 512))
                sample_info = {
                    "tile_id": tid,
                    "rgb_file": r_path.name,
                    "dsm_file": d_path.name,
                    "dimensions": f"{rgb_w}x{rgb_h}",
                    "rgb_channels": rgb_count,
                    "rgb_dtype": rgb_dtype,
                    "dsm_channels": dsm_count,
                    "dsm_dtype": dsm_dtype,
                    "dsm_nodata": dsm_nodata,
                    "crs": dsm_crs,
                    "dsm_min": float(dsm_sample.min()),
                    "dsm_max": float(dsm_sample.max()),
                }
                sample_details.append(sample_info)
                print(f"Tile [{tid}]: {rgb_w}x{rgb_h} | RGB: {rgb_count}ch {rgb_dtype} | DSM: {dsm_count}ch {dsm_dtype} (min={dsm_sample.min():.1f}, max={dsm_sample.max():.1f}, nodata={dsm_nodata}) | CRS: {dsm_crs}")

        except Exception as e:
            read_errors.append((tid, str(e)))

    report["dimension_mismatches"] = dimension_mismatches
    report["read_errors"] = read_errors
    report["crs_set"] = list(crs_list)
    report["sample_inspections"] = sample_details
    report["all_pairs_verified"] = (len(dimension_mismatches) == 0 and len(read_errors) == 0 and len(valid_pairs) == 38)

    print("-" * 65)
    print(f"Dimension Mismatches: {len(dimension_mismatches)}")
    print(f"Read Errors:          {len(read_errors)}")
    print(f"Validation Status:    {'PASS' if report['all_pairs_verified'] else 'FAIL'}")
    print("=" * 65)

    return report

if __name__ == "__main__":
    rep = validate_potsdam_dataset()
    out_json = RESULTS_DIR / "potsdam_validation_report.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(rep, f, indent=2)
    print(f"Saved validation report to: {out_json}")
