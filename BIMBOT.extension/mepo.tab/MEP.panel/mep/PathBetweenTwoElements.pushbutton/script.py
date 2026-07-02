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

el1 = pick_one(uidoc, 'Selecteaza primul element MEP')
el2 = pick_one(uidoc, 'Selecteaza al doilea element MEP')
ids = shortest_path(doc, el1.Id, el2.Id)
if not ids:
    forms.alert('Nu am gasit traseu conectat intre cele doua elemente.', title='Path Between Two Elements')
else:
    set_selection(uidoc, ids)
    forms.alert('Traseu selectat: {} elemente.'.format(len(ids)), title='Path Between Two Elements')
