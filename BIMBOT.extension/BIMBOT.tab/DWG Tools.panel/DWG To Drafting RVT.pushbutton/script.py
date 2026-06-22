# -*- coding: utf-8 -*-
# pyRevit script.py
# DWG -> Native Revit Model Lines, projected to active Floor Plan level

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import *
from System.Collections.Generic import List
from pyrevit import forms, script

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
view = doc.ActiveView
app = __revit__.Application

DELETE_DWG_AFTER_CONVERT = True
MIN_SEGMENT_LENGTH = app.ShortCurveTolerance * 2.0


def get_view_level_elevation():
    try:
        if view.GenLevel:
            return view.GenLevel.Elevation
    except:
        pass
    return 0.0


LEVEL_Z = get_view_level_elevation()


def project_point_to_level(pt):
    return XYZ(pt.X, pt.Y, LEVEL_Z)


def safe_line(p1, p2):
    try:
        p1 = project_point_to_level(p1)
        p2 = project_point_to_level(p2)

        if p1.DistanceTo(p2) <= MIN_SEGMENT_LENGTH:
            return None

        return Line.CreateBound(p1, p2)
    except:
        return None


def ensure_sketch_plane():
    plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, LEVEL_Z))
    sp = SketchPlane.Create(doc, plane)
    return sp


def curve_to_lines(curve):
    lines = []

    try:
        pts = list(curve.Tessellate())
    except:
        return lines

    for i in range(len(pts) - 1):
        ln = safe_line(pts[i], pts[i + 1])
        if ln:
            lines.append(ln)

    return lines


def polyline_to_lines(polyline, transform):
    lines = []

    try:
        pts = list(polyline.GetCoordinates())
    except:
        return lines

    for i in range(len(pts) - 1):
        try:
            p1 = transform.OfPoint(pts[i])
            p2 = transform.OfPoint(pts[i + 1])
            ln = safe_line(p1, p2)
            if ln:
                lines.append(ln)
        except:
            pass

    return lines


def collect_lines(geom_elem, transform):
    all_lines = []

    if geom_elem is None:
        return all_lines

    for obj in geom_elem:

        if isinstance(obj, GeometryInstance):
            try:
                inst_transform = transform.Multiply(obj.Transform)
                inst_geom = obj.GetInstanceGeometry()
                all_lines.extend(collect_lines(inst_geom, inst_transform))
            except:
                pass

        elif isinstance(obj, PolyLine):
            all_lines.extend(polyline_to_lines(obj, transform))

        elif isinstance(obj, Curve):
            try:
                c = obj.CreateTransformed(transform)
                all_lines.extend(curve_to_lines(c))
            except:
                pass

    return all_lines


# Pick DWG
dwg_path = forms.pick_file(
    file_ext="dwg",
    title="Select DWG file"
)

if not dwg_path:
    forms.alert("No DWG selected.")
    script.exit()


# Import DWG temporarily
imported_id_ref = clr.Reference[ElementId]()

t = Transaction(doc, "Import DWG temporarily")
t.Start()

try:
    options = DWGImportOptions()
    options.ColorMode = ImportColorMode.Preserved
    options.Placement = ImportPlacement.Origin
    options.Unit = ImportUnit.Millimeter
    options.ThisViewOnly = True

    success = doc.Import(dwg_path, options, view, imported_id_ref)

    if not success:
        t.RollBack()
        forms.alert("DWG import failed.")
        script.exit()

    cad_id = imported_id_ref.Value
    cad_import = doc.GetElement(cad_id)

    t.Commit()

except Exception as ex:
    t.RollBack()
    forms.alert("Import failed:\n{}".format(ex))
    script.exit()


# Read geometry
opt = Options()
opt.ComputeReferences = False
opt.IncludeNonVisibleObjects = True
opt.View = view

geom = cad_import.get_Geometry(opt)
native_lines = collect_lines(geom, Transform.Identity)

if not native_lines:
    forms.alert("No usable geometry found.")
    script.exit()


# Create model lines
created_ids = List[ElementId]()

t = Transaction(doc, "Convert DWG to Model Lines")
t.Start()

sp = ensure_sketch_plane()

created = 0
failed = 0

for ln in native_lines:
    try:
        mc = doc.Create.NewModelCurve(ln, sp)
        created_ids.Add(mc.Id)
        created += 1
    except:
        failed += 1

if DELETE_DWG_AFTER_CONVERT:
    try:
        doc.Delete(cad_id)
    except:
        pass

t.Commit()


# Select and zoom to created lines
if created_ids.Count > 0:
    try:
        uidoc.Selection.SetElementIds(created_ids)
        uidoc.ShowElements(created_ids)
    except:
        pass


forms.alert(
    "Finished.\n\nCreated Model Lines: {}\nFailed/skipped: {}\nLevel Z: {}".format(
        created,
        failed,
        LEVEL_Z
    )
)