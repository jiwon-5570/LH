from __future__ import annotations

import hashlib
import math
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.mask import mask
from shapely.geometry import Point, box, mapping

BUFFERS_M = (100, 300, 500)
MIN_COVERAGE_RATIO = 0.6


@dataclass
class RasterSource:
    path: Path
    dataset: rasterio.io.DatasetReader
    transformer: Transformer


def lowland_index(relative_elevation_m: float | None, local_std_m: float | None) -> float | None:
    """Return 0..100; 100 means the point is >=2 local standard deviations below its neighbourhood."""
    if relative_elevation_m is None or local_std_m is None or local_std_m <= 0:
        return None
    return round(100 * min(max(-relative_elevation_m / (2 * local_std_m), 0), 1), 4)


class TerrainAnalyzer:
    """Open DEM tiles once and combine all valid pixels intersecting each metric buffer."""

    def __init__(self, paths: list[Path]):
        self.stack = ExitStack()
        self.sources: list[RasterSource] = []
        for path in paths:
            dataset = self.stack.enter_context(rasterio.open(path))
            if dataset.crs is None:
                continue
            self.sources.append(RasterSource(path, dataset, Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)))

    def close(self) -> None:
        self.stack.close()

    def __enter__(self): return self

    def __exit__(self, *_args): self.close()

    @property
    def data_version(self) -> str:
        digest = hashlib.sha256()
        for source in sorted(self.sources, key=lambda item: item.path.name):
            digest.update(source.path.name.encode())
            digest.update(str(source.path.stat().st_size).encode())
            digest.update(str(source.dataset.crs).encode())
        return digest.hexdigest()

    @staticmethod
    def _valid(dataset, values: np.ndarray) -> np.ndarray:
        data = values.astype("float64", copy=False)
        valid = np.isfinite(data)
        if dataset.nodata is not None:
            valid &= data != dataset.nodata
        return data[valid]

    def point_elevation(self, longitude: float, latitude: float) -> float | None:
        values = []
        for source in self.sources:
            x, y = source.transformer.transform(longitude, latitude)
            if source.dataset.bounds.left <= x <= source.dataset.bounds.right and source.dataset.bounds.bottom <= y <= source.dataset.bounds.top:
                sample = self._valid(source.dataset, next(source.dataset.sample([(x, y)])))
                if sample.size:
                    values.append(float(sample[0]))
        return float(np.mean(values)) if values else None

    def _buffer_pixels(self, longitude: float, latitude: float, radius_m: int) -> tuple[np.ndarray, float, float]:
        values: list[np.ndarray] = []
        valid_area = 0.0
        slope_values: list[np.ndarray] = []
        for source in self.sources:
            x, y = source.transformer.transform(longitude, latitude)
            circle = Point(x, y).buffer(radius_m, quad_segs=24)
            left, bottom, right, top = source.dataset.bounds
            if not circle.intersects(box(left, bottom, right, top)):
                continue
            try:
                array, transform = mask(source.dataset, [mapping(circle)], crop=True, filled=False)
            except ValueError:
                continue
            band = np.ma.asarray(array[0])
            valid_mask = ~np.ma.getmaskarray(band) & np.isfinite(band.data)
            if source.dataset.nodata is not None:
                valid_mask &= band.data != source.dataset.nodata
            valid = band.data[valid_mask].astype("float64")
            if not valid.size:
                continue
            values.append(valid)
            pixel_area = abs(transform.a * transform.e)
            valid_area += valid.size * pixel_area
            filled = band.filled(np.nan).astype("float64")
            if min(filled.shape) >= 2:
                gy, gx = np.gradient(filled, abs(transform.e), abs(transform.a))
                slope = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy)))
                slope_values.append(slope[np.isfinite(slope) & valid_mask])
        expected_area = math.pi * radius_m * radius_m
        coverage = min(valid_area / expected_area, 1.0)
        merged = np.concatenate(values) if values else np.array([], dtype="float64")
        slopes = np.concatenate(slope_values) if slope_values else np.array([], dtype="float64")
        return merged, coverage, slopes

    def analyze(self, complex_id: str, longitude: float, latitude: float) -> dict:
        point = self.point_elevation(longitude, latitude)
        result: dict = {"complex_id": complex_id, "elevation_m": point}
        for radius in BUFFERS_M:
            values, coverage, slopes = self._buffer_pixels(longitude, latitude, radius)
            mean = float(np.mean(values)) if values.size else None
            minimum = float(np.min(values)) if values.size else None
            relative = point - mean if point is not None and mean is not None else None
            std = float(np.std(values)) if values.size else None
            result.update({
                f"min_elevation_{radius}m": minimum,
                f"mean_elevation_{radius}m": mean,
                f"relative_elevation_{radius}m": relative,
                f"slope_mean_{radius}m": float(np.mean(slopes)) if slopes.size else None,
                f"slope_max_{radius}m": float(np.max(slopes)) if slopes.size else None,
                f"lowland_index_{radius}m": lowland_index(relative, std),
                f"dem_coverage_ratio_{radius}m": round(coverage, 4),
            })
        coverages = [result[f"dem_coverage_ratio_{radius}m"] for radius in BUFFERS_M]
        result["data_quality_status"] = "COMPLETE" if point is not None and min(coverages) >= MIN_COVERAGE_RATIO else "INSUFFICIENT"
        result["data_version"] = self.data_version
        return result
