# -*- coding: utf-8 -*-
import os, sys
from pyrevit import revit, forms, script
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..','..','..'))
lib = os.path.join(root, 'lib')
if lib not in sys.path:
    sys.path.append(lib)
from mepgraph import *
uidoc = revit.uidoc
doc = revit.doc
out = script.get_output()

# Selecteaza elementele vizibile in view-ul curent care au conectori liberi.
collector = FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType().ToElements()
ids = []
for x in collector:
    if is_mep_element(x) and open_connector_count(x) > 0:
        ids.append(x.Id)
set_selection(uidoc, ids)
forms.alert('Gasite/selectate in view: {} elemente cu conectori liberi.'.format(len(ids)), title='Open Ends')
