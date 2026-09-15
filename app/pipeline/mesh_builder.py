import io
import json
import logging
from pathlib import Path
import struct
from typing import Optional, Tuple
import numpy as np
from PIL import Image

from app.config import (
    BEACH_LIFT_M,
    DEFAULT_HEIGHT_SCALE,
    FEATHER_RIM_Y,
    MESH_GRID_RESOLUTION,
    SEA_LEVEL_Y,
)

logger = logging.getLogger("depthwizard.pipeline.mesh")


def compute_vertex_normals(
    vertices: np.ndarray,
    indices: np.ndarray
) -> np.ndarray:
    """Compute smooth vertex normals for a triangulated mesh."""
    normals = np.zeros_like(vertices, dtype=np.float32)
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]

    # Face normals via cross product
    face_normals = np.cross(v1 - v0, v2 - v0)
    
    # Accumulate into vertex normals
    np.add.at(normals, indices[:, 0], face_normals)
    np.add.at(normals, indices[:, 1], face_normals)
    np.add.at(normals, indices[:, 2], face_normals)

    # Normalize vectors
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths < 1e-8] = 1.0
    return (normals / lengths).astype(np.float32)


def decimate_terrain_grid(
    norm_h: np.ndarray,
    target_res: int,
    flatness_threshold: float = 0.015
) -> np.ndarray:
    """
    Watertight, crack-free curvature-guided decimation of heightfield grid.
    Merges flat adjacent quad pairs into unified double-quad triangles without leaving holes.
    """
    triangles = []
    for r in range(target_res - 1):
        c = 0
        while c < target_res - 1:
            if c + 1 < target_res - 1:
                h_block = norm_h[r : r + 2, c : c + 3]
                span = float(h_block.max() - h_block.min())
                tl = r * target_res + c
                bl = (r + 1) * target_res + c
                mid_t = r * target_res + (c + 1)
                mid_b = (r + 1) * target_res + (c + 1)
                tr = r * target_res + (c + 2)
                br = (r + 1) * target_res + (c + 2)

                if span < flatness_threshold:
                    triangles.append([tl, bl, br])
                    triangles.append([tl, br, tr])
                else:
                    triangles.append([tl, bl, mid_b])
                    triangles.append([tl, mid_b, mid_t])
                    triangles.append([mid_t, mid_b, br])
                    triangles.append([mid_t, br, tr])
                c += 2
            else:
                tl = r * target_res + c
                bl = (r + 1) * target_res + c
                tr = r * target_res + (c + 1)
                br = (r + 1) * target_res + (c + 1)
                triangles.append([tl, bl, br])
                triangles.append([tl, br, tr])
                c += 1

    return np.array(triangles, dtype=np.uint32)


