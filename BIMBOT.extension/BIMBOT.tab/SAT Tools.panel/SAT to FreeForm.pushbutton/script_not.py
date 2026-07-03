# -*- coding: utf-8 -*-
__title__ = "DWG To One Family"
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


def geometry_options():
    opt = Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = True
    opt.DetailLevel = ViewDetailLevel.Fine
    return opt


def is_good_solid(solid):
    try:
        return (
            solid and
            solid.Faces.Size > 0 and
            solid.Edges.Size > 0 and
            abs(solid.Volume) > MIN_VOLUME
        )
    except:
        return False


def collect_geometry(obj, trf, solids, meshes, counter):
    if obj is None:
        return

    try:
        name = obj.GetType().FullName
        counter[name] = counter.get(name, 0) + 1
    except:
        pass

    if isinstance(obj, Solid):
        if is_good_solid(obj):
            try:
                s = SolidUtils.CreateTransformed(obj, trf)
                if is_good_solid(s):
                    solids.append(s)
            except:
                solids.append(obj)
        return

    if isinstance(obj, Mesh):
        meshes.append((obj, trf))
        return

    if isinstance(obj, GeometryInstance):
        try:
            new_trf = trf.Multiply(obj.Transform)
        except:
            new_trf = trf

        try:
            for g in obj.GetInstanceGeometry():
                collect_geometry(g, new_trf, solids, meshes, counter)
        except:
            pass

        try:
            for g in obj.GetSymbolGeometry():
                collect_geometry(g, new_trf, solids, meshes, counter)
        except:
            pass

        return

    if isinstance(obj, GeometryElement):
        for g in obj:
            collect_geometry(g, trf, solids, meshes, counter)
        return


def collect_from_selected_element(el):
    solids = []
    meshes = []
    counter = {}

    geo = el.get_Geometry(geometry_options())

    if geo:
        collect_geometry(
            geo,
            Transform.Identity,
            solids,
            meshes,
            counter
        )

    return solids, meshes, counter


def get_family_category_id():
    try:
        if doc.IsFamilyDocument:
            cat = doc.OwnerFamily.FamilyCategory
            if cat:
                return cat.Id
    except:
        pass

    return ElementId(BuiltInCategory.OST_GenericModel)


def create_one_freeform_from_solids(solids):
    """
    Încearcă să unească toate solidurile într-un singur FreeFormElement.
    Dacă union fail, creează mai multe FreeFormElement, dar toate în aceeași familie.
    """
    if not solids:
        return []

    created = []

    final_solid = solids[0]
    failed_solids = []

    for s in solids[1:]:
        try:
            final_solid = BooleanOperationsUtils.ExecuteBooleanOperation(
                final_solid,
                s,
                BooleanOperationsType.Union
            )
        except:
            failed_solids.append(s)

    try:
        ff = FreeFormElement.Create(doc, final_solid)
        created.append(ff)
    except:
        pass

    for s in failed_solids:
        try:
            ff = FreeFormElement.Create(doc, s)
            created.append(ff)
        except:
            pass

    return created


def create_one_directshape_from_meshes(meshes, name):
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
    ds.ApplicationId = "BIMBOT_DWG_TO_ONE_FAMILY"
    ds.ApplicationDataId = name
    ds.SetShape(result.GetGeometricalObjects())

    return ds


try:
    ref = uidoc.Selection.PickObject(
        ObjectType.Element,
        "Select ONE DWG / imported CAD geometry"
    )

    el = doc.GetElement(ref.ElementId)

    if not el:
        msg("DWG To One Family", "Nu ai selectat niciun element valid.")
        sys.exit()

    solids, meshes, counter = collect_from_selected_element(el)

    if not solids and not meshes:
        report = []
        report.append("Nu am găsit Solid sau Mesh convertibil în elementul selectat.")
        report.append("")
        report.append("Tipuri geometrie găsite:")
        report.append("")

        for k in sorted(counter.keys()):
            report.append("{0} : {1}".format(k, counter[k]))

        report.append("")
        report.append("Asta înseamnă că DWG-ul are probabil proxy / curves / points / unsupported 3D data.")

        msg("DWG To One Family - Report", "\n".join(report))
        sys.exit()

    t = Transaction(doc, "Convert selected DWG to one family geometry")
    t.Start()

    freeforms = []
    mesh_ds = None

    if doc.IsFamilyDocument:
        if solids:
            freeforms = create_one_freeform_from_solids(solids)

        if meshes:
            try:
                mesh_ds = create_one_directshape_from_meshes(
                    meshes,
                    "Converted_Selected_DWG_Mesh"
                )
            except:
                mesh_ds = None

    else:
        if solids:
            ds = DirectShape.CreateElement(doc, get_family_category_id())
            ds.ApplicationId = "BIMBOT_DWG_TO_DIRECTSHAPE"
            ds.ApplicationDataId = "Converted_Selected_DWG_Solids"

            shape_list = List[GeometryObject]()
            for s in solids:
                shape_list.Add(s)

            ds.SetShape(shape_list)
            mesh_ds = ds

        if meshes:
            mesh_ds = create_one_directshape_from_meshes(
                meshes,
                "Converted_Selected_DWG_Mesh"
            )

    t.Commit()

    report = []
    report.append("Conversie terminată.")
    report.append("")
    report.append("Element selectat: {0}".format(el.Id))
    report.append("Solid-uri găsite: {0}".format(len(solids)))
    report.append("Mesh-uri găsite: {0}".format(len(meshes)))
    report.append("")
    report.append("FreeFormElement create: {0}".format(len(freeforms)))
    report.append("DirectShape mesh creat: {0}".format(1 if mesh_ds else 0))
    report.append("")
    report.append("Nu mai scanează toată familia.")
    report.append("Convertește doar DWG-ul selectat.")
    report.append("")
    report.append("După verificare, poți șterge DWG-ul original.")

    msg("DWG To One Family", "\n".join(report))

except Exception as ex:
    try:
        if 't' in globals() and t.HasStarted():
            t.RollBack()
    except:
        pass

    msg(
        "DWG To One Family - Error",
        str(ex) + "\n\n" + traceback.format_exc()
    )