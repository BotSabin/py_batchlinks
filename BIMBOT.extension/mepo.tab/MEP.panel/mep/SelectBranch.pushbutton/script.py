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

el = pick_one(uidoc, 'Selecteaza un element pe ramura')
ids = traverse(doc, el.Id, stop_at_branch=True)
set_selection(uidoc, ids)
forms.alert('Ramura selectata: {} elemente.'.format(len(ids)), title='Select Branch')
