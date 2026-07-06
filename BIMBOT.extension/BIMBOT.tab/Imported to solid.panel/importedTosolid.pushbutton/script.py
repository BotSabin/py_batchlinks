# -*- coding: utf-8 -*-
__title__ = "DWG To Family Solid"
__author__ = "Sabin / BIMBOT"

import clr
import traceback
import sys

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document


MIN_VOLUME = 0.0000001


def msg(title, text):
    TaskDialog.Show(title, text)


def eid_value(eid):
    try:
        return eid.IntegerValue
    except:
        try:
            return eid.Value
        except:
            return -1


def geometry_options():
    opt = Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = True
    opt.DetailLevel = ViewDetailLevel.Fine
    return opt


def is_good_solid(s):
    try:
        if not s:
            return False
        if s.Faces.Size == 0:
            return False
        if s.Edges.Size == 0:
            return False
        if abs(s.Volume) < MIN_VOLUME:
            return False
        return True
    except:
        return False


def add_count(counter, name):
    if name not in counter:
        counter[name] = 0
    counter[name] += 1


def collect_geometry(obj, trf, solids, meshes, curves, polylines, points, counter):
    if obj is None:
        return

    typ = obj.GetType().FullName
    add_count(counter, typ)

    if isinstance(obj, Solid):
        if is_good_solid(obj):
            try:
                solids.append(SolidUtils.CreateTransformed(obj, trf))
            except:
                solids.append(obj)
        return

    if isinstance(obj, Mesh):
        meshes.append((obj, trf))
        return

    if isinstance(obj, Curve):
        try:
            curves.append(obj.CreateTransformed(trf))
        except:
            curves.append(obj)
        return

    if isinstance(obj, PolyLine):
        polylines.append((obj, trf))
        return

    if isinstance(obj, Point):
        points.append((obj, trf))
        return

    if isinstance(obj, GeometryInstance):
        try:
            new_trf = trf.Multiply(obj.Transform)
        except:
            new_trf = trf

        try:
            inst_geo = obj.GetInstanceGeometry()
            for g in inst_geo:
                collect_geometry(g, new_trf, solids, meshes, curves, polylines, points, counter)
        except:
            pass

        try:
            sym_geo = obj.GetSymbolGeometry()
            for g in sym_geo:
                collect_geometry(g, new_trf, solids, meshes, curves, polylines, points, counter)
        except:
            pass

        return

    if isinstance(obj, GeometryElement):
        for g in obj:
            collect_geometry(g, trf, solids, meshes, curves, polylines, points, counter)
        return


def collect_from_element(el):
    solids = []
    meshes = []
    curves = []
    polylines = []
    points = []
    counter = {}

    try:
        geo = el.get_Geometry(geometry_options())
        if geo:
            collect_geometry(
                geo,
                Transform.Identity,
                solids,
                meshes,
                curves,
                polylines,
                points,
                counter
            )
    except:
        pass

    return solids, meshes, curves, polylines, points, counter


def get_family_category_id():
    try:
        if doc.IsFamilyDocument:
            cat = doc.OwnerFamily.FamilyCategory
            if cat:
                return cat.Id
    except:
        pass
    return ElementId(BuiltInCategory.OST_GenericModel)


def create_freeforms(solids):
    created = []

    for s in solids:
        try:
            ff = FreeFormElement.Create(doc, s)
            created.append(ff)
        except:
            pass

    return created


def create_mesh_directshape(meshes, name):
    if not meshes:
        return None

    builder = TessellatedShapeBuilder()
    builder.OpenConnectedFaceSet(False)

    face_count = 0

    for mesh, trf in meshes:
        try:
            tri_count = mesh.NumTriangles
        except:
            tri_count = 0

        for i in range(tri_count):
            try:
                tri = mesh.get_Triangle(i)

                pts = List[XYZ]()
                pts.Add(trf.OfPoint(tri.get_Vertex(0)))
                pts.Add(trf.OfPoint(tri.get_Vertex(1)))
                pts.Add(trf.OfPoint(tri.get_Vertex(2)))

                face = TessellatedFace(pts, ElementId.InvalidElementId)

                if builder.DoesFaceHaveEnoughLoopsAndVertices(face):
                    builder.AddFace(face)
                    face_count += 1
            except:
                pass

    builder.CloseConnectedFaceSet()

    if face_count == 0:
        return None

    builder.Target = TessellatedShapeBuilderTarget.AnyGeometry
    builder.Fallback = TessellatedShapeBuilderFallback.Mesh
    builder.Build()

    result = builder.GetBuildResult()

    ds = DirectShape.CreateElement(doc, get_family_category_id())
    ds.ApplicationId = "BIMBOT_DWG_TO_FAMILY"
    ds.ApplicationDataId = name
    ds.SetShape(result.GetGeometricalObjects())

    return ds


