import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

try:
    import torch
    from torch.utils.data import Dataset, DataLoader
except ImportError:
    # Graceful fallback for non-torch environments
    class Dataset:  # type: ignore
        pass
    DataLoader = None  # type: ignore

from ml.preprocessing import (
    align_dem_to_image,
    create_dem_valid_mask,
    prepare_dem_tensor,
    prepare_image_tensor,
    prepare_mask_tensor,
)

logger = logging.getLogger("depthwizard.ml.dataset")

SUPPORTED_IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
SUPPORTED_DEM_EXTENSIONS = {".tif", ".tiff", ".png", ".img"}


class SatelliteElevationDataset(Dataset):
    """
    PyTorch Dataset for paired optical satellite/aerial imagery and ground-truth DEMs.
    Pairs optical images and DEM rasters by matching filename stems.
    Preserves geospatial metadata (CRS, spatial bounds, NoData tags).
    Generates strict boolean validity masks ignoring NoData / invalid pixels.
    """

    def __init__(
        self,
        root_dir: Union[Path, str],
        target_size: Optional[Tuple[int, int]] = None,
        normalize_images: bool = True,
        custom_nodata: Optional[float] = None,
    ):
        self.root_dir = Path(root_dir)
        self.images_dir = self.root_dir / "images"
        self.dem_dir = self.root_dir / "dem"
        self.target_size = target_size
        self.normalize_images = normalize_images
        self.custom_nodata = custom_nodata

        self.pairs: List[Tuple[str, Path, Path]] = []
        self._unmatched_images: List[Path] = []
        self._unmatched_dems: List[Path] = []

        self._scan_and_pair_files()

    def _scan_and_pair_files(self) -> None:
        if not self.images_dir.exists() or not self.dem_dir.exists():
            logger.warning(
                f"Dataset directory structure missing under {self.root_dir}. "
                f"Expected '{self.images_dir}' and '{self.dem_dir}'."
            )
            return

        # Index optical images by stem
        image_map: Dict[str, Path] = {}
        for f in self.images_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                image_map[f.stem] = f

        # Index DEM rasters by stem
        dem_map: Dict[str, Path] = {}
        for f in self.dem_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_DEM_EXTENSIONS:
                dem_map[f.stem] = f

        # Match pairs
        matched_stems = sorted(set(image_map.keys()) & set(dem_map.keys()))
        for stem in matched_stems:
            self.pairs.append((stem, image_map[stem], dem_map[stem]))

        # Track unmatched files
        self._unmatched_images = [
            img_path for stem, img_path in image_map.items() if stem not in set(matched_stems)
        ]
        self._unmatched_dems = [
            dem_path for stem, dem_path in dem_map.items() if stem not in set(matched_stems)
        ]

        if self._unmatched_images:
            logger.warning(
                f"Found {len(self._unmatched_images)} images without matching DEMs in {self.images_dir}: "
                f"{[p.name for p in self._unmatched_images[:5]]}"
            )
        if self._unmatched_dems:
            logger.warning(
                f"Found {len(self._unmatched_dems)} DEMs without matching images in {self.dem_dir}: "
                f"{[p.name for p in self._unmatched_dems[:5]]}"
            )

        logger.info(f"Initialized dataset with {len(self.pairs)} valid image-DEM pairs from {self.root_dir}.")

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if idx < 0 or idx >= len(self.pairs):
            raise IndexError(f"Index {idx} out of range for dataset of size {len(self.pairs)}.")

        stem, img_path, dem_path = self.pairs[idx]

        # 1. Load optical image
        img_arr, img_crs, img_bounds = self._load_image(img_path)

        # 2. Load ground-truth DEM
        dem_arr, dem_nodata, dem_crs, dem_bounds = self._load_dem(dem_path)

        # Use explicitly provided custom_nodata if specified, else use GeoTIFF nodata
        effective_nodata = self.custom_nodata if self.custom_nodata is not None else dem_nodata

        # Determine target grid resolution
        target_shape = (self.target_size[0], self.target_size[1]) if self.target_size else (img_arr.shape[0], img_arr.shape[1])

        # 3. Align DEM grid to image dimensions
        if dem_arr.shape[:2] != (img_arr.shape[0], img_arr.shape[1]):
            dem_arr = align_dem_to_image(dem_arr, (img_arr.shape[0], img_arr.shape[1]))

        # 4. Construct boolean valid mask (True for real elevation, False for NoData/NaN)
        valid_mask = create_dem_valid_mask(dem_arr, nodata_value=effective_nodata)

        # 5. Convert to PyTorch tensors
        img_tensor = prepare_image_tensor(img_arr, target_size=self.target_size, normalize=self.normalize_images)
        dem_tensor = prepare_dem_tensor(dem_arr, target_shape=target_shape)
        mask_tensor = prepare_mask_tensor(valid_mask, target_shape=target_shape)

        return {
            "image": img_tensor,            # torch.FloatTensor of shape (3, H, W)
            "dem": dem_tensor,              # torch.FloatTensor of shape (1, H, W)
            "valid_mask": mask_tensor,      # torch.BoolTensor of shape (1, H, W)
            "stem": stem,
            "image_path": str(img_path),
            "dem_path": str(dem_path),
            "crs": dem_crs or img_crs or "Unknown",
            "bounds": dem_bounds or img_bounds or {},
            "nodata_value": effective_nodata if effective_nodata is not None else float("nan"),
        }

    def _load_image(self, path: Path) -> Tuple[np.ndarray, Optional[str], Optional[Dict[str, float]]]:
        """Load RGB image using rasterio if GeoTIFF, falling back to PIL."""
        crs_str = None
        bounds_dict = None

        try:
            import rasterio
            with rasterio.open(path) as src:
                crs_str = str(src.crs) if src.crs else None
                if src.bounds:
                    bounds_dict = {
                        "left": float(src.bounds.left),
                        "bottom": float(src.bounds.bottom),
                        "right": float(src.bounds.right),
                        "top": float(src.bounds.top),
                    }
                # Read 3 bands for RGB, or replicate 1 band
                if src.count >= 3:
                    arr = src.read([1, 2, 3])  # (3, H, W)
                    arr = np.transpose(arr, (1, 2, 0))  # (H, W, 3)
                else:
                    single = src.read(1)
                    arr = np.stack([single, single, single], axis=-1)
                return arr.astype(np.float32), crs_str, bounds_dict
        except Exception:
            pass

        # PIL fallback
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            return np.asarray(rgb, dtype=np.float32), crs_str, bounds_dict

    def _load_dem(self, path: Path) -> Tuple[np.ndarray, Optional[float], Optional[str], Optional[Dict[str, float]]]:
        """Load single-band DEM using rasterio if available, falling back to PIL."""
        crs_str = None
        bounds_dict = None
        nodata_val = None

        try:
            import rasterio
            with rasterio.open(path) as src:
                crs_str = str(src.crs) if src.crs else None
                nodata_val = float(src.nodata) if src.nodata is not None else None
                if src.bounds:
                    bounds_dict = {
                        "left": float(src.bounds.left),
                        "bottom": float(src.bounds.bottom),
                        "right": float(src.bounds.right),
                        "top": float(src.bounds.top),
                    }
                dem = src.read(1).astype(np.float32)
                return dem, nodata_val, crs_str, bounds_dict
        except Exception:
            pass

        # PIL fallback
        with Image.open(path) as img:
            arr = np.asarray(img, dtype=np.float32)
            if arr.ndim == 3:
                arr = arr[:, :, 0]
            return arr, nodata_val, crs_str, bounds_dict