def generate_terrain_mesh(
    elevation_map: np.ndarray,
    target_res: int = MESH_GRID_RESOLUTION,
    height_scale: float = DEFAULT_HEIGHT_SCALE,
    adaptive_decimate: bool = False,
    physical_span: float = 600.0,
    feather_fraction: float = 0.09,
    feather_rim_y: float = FEATHER_RIM_Y,
    beach_lift_m: float = BEACH_LIFT_M,
    preserve_datum: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate triangulated 3D mesh from 2D elevation grid.
    Returns (vertices, normals, uvs, indices).

    Anti-flooding design (fixes "sea overlaps terrain"):
    - Interior heights are anchored so their minimum sits at
      ``beach_lift_m`` (default 2.5m), safely above the engine water
      plane (1.5m + ~0.13m Gerstner swell). Previously the
      interior minimum was 0.0m, so the bottom ~4% of every low-relief
      tile rendered submerged.
    - When ``preserve_datum`` is True (metric georeferenced DEM/GCP
      heights), relief shape is preserved via a robust p2/p98 span
      instead of min/max, so SRTM outliers cannot flatten the coast.
    - Only the outer feather apron dips to ``feather_rim_y`` (below sea
      level, above the seabed) so the tile meets the ocean with a beach
      falloff instead of a cliff wall. Feathering is applied in metre
      (Y) space, not normalized space, so it stays correct for both
      relative and metric inputs.
    """
    # Downsample/resample elevation map to target resolution
    img = Image.fromarray(elevation_map.astype(np.float32))
    img_resampled = img.resize((target_res, target_res), resample=Image.Resampling.BILINEAR)
    h_grid = np.asarray(img_resampled, dtype=np.float32)

    # Normalize height
    h_min, h_max = float(h_grid.min()), float(h_grid.max())
    if preserve_datum and h_max > h_min:
        # Robust span: p2 (shoreline anchor) to p98, immune to single
        # outlier pits/peaks that would otherwise collapse relief.
        finite = h_grid[np.isfinite(h_grid)]
        if finite.size >= 8:
            p_lo = float(np.percentile(finite, 2))
            p_hi = float(np.percentile(finite, 98))
        else:
            p_lo, p_hi = h_min, h_max
        span = p_hi - p_lo
        if span > 1e-9:
            norm_h = (h_grid - p_lo) / span
        else:
            norm_h = np.zeros_like(h_grid)
        # Clamp outlier tails (e.g. deep pits) so they cannot drag the
        # whole coast below sea level; real depressions still survive
        # as slightly-below-beach dips inside the feather blend.
        norm_h = np.clip(norm_h, -0.05, 1.0).astype(np.float32)
    elif h_max > h_min:
        norm_h = (h_grid - h_min) / (h_max - h_min)
    else:
        norm_h = np.zeros_like(h_grid)

    # Anchor interior minimum above the sea: y in [beach_lift, height_scale].
    # Guarantees dry land even for perfectly flat coastal plains.
    lift = float(np.clip(beach_lift_m, SEA_LEVEL_Y + 0.3, height_scale))
    grid_y_interior = (lift + norm_h * (height_scale - lift)).astype(np.float32)

    # Beach falloff in metre space: slope the outer apron down to the rim
    # so the tile blends into the ocean instead of ending in a cliff wall.
    feather_px = max(int(round(target_res * feather_fraction)), 0)
    if feather_px > 0 and height_scale != 0:
        rows, cols = np.mgrid[0:target_res, 0:target_res]
        edge_dist = np.minimum(
            np.minimum(rows, cols),
            np.minimum(target_res - 1 - rows, target_res - 1 - cols),
        ).astype(np.float32) / float(feather_px)
        mask = np.clip(edge_dist, 0.0, 1.0)
        # smoothstep for C1-continuous slope into the rim
        mask = mask * mask * (3.0 - 2.0 * mask)
        grid_y = np.float32(feather_rim_y) * (1.0 - mask) + grid_y_interior * mask
    else:
        grid_y = grid_y_interior

    # Mesh physical extents in virtual units (enlarged for realistic wide map view)
    width = physical_span
    depth = physical_span

    xs = np.linspace(-width / 2.0, width / 2.0, target_res, dtype=np.float32)
    zs = np.linspace(-depth / 2.0, depth / 2.0, target_res, dtype=np.float32)
    grid_x, grid_z = np.meshgrid(xs, zs)

    # Flatten coordinates into (N, 3) vertices
    vertices = np.stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()], axis=1).astype(np.float32)

    # UV coordinates [0.0, 1.0]
    us = np.linspace(0.0, 1.0, target_res, dtype=np.float32)
    vs = np.linspace(0.0, 1.0, target_res, dtype=np.float32)
    grid_u, grid_v = np.meshgrid(us, vs)
    uvs = np.stack([grid_u.ravel(), grid_v.ravel()], axis=1).astype(np.float32)

    if adaptive_decimate:
        indices = decimate_terrain_grid(norm_h, target_res)
    else:
        # Generate triangle indices for regular grid (100% solid, zero holes)
        r, c = np.meshgrid(
            np.arange(target_res - 1, dtype=np.uint32),
            np.arange(target_res - 1, dtype=np.uint32),
            indexing="ij"
        )
        v0 = (r * target_res + c).ravel()
        v1 = ((r + 1) * target_res + c).ravel()
        v2 = ((r + 1) * target_res + (c + 1)).ravel()
        v3 = (r * target_res + (c + 1)).ravel()

        tri1 = np.stack([v0, v1, v2], axis=1)
        tri2 = np.stack([v0, v2, v3], axis=1)
        indices = np.concatenate([tri1, tri2], axis=0).astype(np.uint32)

    # Compute smooth vertex normals
    normals = compute_vertex_normals(vertices, indices)

    return vertices, normals, uvs, indices


def export_pure_glb(
    vertices: np.ndarray,
    normals: np.ndarray,
    uvs: np.ndarray,
    indices: np.ndarray,
    texture_image: Image.Image,
    output_path: Path,
    extras: Optional[dict] = None,
) -> Path:
    """
    Self-contained, zero-external-dependency binary glTF 2.0 (.glb) exporter.
    Packs vertices, normals, UVs, triangle indices, and embedded PNG texture.
    Compatible with Raylib WebAssembly (cgltf + stbi_png), Three.js, and Babylon.js.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compress texture to PNG in-memory (Raylib WASM stbi supports PNG directly)
    tex_rgb = texture_image.convert("RGB")
    tex_buf = io.BytesIO()
    tex_rgb.save(tex_buf, format="PNG", optimize=True)
    img_bytes = tex_buf.getvalue()

    # Align byte buffer to 4-byte boundaries
    def pad4(b: bytes) -> bytes:
        pad = (4 - (len(b) % 4)) % 4
        return b + b"\x00" * pad

    indices_bytes = pad4(indices.astype(np.uint32).tobytes())
    positions_bytes = pad4(vertices.astype(np.float32).tobytes())
    normals_bytes = pad4(normals.astype(np.float32).tobytes())
    uvs_bytes = pad4(uvs.astype(np.float32).tobytes())
    img_bytes_padded = pad4(img_bytes)

    # Buffer layout offsets
    offset_indices = 0
    len_indices = len(indices_bytes)

    offset_pos = offset_indices + len_indices
    len_pos = len(positions_bytes)

    offset_norm = offset_pos + len_pos
    len_norm = len(normals_bytes)

    offset_uv = offset_norm + len_norm
    len_uv = len(uvs_bytes)

    offset_img = offset_uv + len_uv
    len_img = len(img_bytes_padded)

    total_bin = (
        indices_bytes + positions_bytes + normals_bytes + uvs_bytes + img_bytes_padded
    )

    # Bounding box of vertices
    min_pos = vertices.min(axis=0).tolist()
    max_pos = vertices.max(axis=0).tolist()

    # Construct glTF JSON structure (extras carry sea/shoreline metadata
    # so the engine can adapt the water plane per tile).
    gltf_dict = {
        "asset": {"version": "2.0", "generator": "DepthWizard-MeshBuilder"},
        "extras": extras or {},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "TerrainMesh"}],
        "meshes": [{
            "primitives": [{
                "attributes": {
                    "POSITION": 1,
                    "NORMAL": 2,
                    "TEXCOORD_0": 3,
                },
                "indices": 0,
                "material": 0,
                "mode": 4,  # TRIANGLES
            }]
        }],
        "materials": [{
            "name": "TerrainMaterial",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                "metallicFactor": 0.05,
                "roughnessFactor": 0.85,
            },
            "doubleSided": True,
        }],
        "textures": [{"sampler": 0, "source": 0}],
        "images": [{"bufferView": 4, "mimeType": "image/png"}],
        "samplers": [{
            "magFilter": 9729,  # LINEAR
            "minFilter": 9987,  # LINEAR_MIPMAP_LINEAR
            "wrapS": 33071,     # CLAMP_TO_EDGE
            "wrapT": 33071,
        }],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5125,  # UNSIGNED_INT
                "count": len(indices.ravel()),
                "type": "SCALAR",
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5126,  # FLOAT
                "count": len(vertices),
                "type": "VEC3",
                "max": max_pos,
                "min": min_pos,
            },
            {
                "bufferView": 2,
                "byteOffset": 0,
                "componentType": 5126,  # FLOAT
                "count": len(normals),
                "type": "VEC3",
            },
            {
                "bufferView": 3,
                "byteOffset": 0,
                "componentType": 5126,  # FLOAT
                "count": len(uvs),
                "type": "VEC2",
            },
        ],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": offset_indices,
                "byteLength": len(indices.tobytes()),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": offset_pos,
                "byteLength": len(vertices.tobytes()),
                "target": 34962,  # ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": offset_norm,
                "byteLength": len(normals.tobytes()),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": offset_uv,
                "byteLength": len(uvs.tobytes()),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": offset_img,
                "byteLength": len(img_bytes),
            },
        ],
        "buffers": [{"byteLength": len(total_bin)}],
    }

    json_str = json.dumps(gltf_dict, separators=(",", ":"))
    json_bytes = pad4(json_str.encode("utf-8"))

    # GLB Header: magic=0x46546C67 ('glTF'), version=2, length
    total_glb_len = 12 + (8 + len(json_bytes)) + (8 + len(total_bin))
    header = struct.pack("<4sII", b"glTF", 2, total_glb_len)

    # Chunk 0: JSON (type=0x4E4F534A)
    chunk0_hdr = struct.pack("<II", len(json_bytes), 0x4E4F534A)

    # Chunk 1: BIN (type=0x004E4942)
    chunk1_hdr = struct.pack("<II", len(total_bin), 0x004E4942)

    with open(output_path, "wb") as f:
        f.write(header)
        f.write(chunk0_hdr)
        f.write(json_bytes)
        f.write(chunk1_hdr)
        f.write(total_bin)

    logger.info(f"Exported self-contained .glb terrain mesh: {output_path} ({total_glb_len / 1024:.1f} KB)")
    return output_path


