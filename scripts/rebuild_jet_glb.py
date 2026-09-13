import io
import json
import struct
from pathlib import Path
import numpy as np
from PIL import Image

def rebuild_jet():
    jet_path = Path("app/static/viewer/jet.glb")
    tex_dir = Path("app/static/viewer/atlasjet-texture")
    
    # Read original jet.glb
    with open(jet_path, "rb") as f:
        f.seek(12)
        clen = int.from_bytes(f.read(4), "little")
        f.seek(20)
        d = json.loads(f.read(clen))
        f.seek(20 + clen)
        bin_len = int.from_bytes(f.read(4), "little")
        f.seek(28 + clen)
        bdata = f.read(bin_len)

    # Node transforms:
    # Node 2 (plane_full) parent translation:
    T2 = np.array([0.0018557249568402767, 0.7692197561264038, -2.411759614944458], dtype=np.float32)
    # Node 0/1 local transform:
    T0 = np.array([-0.0006413273513317108, -0.9431214332580566, 2.5335988998413086], dtype=np.float32)
    q = [0.7071068286895752, 0, 0, 0.7071068286895752] # 90 deg rotation around X
    S0 = np.array([0.3196147680282593, 2.8115179538726807, 0.3196147680282593], dtype=np.float32)
    
    x, y, z, w = q
    R = np.array([
        [1 - 2*(y*y + z*z),     2*(x*y - z*w),     2*(x*z + y*w)],
        [    2*(x*y + z*w), 1 - 2*(x*x + z*z),     2*(y*z - x*w)],
        [    2*(x*z - y*w),     2*(y*z + x*w), 1 - 2*(x*x + y*y)]
    ], dtype=np.float32)
    
    invS = np.array([1.0/S0[0], 1.0/S0[1], 1.0/S0[2]], dtype=np.float32)

    def xform_v(verts):
        # verts: (N, 3)
        return (verts * S0) @ R.T + T0 + T2

    def xform_n(normals):
        # normals: (N, 3)
        tn = (normals * invS) @ R.T
        lengths = np.linalg.norm(tn, axis=1, keepdims=True)
        lengths[lengths < 1e-8] = 1.0
        return tn / lengths

    def get_accessor_data(acc_idx, dtype, shape_item):
        acc = d["accessors"][acc_idx]
        bv = d["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        cnt = acc["count"]
        return np.frombuffer(bdata, dtype=dtype, count=cnt * shape_item, offset=off).reshape(-1, shape_item)

    def get_indices(acc_idx):
        acc = d["accessors"][acc_idx]
        bv = d["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        cnt = acc["count"]
        comp_type = acc["componentType"]
        if comp_type == 5123: # UNSIGNED_SHORT
            return np.frombuffer(bdata, dtype=np.uint16, count=cnt, offset=off).astype(np.uint32)
        elif comp_type == 5125: # UNSIGNED_INT
            return np.frombuffer(bdata, dtype=np.uint32, count=cnt, offset=off)
        elif comp_type == 5121: # UNSIGNED_BYTE
            return np.frombuffer(bdata, dtype=np.uint8, count=cnt, offset=off).astype(np.uint32)
        raise ValueError(f"Unknown index componentType: {comp_type}")

    # Process all primitives
    # Target primitives list:
    # Each item: { 'mat': int, 'verts': (N,3), 'norms': (N,3), 'uvs': (N,2), 'indices': (M,) }
    all_prims = []

    # Mesh 0: needs mirror across X=0
    for pi, p in enumerate(d["meshes"][0]["primitives"]):
        mat_idx = p["material"]
        pos = get_accessor_data(p["attributes"]["POSITION"], np.float32, 3)
        norm = get_accessor_data(p["attributes"]["NORMAL"], np.float32, 3)
        uv = get_accessor_data(p["attributes"]["TEXCOORD_0"], np.float32, 2)
        idx = get_indices(p["indices"])

        t_pos = xform_v(pos)
        t_norm = xform_n(norm)

        # Mirror across X=0 (plane of symmetry)
        m_pos = t_pos.copy()
        m_pos[:, 0] = -m_pos[:, 0]

        m_norm = t_norm.copy()
        m_norm[:, 0] = -m_norm[:, 0]

        m_uv = uv.copy() # shared UVs for mirrored side

        n_verts = len(pos)
        m_idx = []
        for i in range(0, len(idx), 3):
            # reverse triangle winding
            m_idx.extend([idx[i] + n_verts, idx[i+2] + n_verts, idx[i+1] + n_verts])
        m_idx = np.array(m_idx, dtype=np.uint32)

        merged_pos = np.vstack([t_pos, m_pos])
        merged_norm = np.vstack([t_norm, m_norm])
        merged_uv = np.vstack([uv, m_uv])
        merged_idx = np.concatenate([idx, m_idx])

        all_prims.append({
            "mat": mat_idx,
            "verts": merged_pos,
            "norms": merged_norm,
            "uvs": merged_uv,
            "indices": merged_idx
        })

    # Mesh 1: already symmetrical (engines, pylons), no mirror needed
    for pi, p in enumerate(d["meshes"][1]["primitives"]):
        mat_idx = p["material"]
        pos = get_accessor_data(p["attributes"]["POSITION"], np.float32, 3)
        norm = get_accessor_data(p["attributes"]["NORMAL"], np.float32, 3)
        idx = get_indices(p["indices"])

        t_pos = xform_v(pos)
        t_norm = xform_n(norm)
        # Default dummy UVs for mesh 1
        dummy_uv = np.zeros((len(pos), 2), dtype=np.float32)

        all_prims.append({
            "mat": mat_idx,
            "verts": t_pos,
            "norms": t_norm,
            "uvs": dummy_uv,
            "indices": idx
        })

    # Compute overall bounding box to center the model
    all_verts = np.vstack([p["verts"] for p in all_prims])
    min_b = all_verts.min(axis=0)
    max_b = all_verts.max(axis=0)
    print(f"Combined bounds before centering: min={min_b}, max={max_b}")

    # Center: keep X=0 exactly, center Y and Z
    center = np.array([0.0, (min_b[1] + max_b[1]) * 0.5, (min_b[2] + max_b[2]) * 0.5], dtype=np.float32)
    for p in all_prims:
        p["verts"] -= center

    all_verts_centered = np.vstack([p["verts"] for p in all_prims])
    min_c = all_verts_centered.min(axis=0)
    max_c = all_verts_centered.max(axis=0)
    print(f"Centered bounds: min={min_c}, max={max_c}, span={max_c - min_c}")

    # Prepare crisp Atlasjet white livery texture
    white_img = Image.open(tex_dir / "atlasjet-white.png").convert("RGBA")
    img_buf = io.BytesIO()
    white_img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    # Build pure glTF 2.0 binary
    buffer_bytes = bytearray()
    buffer_views = []
    accessors = []
    primitives_json = []

    def pad4(buf):
        rem = len(buf) % 4
        if rem != 0:
            buf.extend(b"\x00" * (4 - rem))

    # Add each primitive's attributes and indices
    for prim in all_prims:
        # Indices bufferView
        pad4(buffer_bytes)
        idx_offset = len(buffer_bytes)
        idx_raw = prim["indices"].astype(np.uint32).tobytes()
        buffer_bytes.extend(idx_raw)
        idx_bv = len(buffer_views)
        buffer_views.append({
            "buffer": 0,
            "byteOffset": idx_offset,
            "byteLength": len(idx_raw),
            "target": 34963 # ELEMENT_ARRAY_BUFFER
        })
        idx_acc = len(accessors)
        accessors.append({
            "bufferView": idx_bv,
            "byteOffset": 0,
            "componentType": 5125, # UNSIGNED_INT
            "count": len(prim["indices"]),
            "type": "SCALAR"
        })

        # Position bufferView
        pad4(buffer_bytes)
        pos_offset = len(buffer_bytes)
        pos_raw = prim["verts"].astype(np.float32).tobytes()
        buffer_bytes.extend(pos_raw)
        pos_bv = len(buffer_views)
        buffer_views.append({
            "buffer": 0,
            "byteOffset": pos_offset,
            "byteLength": len(pos_raw),
            "target": 34962 # ARRAY_BUFFER
        })
        pos_acc = len(accessors)
        accessors.append({
            "bufferView": pos_bv,
            "byteOffset": 0,
            "componentType": 5126, # FLOAT
            "count": len(prim["verts"]),
            "type": "VEC3",
            "min": prim["verts"].min(axis=0).tolist(),
            "max": prim["verts"].max(axis=0).tolist()
        })

        # Normal bufferView
        pad4(buffer_bytes)
        norm_offset = len(buffer_bytes)
        norm_raw = prim["norms"].astype(np.float32).tobytes()
        buffer_bytes.extend(norm_raw)
        norm_bv = len(buffer_views)
        buffer_views.append({
            "buffer": 0,
            "byteOffset": norm_offset,
            "byteLength": len(norm_raw),
            "target": 34962
        })
        norm_acc = len(accessors)
        accessors.append({
            "bufferView": norm_bv,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(prim["norms"]),
            "type": "VEC3"
        })

        # UV bufferView
        pad4(buffer_bytes)
        uv_offset = len(buffer_bytes)
        uv_raw = prim["uvs"].astype(np.float32).tobytes()
        buffer_bytes.extend(uv_raw)
        uv_bv = len(buffer_views)
        buffer_views.append({
            "buffer": 0,
            "byteOffset": uv_offset,
            "byteLength": len(uv_raw),
            "target": 34962
        })
        uv_acc = len(accessors)
        accessors.append({
            "bufferView": uv_bv,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(prim["uvs"]),
            "type": "VEC2"
        })

        primitives_json.append({
            "attributes": {
                "POSITION": pos_acc,
                "NORMAL": norm_acc,
                "TEXCOORD_0": uv_acc
            },
            "indices": idx_acc,
            "material": prim["mat"],
            "mode": 4
        })

    # Texture image bufferView
    pad4(buffer_bytes)
    img_offset = len(buffer_bytes)
    buffer_bytes.extend(img_bytes)
    img_bv = len(buffer_views)
    buffer_views.append({
        "buffer": 0,
        "byteOffset": img_offset,
        "byteLength": len(img_bytes)
    })

    # Materials
    materials_json = [
        {
            "name": "uçak_fuselage",
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "baseColorTexture": {"index": 0},
                "metallicFactor": 0.05,
                "roughnessFactor": 0.35
            },
            "doubleSided": True
        },
        {
            "name": "cam_cockpit",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.12, 0.16, 0.22, 0.95],
                "metallicFactor": 0.9,
                "roughnessFactor": 0.15
            },
            "doubleSided": True
        },
        {
            "name": "kantuc_wingtip",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.85, 0.12, 0.12, 1.0],
                "metallicFactor": 0.1,
                "roughnessFactor": 0.5
            },
            "doubleSided": True
        },
        {
            "name": "motor_cowling",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.95, 0.95, 0.96, 1.0],
                "metallicFactor": 0.15,
                "roughnessFactor": 0.4
            },
            "doubleSided": True
        },
        {
            "name": "motor_metal",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.42, 0.44, 0.48, 1.0],
                "metallicFactor": 0.85,
                "roughnessFactor": 0.25
            },
            "doubleSided": True
        },
        {
            "name": "aerodynamic_trim",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.18, 0.18, 0.2, 1.0],
                "metallicFactor": 0.2,
                "roughnessFactor": 0.6
            },
            "doubleSided": True
        }
    ]

    gltf = {
        "asset": {"version": "2.0", "generator": "DepthWizard-Rebuilder"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "AtlasjetAirbus"}],
        "meshes": [{
            "name": "JetMesh",
            "primitives": primitives_json
        }],
        "materials": materials_json,
        "textures": [{"sampler": 0, "source": 0}],
        "images": [{"bufferView": img_bv, "mimeType": "image/png"}],
        "samplers": [{
            "magFilter": 9729,
            "minFilter": 9987,
            "wrapS": 33071,
            "wrapT": 33071
        }],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(buffer_bytes)}]
    }

    json_str = json.dumps(gltf, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")
    # Pad JSON to 4-byte boundary with spaces
    rem = len(json_bytes) % 4
    if rem != 0:
        json_bytes += b" " * (4 - rem)

    # Pad binary chunk to 4-byte boundary
    pad4(buffer_bytes)

    total_length = 12 + 8 + len(json_bytes) + 8 + len(buffer_bytes)

    out_buf = bytearray()
    # GLB Header
    out_buf.extend(b"glTF")
    out_buf.extend(struct.pack("<I", 2)) # Version
    out_buf.extend(struct.pack("<I", total_length))

    # Chunk 0: JSON
    out_buf.extend(struct.pack("<I", len(json_bytes)))
    out_buf.extend(b"JSON")
    out_buf.extend(json_bytes)

    # Chunk 1: BIN
    out_buf.extend(struct.pack("<I", len(buffer_bytes)))
    out_buf.extend(b"BIN\x00")
    out_buf.extend(buffer_bytes)

    with open(jet_path, "wb") as f:
        f.write(out_buf)

    print(f"Successfully rebuilt {jet_path}: size={len(out_buf)} bytes, primitives={len(primitives_json)}")

if __name__ == "__main__":
    rebuild_jet()