def run_dataloader_smoke_test(split_dir: Optional[Path] = None) -> None:
    """
    DataLoader smoke test for inspecting paired datasets.
    Calculates elevation min/max only across valid, unmasked DEM pixels.
    Reports clear notification when real paired data is absent.
    """
    from ml.config import TEST_DIR

    target_dir = split_dir or TEST_DIR
    dataset = SatelliteElevationDataset(target_dir)

    print("\n" + "=" * 50)
    print("DATALOADER SMOKE TEST REPORT")
    print("=" * 50)
    print(f"Dataset target directory: {target_dir}")
    print(f"Dataset size: {len(dataset)}")

    if len(dataset) == 0:
        print("\nReal paired satellite/aerial image and DEM data is required for baseline evaluation.")
        print(f"Please place matching optical images in: {target_dir / 'images'}")
        print(f"Please place matching DEM rasters in:   {target_dir / 'dem'}")
        print("=" * 50 + "\n")
        return

    loader = DataLoader(dataset, batch_size=1, shuffle=False)
    for batch in loader:
        img = batch["image"]
        dem = batch["dem"]
        mask = batch["valid_mask"]
        stem = batch["stem"][0]

        valid_dem_vals = dem[mask]
        if valid_dem_vals.numel() > 0:
            elev_min = float(valid_dem_vals.min().item())
            elev_max = float(valid_dem_vals.max().item())
        else:
            elev_min = float("nan")
            elev_max = float("nan")

        print(f"Sample stem:     {stem}")
        print(f"Image shape:     {list(img.shape)}")
        print(f"DEM shape:       {list(dem.shape)}")
        print(f"Image dtype:     {img.dtype}")
        print(f"DEM dtype:       {dem.dtype}")
        print(f"Valid pixels:    {mask.sum().item()} / {mask.numel()}")
        print(f"Elevation min:   {elev_min:.2f} m")
        print(f"Elevation max:   {elev_max:.2f} m")
        break

    print("=" * 50 + "\n")


if __name__ == "__main__":
    run_dataloader_smoke_test()
