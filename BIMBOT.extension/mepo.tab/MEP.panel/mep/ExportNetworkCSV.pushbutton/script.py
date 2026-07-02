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

import csv
el = pick_one(uidoc, 'Selecteaza un element MEP din reteaua de exportat')
ids = traverse(doc, el.Id)
path = forms.save_file(file_ext='csv', default_name='MEP_Network.csv')
if path:
    with open(path, 'wb') as f:
        w = csv.writer(f)
        w.writerow(['ElementId', 'Category', 'Family/Type', 'OpenConnectors', 'Length_m'])
        for eid in ids:
            x = doc.GetElement(eid)
            cat = x.Category.Name if x.Category else ''
            typ = ''
            try: typ = x.Name
            except Exception: pass
            length_m = ''
            try:
                p = x.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
                if p: length_m = round(p.AsDouble() * 0.3048, 3)
            except Exception: pass
            w.writerow([eid.IntegerValue, cat, typ, open_connector_count(x), length_m])
    set_selection(uidoc, ids)
    forms.alert('Exportat CSV: {}'.format(path), title='Export Network CSV')
