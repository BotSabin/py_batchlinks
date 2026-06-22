# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script
import os

doc = revit.doc

ifc_path = forms.pick_file(file_ext='ifc', title='Selecteaza IFC Light pentru Link in Revit')
if not ifc_path:
    script.exit()

folder = os.path.dirname(ifc_path)
base = os.path.splitext(os.path.basename(ifc_path))[0]
linked_rvt = os.path.join(folder, base + "_Linked.rvt")

try:
    with revit.Transaction("BIMBOT - Link IFC"):
        result = DB.RevitLinkType.CreateFromIFC(
            doc,
            ifc_path,
            linked_rvt,
            True
        )

        link_type_id = result.ElementId
        DB.RevitLinkInstance.Create(doc, link_type_id)

    forms.alert("IFC linkuit in Revit:\n\n{}".format(ifc_path), title="BIMBOT Link IFC")

except Exception as e:
    forms.alert(
        "Nu am reusit sa linkuiesc IFC-ul automat.\n\n"
        "IFC-ul exista aici:\n{}\n\n"
        "Eroare:\n{}".format(ifc_path, str(e)),
        title="BIMBOT Link IFC"
    )