def get_target_elements():
    selected_ids = list(uidoc.Selection.GetElementIds())

    if selected_ids:
        return [doc.GetElement(x) for x in selected_ids if doc.GetElement(x)]

    all_elements = []
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()

    for el in collector:
        try:
            if el.Category:
                all_elements.append(el)
        except:
            pass

    return all_elements


try:
    if not doc.IsFamilyDocument:
        msg(
            "DWG To Family Solid",
            "Deschide familia RFA în Family Editor și rulează scriptul acolo.\n\n"
            "În Project va crea geometrie DirectShape, dar nu familie editabilă."
        )

    elements = get_target_elements()

    if not elements:
        msg("DWG To Family Solid", "Nu am găsit niciun element de analizat.")
        sys.exit()

    all_solids = []
    all_meshes = []
    all_curves = []
    all_polylines = []
    all_points = []
    total_counter = {}

    for el in elements:
        solids, meshes, curves, polylines, points, counter = collect_from_element(el)

        all_solids.extend(solids)
        all_meshes.extend(meshes)
        all_curves.extend(curves)
        all_polylines.extend(polylines)
        all_points.extend(points)

        for k in counter:
            if k not in total_counter:
                total_counter[k] = 0
            total_counter[k] += counter[k]

    if not all_solids and not all_meshes:
        report = []
        report.append("Nu am găsit Solid sau Mesh convertibil.")
        report.append("")
        report.append("Ce a găsit Revit API în geometrie:")
        report.append("")

        for k in sorted(total_counter.keys()):
            report.append("{0} : {1}".format(k, total_counter[k]))

        report.append("")
        report.append("Dacă vezi multe PolyLine / Curve / Point, acel DWG nu conține solid real.")
        report.append("Dacă este Proxy/AEC object, Revit API nu îl poate transforma în solid.")

        msg("DWG To Family Solid - Report", "\n".join(report))
        sys.exit()

    t = Transaction(doc, "Convert DWG geometry to Family geometry")
    t.Start()

    freeforms = []
    mesh_ds = None

    if all_solids:
        freeforms = create_freeforms(all_solids)

    if all_meshes:
        try:
            mesh_ds = create_mesh_directshape(all_meshes, "Converted_DWG_Mesh")
        except:
            mesh_ds = None

    t.Commit()

    report = []
    report.append("Conversie terminată.")
    report.append("")
    report.append("Elemente analizate: {0}".format(len(elements)))
    report.append("Solid-uri găsite: {0}".format(len(all_solids)))
    report.append("Mesh-uri găsite: {0}".format(len(all_meshes)))
    report.append("Curves găsite: {0}".format(len(all_curves)))
    report.append("PolyLines găsite: {0}".format(len(all_polylines)))
    report.append("Points găsite: {0}".format(len(all_points)))
    report.append("")
    report.append("FreeFormElement create: {0}".format(len(freeforms)))
    report.append("DirectShape mesh creat: {0}".format(1 if mesh_ds else 0))
    report.append("")

    if len(freeforms) > 0:
        report.append("Solidurile au fost convertite în geometrie de familie.")
    else:
        report.append("Nu s-a creat FreeFormElement. Geometria nu este solid real.")

    report.append("")
    report.append("Important: parametrul Height nu apare automat. Geometria importată devine formă fixă, nu extrusion parametric.")

    msg("DWG To Family Solid", "\n".join(report))

except Exception as ex:
    try:
        if 't' in globals() and t.HasStarted():
            t.RollBack()
    except:
        pass

    msg(
        "DWG To Family Solid - Error",
        str(ex) + "\n\n" + traceback.format_exc()
    )