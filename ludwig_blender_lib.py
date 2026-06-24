# Ludwig Blender realism toolkit.
# This file is PREPENDED to every generated scene script, so all of these
# L_* helpers are in scope. The generator calls them instead of hand-rolling
# flat materials and lights. Everything is headless-safe (no operators that
# need a 3D viewport) and wrapped so Blender API drift degrades gracefully.

import bpy, math, mathutils


def L_reset():
    """Empty the scene."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


# --------------------------------------------------------------------------- #
# Materials — procedural PBR. kind in:
#   wood, fabric, ceramic, metal, plaster, plastic, glass, leather, concrete
# --------------------------------------------------------------------------- #

_PRESETS = {
    "wood":     dict(rough=0.45, metal=0.0, grain="wood"),
    "fabric":   dict(rough=0.9,  metal=0.0, grain="weave"),
    "leather":  dict(rough=0.55, metal=0.0, grain="weave"),
    "ceramic":  dict(rough=0.15, metal=0.0, grain=None),
    "metal":    dict(rough=0.25, metal=1.0, grain=None),
    "plaster":  dict(rough=0.85, metal=0.0, grain="bump"),
    "concrete": dict(rough=0.9,  metal=0.0, grain="bump"),
    "plastic":  dict(rough=0.4,  metal=0.0, grain=None),
    "glass":    dict(rough=0.0,  metal=0.0, grain=None),
}


def L_pbr(name, color=(0.8, 0.8, 0.8), kind="plastic", roughness=None):
    """Return a Material with a procedural PBR setup for `kind`."""
    p = _PRESETS.get(kind, _PRESETS["plastic"])
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (-300, 0)
    out.location = (60, 0)
    col = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = p["rough"] if roughness is None else roughness
    bsdf.inputs["Metallic"].default_value = p["metal"]
    if kind == "glass":
        try:
            bsdf.inputs["Transmission Weight"].default_value = 1.0
        except KeyError:
            pass
    if kind == "ceramic":
        try:
            bsdf.inputs["Coat Weight"].default_value = 0.3
        except KeyError:
            pass

    grain = p["grain"]
    if grain == "wood":
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.location = (-1100, 100)
        wave.inputs["Scale"].default_value = 2.5
        wave.inputs["Distortion"].default_value = 8.0
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-1100, -150)
        noise.inputs["Scale"].default_value = 18.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.location = (-700, 100)
        dark = tuple(c * 0.55 for c in color)
        ramp.color_ramp.elements[0].color = (dark[0], dark[1], dark[2], 1)
        ramp.color_ramp.elements[1].color = col
        nt.links.new(wave.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-700, -200)
        bump.inputs["Strength"].default_value = 0.15
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    elif grain in ("weave", "bump"):
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-700, -200)
        noise.inputs["Scale"].default_value = 40.0 if grain == "weave" else 8.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-400, -200)
        bump.inputs["Strength"].default_value = 0.2 if grain == "weave" else 0.35
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def L_apply(obj, material, *, bevel=True, smooth=True):
    """Assign a material and add bevel + smooth shading for light-catching edges."""
    if obj.type != "MESH":
        return obj
    obj.data.materials.clear()
    obj.data.materials.append(material)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    if bevel:
        L_bevel(obj)
    return obj


def L_bevel(obj, width=0.012, segments=2):
    if obj.type != "MESH":
        return
    m = obj.modifiers.new("L_bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(35)


# --------------------------------------------------------------------------- #
# Lighting & world — realistic golden-hour sky + sun + soft fill
# --------------------------------------------------------------------------- #

def L_sky(elevation_deg=8.0, rotation_deg=120.0, strength=1.0):
    """Physically-based Nishita sky for believable ambient + horizon color."""
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Strength"].default_value = strength
    try:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(elevation_deg)
        sky.sun_rotation = math.radians(rotation_deg)
        sky.altitude = 200
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    except Exception:
        bg.inputs["Color"].default_value = (0.9, 0.7, 0.5, 1.0)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def L_sun(strength=3.5, elevation_deg=12.0, azimuth_deg=45.0, color=(1.0, 0.82, 0.6)):
    d = bpy.data.lights.new("L_sun", type="SUN")
    d.energy = strength
    d.color = color
    d.angle = math.radians(2.0)  # soft shadow edges
    o = bpy.data.objects.new("L_sun", d)
    bpy.context.scene.collection.objects.link(o)
    el = math.radians(elevation_deg)
    az = math.radians(azimuth_deg)
    o.rotation_euler = (math.radians(90) - el, 0.0, az)
    return o


def L_fill(strength=60.0, location=(-4, -3, 5), size=6.0, color=(0.6, 0.7, 1.0)):
    d = bpy.data.lights.new("L_fill", type="AREA")
    d.energy = strength
    d.size = size
    d.color = color
    o = bpy.data.objects.new("L_fill", d)
    bpy.context.scene.collection.objects.link(o)
    o.location = location
    o.rotation_euler = mathutils.Vector(location).normalized().to_track_quat("Z", "Y").to_euler()
    return o


# Balanced lighting presets. Each pairs a WARM (or neutral) key with a COOL,
# softer fill so material colors survive and shadows don't go monochrome — the
# warm/cool contrast is what actually reads as a mood, not a saturated wash.
_LIGHTING = {
    "golden_hour": dict(sky=(10, 0.55), sun=(4.5, 13, 125, (1.0, 0.84, 0.66)),
                        fill=(35, (0.55, 0.68, 1.0))),
    "sunset":      dict(sky=(6, 0.5), sun=(4.0, 8, 120, (1.0, 0.72, 0.5)),
                        fill=(40, (0.5, 0.62, 1.0))),
    "midday":      dict(sky=(62, 1.0), sun=(5.5, 60, 90, (1.0, 0.97, 0.92)),
                        fill=(18, (0.85, 0.9, 1.0))),
    "overcast":    dict(sky=(45, 1.1), sun=(1.6, 55, 70, (0.95, 0.96, 1.0)),
                        fill=(30, (0.9, 0.93, 1.0))),
    "studio":      dict(sky=(50, 0.25), sun=(3.0, 45, 60, (1.0, 1.0, 1.0)),
                        fill=(120, (1.0, 1.0, 1.0))),
    "dramatic":    dict(sky=(20, 0.15), sun=(7.0, 22, 135, (1.0, 0.9, 0.78)),
                        fill=(8, (0.4, 0.5, 0.85))),
    "night":       dict(sky=(8, 0.08), sun=(0.6, 14, 200, (0.6, 0.7, 1.0)),
                        fill=(15, (1.0, 0.7, 0.4))),
}


def _area(name, loc, energy, size, color=(1, 1, 1), target=(0, 0, 0.5)):
    d = bpy.data.lights.new(name, type="AREA")
    d.energy = energy
    d.size = size
    d.color = color
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    direction = mathutils.Vector(target) - mathutils.Vector(loc)
    o.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return o


def L_studio_lights():
    """Classic 3-point studio rig: soft key + fill + rim, on a neutral world."""
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1.0)
        bg.inputs["Strength"].default_value = 0.4
    _area("L_key", (-3.0, -3.5, 4.0), 900, 6.0, (1.0, 0.98, 0.95))
    _area("L_fill", (4.0, -2.0, 2.0), 250, 5.0, (0.95, 0.97, 1.0))
    _area("L_rim", (1.5, 4.5, 5.0), 700, 3.0, (1.0, 1.0, 1.0))


def L_lighting(mood="golden_hour"):
    """Set a complete, balanced lighting rig for a named mood. Preferred over
    hand-tuning sun/sky/fill (which tends to over-saturate)."""
    if mood == "studio":
        L_studio_lights()
        return
    cfg = _LIGHTING.get(mood, _LIGHTING["golden_hour"])
    se, ss = cfg["sky"]
    L_sky(elevation_deg=se, rotation_deg=120, strength=ss)
    sstr, sel, saz, scol = cfg["sun"]
    L_sun(strength=sstr, elevation_deg=sel, azimuth_deg=saz, color=scol)
    fstr, fcol = cfg["fill"]
    L_fill(strength=fstr, color=fcol)


# --------------------------------------------------------------------------- #
# Staging — seating, camera aim + ground plane
# --------------------------------------------------------------------------- #

def L_seat(*objs, ground_z=0.0):
    """Drop one or more meshes AS A GROUP so the lowest point of the whole set
    rests exactly on the ground (z=ground_z), preserving their relative positions.

    This kills the single most common failure the critic flags: a subject that
    floats above the floor or sinks into it. Pass EVERY mesh that makes up the
    subject so the assembly drops together without breaking apart, e.g.
        L_seat(body, lid, handle)
    Call it after the parts are built and positioned, just before framing.
    Returns the sole object when given one, else the tuple of objects.
    """
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    if not meshes:
        return objs[0] if len(objs) == 1 else objs
    # World-space matrices are lazily evaluated; force them current before we read
    # bounding boxes, or a just-moved part reports a stale position.
    bpy.context.view_layer.update()
    min_z = min((o.matrix_world @ mathutils.Vector(corner)).z
                for o in meshes for corner in o.bound_box)
    dz = ground_z - min_z
    for o in meshes:
        o.location.z += dz
    bpy.context.view_layer.update()
    return objs[0] if len(objs) == 1 else objs


def L_camera(location=(8, -8, 5), target=(0, 0, 1), lens=50.0):
    cd = bpy.data.cameras.new("L_cam")
    cd.lens = lens
    co = bpy.data.objects.new("L_cam", cd)
    bpy.context.scene.collection.objects.link(co)
    co.location = location
    direction = mathutils.Vector(target) - mathutils.Vector(location)
    co.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = co
    return co


def L_autocam(azimuth_deg=35.0, elevation_deg=16.0, margin=1.45, lens=50.0):
    """Place the camera at a chosen angle and AUTO-FIT it so the whole subject is
    framed. Computes the bounding sphere of scene geometry (ignoring the ground/
    backdrop) and backs the camera off to fit. The reliable way to avoid bad crops."""
    pts = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name.startswith("L_ground"):
            continue
        dims = o.dimensions
        if max(dims) > 18.0:  # skip huge flats (floors/backdrops)
            continue
        for corner in o.bound_box:
            pts.append(o.matrix_world @ mathutils.Vector(corner))
    if not pts:
        return L_camera(location=(8, -8, 5), target=(0, 0, 1), lens=lens)
    lo = mathutils.Vector((min(p[i] for p in pts) for i in range(3)))
    hi = mathutils.Vector((max(p[i] for p in pts) for i in range(3)))
    center = (lo + hi) / 2.0
    radius = max((p - center).length for p in pts) or 1.0

    sensor = 36.0
    fov = 2.0 * math.atan(sensor / (2.0 * lens))
    dist = (radius / math.sin(fov / 2.0)) * margin

    el = math.radians(elevation_deg)
    az = math.radians(azimuth_deg)
    direction = mathutils.Vector(
        (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    loc = center + direction * dist
    return L_camera(location=tuple(loc), target=tuple(center), lens=lens)


def L_backdrop(color=(0.82, 0.82, 0.85), width=40.0, front=14.0, height=16.0,
               radius=5.0, segments=12, roughness=0.6):
    """A seamless 'infinity cove' sweep: floor curving smoothly up into a back
    wall, with no visible seam. The standard studio product backdrop."""
    prof = [(front, 0.0), (0.0, 0.0)]
    for i in range(1, segments + 1):
        t = (math.pi / 2) * (i / segments)
        prof.append((-radius * math.sin(t), radius - radius * math.cos(t)))
    prof.append((-radius, height))

    hw = width / 2.0
    verts, faces = [], []
    for (y, z) in prof:
        verts.append((-hw, y, z))
        verts.append((hw, y, z))
    for i in range(len(prof) - 1):
        a, b = 2 * i, 2 * i + 1
        c, d = 2 * (i + 1), 2 * (i + 1) + 1
        faces.append((a, b, d, c))

    mesh = bpy.data.meshes.new("L_ground_backdrop")
    obj = bpy.data.objects.new("L_ground_backdrop", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for p in mesh.polygons:
        p.use_smooth = True
    obj.data.materials.append(L_pbr("L_backdrop_mat", color, "plaster", roughness=roughness))
    return obj


def L_ground(size=40.0, color=(0.5, 0.45, 0.4), kind="plaster"):
    mesh = bpy.data.meshes.new("L_ground")
    obj = bpy.data.objects.new("L_ground", mesh)
    bpy.context.scene.collection.objects.link(obj)
    h = size / 2.0
    verts = [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    L_apply(obj, L_pbr("L_ground_mat", color, kind), bevel=False)
    return obj


# --------------------------------------------------------------------------- #
# Render quality — best-effort EEVEE Next, or Cycles for a hero shot
# --------------------------------------------------------------------------- #

def L_quality(engine="EEVEE", samples=64):
    scene = bpy.context.scene
    if engine.upper() == "CYCLES":
        scene.render.engine = "CYCLES"
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        try:
            scene.cycles.use_denoising = True
        except Exception:
            pass
    else:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except Exception:
            pass
        for attr, val in (("taa_render_samples", samples),
                          ("use_raytracing", True),
                          ("use_shadows", True)):
            try:
                setattr(scene.eevee, attr, val)
            except Exception:
                pass
    scene.view_settings.view_transform = "AgX" if "AgX" in [
        v.name for v in scene.view_settings.bl_rna.properties["view_transform"].enum_items
    ] else scene.view_settings.view_transform


# --------------------------------------------------------------------------- #
# Asset retrieval — fetch real CC0 meshes from Poly Haven (no API key) and import
# them headlessly, so the model can ARRANGE real, photoscanned geometry instead
# of sculpting everything from primitives. L_asset returns None on any failure
# (no match, no network), so the caller can fall back to building a primitive.
# --------------------------------------------------------------------------- #

import os as _os, re as _re, json as _json, tempfile as _tf
import urllib.request as _ureq

_PH_API = "https://api.polyhaven.com"
_PH_CACHE = _os.path.join(_tf.gettempdir(), "ludwig_assets")
_PH_UA = {"User-Agent": "Ludwig/0.1 (+https://github.com/IrgenSlj/Ludwig)"}
_PH_CATALOG = None
# light synonym map so natural briefs land on Poly Haven's asset naming
_PH_SYNONYMS = {"mug": "cup", "couch": "sofa", "armchair": "chair",
                "stool": "chair", "boots": "boot", "sneaker": "shoe",
                "plant": "pot", "succulent": "plant"}


def _ph_json(url):
    with _ureq.urlopen(_ureq.Request(url, headers=_PH_UA), timeout=30) as r:
        return _json.loads(r.read().decode())


def _ph_fetch(url, dst):
    with _ureq.urlopen(_ureq.Request(url, headers=_PH_UA), timeout=90) as r:
        data = r.read()
    with open(dst, "wb") as f:
        f.write(data)


def _ph_catalog():
    global _PH_CATALOG
    if _PH_CATALOG is None:
        _PH_CATALOG = _ph_json(_PH_API + "/assets?type=models")
    return _PH_CATALOG


def _ph_match(query):
    """Best Poly Haven model id for a text query, by keyword overlap, or None."""
    cat = _ph_catalog()
    words = set(_re.findall(r"[a-z0-9]+", query.lower()))
    words |= {_PH_SYNONYMS[w] for w in list(words) if w in _PH_SYNONYMS}
    best, best_score = None, 0
    for aid, meta in cat.items():
        hay = (aid.lower().replace("_", " ") + " "
               + " ".join(meta.get("tags", [])) + " "
               + " ".join(meta.get("categories", []))).lower()
        score = len(words & set(_re.findall(r"[a-z0-9]+", hay)))
        if score > best_score:
            best, best_score = aid, score
    return best


def _ph_download(aid, res="1k"):
    """Download an asset's gltf + bundled textures into a cache dir; return path."""
    files = _ph_json(_PH_API + "/files/%s" % aid)
    gltf = files["gltf"][res]["gltf"]
    ddir = _os.path.join(_PH_CACHE, aid, res)
    main = _os.path.join(ddir, _os.path.basename(gltf["url"]))
    if _os.path.exists(main):
        return main  # cached from a prior candidate/run
    _os.makedirs(ddir, exist_ok=True)
    _ph_fetch(gltf["url"], main)
    for relpath, info in gltf.get("include", {}).items():
        url = info["url"] if isinstance(info, dict) else info
        dst = _os.path.join(ddir, relpath)
        _os.makedirs(_os.path.dirname(dst), exist_ok=True)
        _ph_fetch(url, dst)
    return main