def build_terrain_glb(
    elevation_map: np.ndarray,
    texture_image: Image.Image,
    output_path: Path,
    grid_resolution: int = MESH_GRID_RESOLUTION,
    height_scale: float = DEFAULT_HEIGHT_SCALE,
    physical_span: float = 600.0,
    feather_fraction: float = 0.09,
    feather_rim_y: float = FEATHER_RIM_Y,
    beach_lift_m: float = BEACH_LIFT_M,
    preserve_datum: bool = False,
) -> Path:
    """
    Complete pipeline to generate triangulated 3D mesh and export to glTF .glb.
    """
    verts, norms, uvs, indices = generate_terrain_mesh(
        elevation_map=elevation_map,
        target_res=grid_resolution,
        height_scale=height_scale,
        physical_span=physical_span,
        feather_fraction=feather_fraction,
        feather_rim_y=feather_rim_y,
        beach_lift_m=beach_lift_m,
        preserve_datum=preserve_datum,
    )

    extras = {
        "seaLevelY": float(SEA_LEVEL_Y),
        "beachLiftM": float(beach_lift_m),
        "featherRimY": float(feather_rim_y),
        "terrainMinY": float(verts[:, 1].min()),
        "terrainMaxY": float(verts[:, 1].max()),
        "physicalSpan": float(physical_span),
        "heightScale": float(height_scale),
        "preserveDatum": bool(preserve_datum),
    }

    return export_pure_glb(
        vertices=verts,
        normals=norms,
        uvs=uvs,
        indices=indices,
        texture_image=texture_image,
        output_path=output_path,
        extras=extras,
    )
