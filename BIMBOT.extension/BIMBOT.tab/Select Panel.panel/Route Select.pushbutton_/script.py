# -*- coding: utf-8 -*-

import os
import System
from collections import deque

from pyrevit import revit, forms
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons, TaskDialogResult
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from System.Collections.Generic import List


uidoc = revit.uidoc
doc = revit.doc


# =========================================================
# HELPERS
# =========================================================

def msg(text, title="Route Select"):
    TaskDialog.Show(title, text)


def eid_int(element_id):
    try:
        return element_id.IntegerValue
    except:
        try:
            return int(element_id.Value)
        except:
            return int(str(element_id))


def make_element_id(value):
    try:
        return ElementId(value)
    except:
        return ElementId(System.Int64(value))


def get_bool(control):
    try:
        return bool(control.IsChecked)
    except:
        return False


# =========================================================
# OPTIONS
# =========================================================

class Options(object):
    def __init__(self):
        self.mode = "2"
        self.same_system_only = False
        self.include_accessories = True
        self.include_sprinklers = True
        self.include_flexpipes = True


# =========================================================
# WPF UI
# =========================================================

class RouteSelectWindow(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.WPFWindow.__init__(self, xaml_file)

        self.options = Options()
        self.cancelled = True

        self.BtnStart.Click += self.start_click
        self.BtnCancel.Click += self.cancel_click

    def start_click(self, sender, args):
        if get_bool(self.RbMultiSegment):
            self.options.mode = "multi"
        else:
            self.options.mode = "2"

        self.options.same_system_only = get_bool(self.CbSameSystem)
        self.options.include_accessories = get_bool(self.CbIncludeAccessories)
        self.options.include_sprinklers = get_bool(self.CbIncludeSprinklers)
        self.options.include_flexpipes = get_bool(self.CbIncludeFlexPipes)

        self.cancelled = False
        self.Close()

    def cancel_click(self, sender, args):
        self.cancelled = True
        self.Close()


# =========================================================
# CATEGORIES
# =========================================================

def get_allowed_cat_ids(options):
    ids = [
        int(BuiltInCategory.OST_PipeCurves),
        int(BuiltInCategory.OST_PipeFitting)
    ]

    if options.include_accessories:
        ids.append(int(BuiltInCategory.OST_PipeAccessory))

    if options.include_sprinklers:
        ids.append(int(BuiltInCategory.OST_Sprinklers))

    if options.include_flexpipes:
        ids.append(int(BuiltInCategory.OST_FlexPipeCurves))

    return ids


def is_allowed_mep(elem, options):
    try:
        if elem is None:
            return False
        if elem.Category is None:
            return False

        return eid_int(elem.Category.Id) in get_allowed_cat_ids(options)
    except:
        return False


class MEPSelectionFilter(ISelectionFilter):
    def __init__(self, options):
        self.options = options

    def AllowElement(self, elem):
        return is_allowed_mep(elem, self.options)

    def AllowReference(self, ref, point):
        return True


# =========================================================
# SYSTEM FILTER
# =========================================================

def get_param_value(elem, bip):
    try:
        p = elem.get_Parameter(bip)
        if p:
            s = p.AsString()
            if s:
                return s
            vs = p.AsValueString()
            if vs:
                return vs
    except:
        pass
    return None


def get_system_key(elem):
    try:
        if hasattr(elem, "MEPSystem") and elem.MEPSystem:
            return eid_int(elem.MEPSystem.Id)
    except:
        pass

    val = get_param_value(elem, BuiltInParameter.RBS_SYSTEM_NAME_PARAM)
    if val:
        return val

    val = get_param_value(elem, BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM)
    if val:
        return val

    return None


# =========================================================
# CONNECTORS
# =========================================================

def get_connectors(elem):
    connectors = []

    if elem is None:
        return connectors

    try:
        cm = elem.ConnectorManager
        if cm:
            for c in cm.Connectors:
                connectors.append(c)
    except:
        pass

    try:
        if elem.MEPModel and elem.MEPModel.ConnectorManager:
            for c in elem.MEPModel.ConnectorManager.Connectors:
                connectors.append(c)
    except:
        pass

    return connectors


def get_connected_elements(elem, options, system_key):
    result = []

    for conn in get_connectors(elem):
        try:
            for ref_conn in conn.AllRefs:
                try:
                    owner = ref_conn.Owner

                    if owner is None:
                        continue

                    if eid_int(owner.Id) == eid_int(elem.Id):
                        continue

                    if not is_allowed_mep(owner, options):
                        continue

                    if options.same_system_only:
                        owner_key = get_system_key(owner)
                        if system_key and owner_key and owner_key != system_key:
                            continue

                    result.append(owner)

                except:
                    pass
        except:
            pass

    return result


# =========================================================
# BFS PATH FINDER
# =========================================================

def find_path(start_elem, end_elem, options):
    start_id = eid_int(start_elem.Id)
    end_id = eid_int(end_elem.Id)

    system_key = None
    if options.same_system_only:
        system_key = get_system_key(start_elem)

    queue = deque([start_elem])
    visited = set([start_id])
    parent = {}

    while queue:
        current = queue.popleft()
        current_id = eid_int(current.Id)

        if current_id == end_id:
            break

        neighbours = get_connected_elements(current, options, system_key)

        for neigh in neighbours:
            neigh_id = eid_int(neigh.Id)

            if neigh_id in visited:
                continue

            visited.add(neigh_id)
            parent[neigh_id] = current_id
            queue.append(neigh)

    if end_id not in visited:
        return []

    path = []
    current_id = end_id

    while current_id != start_id:
        path.append(current_id)

        if current_id not in parent:
            return []

        current_id = parent[current_id]

    path.append(start_id)
    path.reverse()

    return path


# =========================================================
# REVIT PICK / SELECT
# =========================================================

def pick_mep_element(message, options):
    try:
        picked_ref = uidoc.Selection.PickObject(
            ObjectType.Element,
            MEPSelectionFilter(options),
            message
        )
        return doc.GetElement(picked_ref.ElementId)
    except:
        return None


def select_ids(id_ints):
    ids = List[ElementId]()

    for x in id_ints:
        try:
            ids.Add(make_element_id(x))
        except:
            pass

    uidoc.Selection.SetElementIds(ids)


# =========================================================
# MULTI SEGMENT ACTION
# =========================================================

def ask_add_waypoint():
    result = TaskDialog.Show(
        "Multi Segment Route",
        "Add another waypoint?\n\nYes = Add waypoint\nNo = Pick End and finish\nCancel = Stop",
        TaskDialogCommonButtons.Yes | TaskDialogCommonButtons.No | TaskDialogCommonButtons.Cancel
    )

    if result == TaskDialogResult.Yes:
        return "waypoint"

    if result == TaskDialogResult.No:
        return "end"

    return None


# =========================================================
# MODES
# =========================================================

def run_two_point_mode(options):
    start = pick_mep_element("Pick START element", options)
    if not start:
        return

    end = pick_mep_element("Pick END element", options)
    if not end:
        return

    path = find_path(start, end, options)

    if not path:
        msg("No connected route found between selected elements.")
        return

    select_ids(path)
    msg("Selected {} elements.".format(len(path)))


def run_multi_segment_mode(options):
    picked = []

    start = pick_mep_element("Pick START element", options)
    if not start:
        return

    picked.append(start)

    while True:
        action = ask_add_waypoint()

        if action == "waypoint":
            waypoint = pick_mep_element("Pick WAYPOINT element", options)
            if waypoint:
                picked.append(waypoint)

        elif action == "end":
            end = pick_mep_element("Pick END element", options)
            if end:
                picked.append(end)
            break

        else:
            return

    if len(picked) < 2:
        return

    final_ids = []

    for i in range(len(picked) - 1):
        segment_path = find_path(picked[i], picked[i + 1], options)

        if not segment_path:
            msg("No route found between point {} and point {}.".format(i + 1, i + 2))
            return

        for eid in segment_path:
            if eid not in final_ids:
                final_ids.append(eid)

    select_ids(final_ids)
    msg("Selected {} elements from multi-segment route.".format(len(final_ids)))


# =========================================================
# START
# =========================================================

xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")

window = RouteSelectWindow(xaml_path)
window.ShowDialog()

if window.cancelled:
    pass
else:
    opts = window.options

    if opts.mode == "2":
        run_two_point_mode(opts)

    elif opts.mode == "multi":
        run_multi_segment_mode(opts)