def L_asset(query, location=(0, 0, 0), max_dim=2.0, on_ground=True, res="1k"):
    """Fetch a real CC0 mesh matching `query` from Poly Haven, import it, scale
    it to ~`max_dim` units on its largest axis, center it at `location`, seat it
    on the ground, and return a parent Empty controlling the whole asset.
    Returns None on any failure so the caller can build a primitive instead."""
    try:
        aid = _ph_match(query)
        if not aid:
            print("L_asset: no Poly Haven match for %r" % query)
            return None
        path = _ph_download(aid, res)
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        meshes = [o for o in new if o.type == "MESH"]
        if not meshes:
            return None
        empty = bpy.data.objects.new("L_asset_" + aid, None)
        bpy.context.scene.collection.objects.link(empty)
        for o in new:
            if o.parent is None:
                o.parent = empty
                o.matrix_parent_inverse = empty.matrix_world.inverted()
        bpy.context.view_layer.update()

        def _bounds():
            pts = [o.matrix_world @ mathutils.Vector(c)
                   for o in meshes for c in o.bound_box]
            lo = mathutils.Vector((min(p[i] for p in pts) for i in range(3)))
            hi = mathutils.Vector((max(p[i] for p in pts) for i in range(3)))
            return lo, hi

        lo, hi = _bounds()
        biggest = max(hi - lo) or 1.0
        empty.scale = (max_dim / biggest,) * 3
        bpy.context.view_layer.update()
        lo, hi = _bounds()
        center = (lo + hi) / 2.0
        empty.location.x += location[0] - center.x
        empty.location.y += location[1] - center.y
        empty.location.z += (location[2] - lo.z) if on_ground else (location[2] - center.z)
        bpy.context.view_layer.update()
        return empty
    except Exception as e:
        print("L_asset(%r) failed: %s" % (query, e))
        return None
