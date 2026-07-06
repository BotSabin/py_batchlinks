# -*- coding: utf-8 -*-
__title__ = "Convert Exact FreeForm"
__author__ = "Sabin / BIMBOT"

import clr
import sys
import traceback

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

MIN_VOLUME = 0.0000001


def show(title, msg):
    TaskDialog.Show(title, msg)


def get_options():
    opt = Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = True
    opt.DetailLevel = ViewDetailLevel.Fine
    return opt


def is_valid_solid(s):
    try:
        return (
            s and
            s.Faces.Size > 0 and
            s.Edges.Size > 0 and
            abs(s.Volume) > MIN_VOLUME
        )
    except:
        return False


def collect_solids(obj, trf, solids):
    if obj is None:
        return

    if isinstance(obj, Solid):
        if is_valid_solid(obj):
            try:
                ts = SolidUtils.CreateTransformed(obj, trf)
                if is_valid_solid(ts):
                    solids.append(ts)
            except:
                solids.append(obj)
        return

    if isinstance(obj, GeometryInstance):
        try:
            new_trf = trf.Multiply(obj.Transform)
        except:
            new_trf = trf

        try:
            for g in obj.GetInstanceGeometry():
                collect_solids(g, new_trf, solids)
        except:
            pass

        try:
            for g in obj.GetSymbolGeometry():
                collect_solids(g, new_trf, solids)
        except:
            pass

        return

    if isinstance(obj, GeometryElement):
        for g in obj:
            collect_solids(g, trf, solids)
        return


def get_solids_from_element(el):
    solids = []
    geo = el.get_Geometry(get_options())
    if geo:
        collect_solids(geo, Transform.Identity, solids)
    return solids


def get_or_create_material(name, r, g, b):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name:
            return m.Id

    mat_id = Material.Create(doc, name)
    mat = doc.GetElement(mat_id)
    mat.Color = Color(r, g, b)
    return mat_id


def set_material(el, mat_id):
    try:
        p = el.get_Parameter(BuiltInParameter.MATERIAL_ID_PARAM)
        if p and not p.IsReadOnly:
            p.Set(mat_id)
    except:
        pass


def ask_delete_original():
    td = TaskDialog("Convert Exact FreeForm")
    td.MainInstruction = "Convert selected CAD geometry to exact FreeForm?"
    td.MainContent = (
        "This keeps the exact visible solid geometry as FreeFormElement.\n\n"
        "Recommended: delete the original CAD import after conversion."
    )
    td.AddCommandLink(
        TaskDialogCommandLinkId.CommandLink1,
        "Create FreeForm and keep original CAD import"
    )
    td.AddCommandLink(
        TaskDialogCommandLinkId.CommandLink2,
        "Create FreeForm and delete original CAD import"
    )
    td.CommonButtons = TaskDialogCommonButtons.Cancel
    return td.Show()


try:
    if not doc.IsFamilyDocument:
        show(
            "Convert Exact FreeForm",
            "Open the .RFA in Family Editor and run this tool there."
        )
        sys.exit()

    ref = uidoc.Selection.PickObject(
        ObjectType.Element,
        "Select CAD / DWG / ImportInstance geometry to convert"
    )

    source = doc.GetElement(ref.ElementId)

    if not source:
        show("Convert Exact FreeForm", "No valid element selected.")
        sys.exit()

    solids = get_solids_from_element(source)

    if not solids:
        show(
            "Convert Exact FreeForm",
            "No readable solid geometry was found in the selected element."
        )
        sys.exit()

    action = ask_delete_original()

    if action == TaskDialogResult.Cancel:
        sys.exit()

    t = Transaction(doc, "BIMBOT Convert Exact FreeForm")
    t.Start()

    default_mat = get_or_create_material("BIMBOT Exact FreeForm", 180, 180, 180)

    created = []
    failed = 0

    for s in solids:
        try:
            ff = FreeFormElement.Create(doc, s)
            set_material(ff, default_mat)
            created.append(ff)
        except:
            failed += 1

    original_status = "Original CAD import kept."

    if action == TaskDialogResult.CommandLink2:
        try:
            doc.Delete(source.Id)
            original_status = "Original CAD import deleted."
        except:
            original_status = "Original CAD import could not be deleted."

    t.Commit()

    show(
        "Convert Exact FreeForm",
        "Conversion completed.\n\n"
        "Solids found: {0}\n"
        "FreeForm elements created: {1}\n"
        "Failed solids: {2}\n\n"
        "{3}\n\n"
        "Save the family with Save As + Compact File.".format(
            len(solids),
            len(created),
            failed,
            original_status
        )
    )

except Exception as ex:
    try:
        if 't' in globals() and t.HasStarted():
            t.RollBack()
    except:
        pass

    show(
        "Convert Exact FreeForm - Error",
        str(ex) + "\n\n" + traceback.format_exc()
    )