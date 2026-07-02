# -*- coding: utf-8 -*-

import os
import sys

from pyrevit import revit, forms
from Autodesk.Revit.DB import *
from System.Collections.Generic import List

uidoc = revit.uidoc
doc = revit.doc


# -------------------------------------------------------
# Pick one MEP element
# -------------------------------------------------------

selection = uidoc.Selection

if selection.GetElementIds().Count > 0:
    elem = doc.GetElement(list(selection.GetElementIds())[0])
else:
    ref = uidoc.Selection.PickObject(
        Autodesk.Revit.UI.Selection.ObjectType.Element,
        "Select an MEP element"
    )
    elem = doc.GetElement(ref.ElementId)


# -------------------------------------------------------
# Read System Name
# -------------------------------------------------------

param = elem.LookupParameter("System Name")

if not param:
    forms.alert(
        "Selected element does not have a 'System Name' parameter.",
        exitscript=True
    )

system_name = param.AsString()

if not system_name:
    forms.alert(
        "The selected element has no System Name assigned.",
        exitscript=True
    )


# -------------------------------------------------------
# Find all elements with same System Name
# -------------------------------------------------------

ids = List[ElementId]()

collector = FilteredElementCollector(doc, doc.ActiveView.Id)\
            .WhereElementIsNotElementType()

for e in collector:

    p = e.LookupParameter("System Name")

    if not p:
        continue

    try:
        if p.AsString() == system_name:
            ids.Add(e.Id)
    except:
        pass


# -------------------------------------------------------
# Temporary Isolate
# -------------------------------------------------------

with revit.Transaction("Isolate System by System Name"):
    doc.ActiveView.IsolateElementsTemporary(ids)

uidoc.Selection.SetElementIds(ids)

forms.alert(
    "{} elements isolated.\n\nSystem Name: {}".format(
        ids.Count,
        system_name
    ),
    title="Auto Isolate System"
)