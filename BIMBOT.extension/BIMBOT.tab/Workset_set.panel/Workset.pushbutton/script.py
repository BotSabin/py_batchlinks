# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms
from System.Collections.ObjectModel import ObservableCollection
from System.Windows import Visibility
from System.Windows.Data import CollectionViewSource
from System.Windows.Forms import FormStartPosition
import System.Drawing

import clr
import os
import re

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Windows.Forms import (
    Form,
    DataGridView,
    DataGridViewAutoSizeColumnsMode,
    Label,
    Panel,
    DockStyle,
    Button as WinButton,
    FormStartPosition
)
from System.Drawing import Size, Point, Font


doc = revit.doc
uidoc = revit.uidoc


def get_id_value(element_id):
    """Revit 2021-2026 compatible ElementId / WorksetId integer getter."""
    if element_id is None:
        return -1

    try:
        return element_id.IntegerValue
    except:
        pass

    try:
        return element_id.Value
    except:
        pass

    try:
        return int(element_id)
    except:
        return -1


class WorksetRow(object):
    def __init__(self, enabled, category, family, type_name, system_name,
                 level_name, current_worksets, count, target_workset):
        self.Enabled = enabled
        self.Category = category
        self.Family = family
        self.TypeName = type_name
        self.SystemName = system_name
        self.LevelName = level_name
        self.CurrentWorksets = current_worksets
        self.Count = count
        self.TargetWorkset = target_workset


def show_report_window(title, summary_lines, table_data, columns):
    has_table = table_data is not None and len(table_data) > 0

    form = Form()
    form.Text = title
    form.Size = Size(520, 340 if not has_table else 520)
    form.StartPosition = FormStartPosition.CenterScreen
    form.TopMost = True
    form.BackColor = System.Drawing.Color.FromArgb(17, 24, 39)

    panel = Panel()
    panel.Dock = DockStyle.Fill if not has_table else DockStyle.Top
    panel.Height = 300
    panel.BackColor = System.Drawing.Color.FromArgb(17, 24, 39)
    form.Controls.Add(panel)

    y = 14

    title_lbl = Label()
    title_lbl.Text = title
    title_lbl.Location = Point(14, y)
    title_lbl.Size = Size(660, 28)
    title_lbl.Font = Font("Segoe UI", 13, System.Drawing.FontStyle.Bold)
    title_lbl.ForeColor = System.Drawing.Color.White
    panel.Controls.Add(title_lbl)

    y += 38

    for line in summary_lines:
        lbl = Label()
        lbl.Text = str(line)
        lbl.Location = Point(16, y)
        lbl.Size = Size(650, 20)
        lbl.Font = Font("Segoe UI", 9)
        lbl.ForeColor = System.Drawing.Color.FromArgb(209, 213, 219)
        panel.Controls.Add(lbl)
        y += 22

    close_btn = WinButton()
    close_btn.Text = "Close Report"
    close_btn.Size = Size(130, 34)
    close_btn.Location = Point(16, y + 10)
    close_btn.BackColor = System.Drawing.Color.FromArgb(37, 99, 235)
    close_btn.ForeColor = System.Drawing.Color.White
    close_btn.FlatStyle = System.Windows.Forms.FlatStyle.Flat
    close_btn.FlatAppearance.BorderSize = 0
    close_btn.Click += lambda sender, args: form.Close()
    panel.Controls.Add(close_btn)

    if has_table:
        grid = DataGridView()
        grid.Dock = DockStyle.Fill
        grid.ReadOnly = True
        grid.AllowUserToAddRows = False
        grid.AllowUserToDeleteRows = False
        grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
        grid.BackgroundColor = System.Drawing.Color.FromArgb(17, 24, 39)
        grid.BorderStyle = System.Windows.Forms.BorderStyle.None
        grid.GridColor = System.Drawing.Color.FromArgb(55, 65, 81)
        grid.EnableHeadersVisualStyles = False
        grid.RowHeadersVisible = False

        grid.CellBorderStyle = System.Windows.Forms.DataGridViewCellBorderStyle.SingleHorizontal
        grid.ColumnHeadersBorderStyle = System.Windows.Forms.DataGridViewHeaderBorderStyle.None

        grid.ColumnHeadersDefaultCellStyle.BackColor = System.Drawing.Color.FromArgb(3, 7, 18)
        grid.ColumnHeadersDefaultCellStyle.ForeColor = System.Drawing.Color.White
        grid.ColumnHeadersDefaultCellStyle.Font = Font("Segoe UI", 9, System.Drawing.FontStyle.Bold)

        grid.DefaultCellStyle.BackColor = System.Drawing.Color.FromArgb(17, 24, 39)
        grid.DefaultCellStyle.ForeColor = System.Drawing.Color.White
        grid.DefaultCellStyle.SelectionBackColor = System.Drawing.Color.FromArgb(37, 99, 235)
        grid.DefaultCellStyle.SelectionForeColor = System.Drawing.Color.White
        grid.DefaultCellStyle.Font = Font("Segoe UI", 9)

        grid.AlternatingRowsDefaultCellStyle.BackColor = System.Drawing.Color.FromArgb(31, 41, 55)
        grid.AlternatingRowsDefaultCellStyle.ForeColor = System.Drawing.Color.White
        grid.AlternatingRowsDefaultCellStyle.SelectionBackColor = System.Drawing.Color.FromArgb(37, 99, 235)
        grid.AlternatingRowsDefaultCellStyle.SelectionForeColor = System.Drawing.Color.White

        for col in columns:
            grid.Columns.Add(str(col), str(col))

        for row in table_data:
            grid.Rows.Add([str(x) for x in row])

        form.Controls.Add(grid)

    form.Show()
    form.BringToFront()
    form.Activate()

def normalize_text(value):
    if not value:
        return ""
    value = str(value).lower()
    value = value.replace("_", " ").replace("-", " ").replace("/", " ").replace("\\", " ")
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_worksets():
    return sorted(
        list(DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset)),
        key=lambda x: x.Name
    )


def get_scope_boxes_in_active_view():
    try:
        scope_boxes = list(
            DB.FilteredElementCollector(doc, doc.ActiveView.Id)
            .OfCategory(DB.BuiltInCategory.OST_VolumeOfInterest)
            .WhereElementIsNotElementType()
        )
    except:
        scope_boxes = []

    return sorted(scope_boxes, key=lambda x: x.Name)


def get_views():
    valid_types = [
        DB.ViewType.FloorPlan,
        DB.ViewType.CeilingPlan,
        DB.ViewType.EngineeringPlan,
        DB.ViewType.AreaPlan,
        DB.ViewType.Section,
        DB.ViewType.ThreeD
    ]

    views = []
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.IsTemplate:
            continue
        if view.ViewType in valid_types:
            views.append(view)

    return sorted(views, key=lambda x: x.Name)


def get_view_level_name(view):
    try:
        if view and view.GenLevel:
            return view.GenLevel.Name
    except:
        pass
    return ""


def get_active_view_level_name():
    return get_view_level_name(doc.ActiveView)


def get_active_view_display():
    level_name = get_active_view_level_name()
    if level_name:
        return "{} | ID {} | Level: {}".format(
            doc.ActiveView.Name,
            get_id_value(doc.ActiveView.Id),
            level_name
        )

    return "{} | ID {} | Level: All / No GenLevel".format(
        doc.ActiveView.Name,
        get_id_value(doc.ActiveView.Id)
    )


def get_param_value(element, param_name):
    try:
        param = element.LookupParameter(param_name)
        if not param:
            return ""

        if param.StorageType == DB.StorageType.String:
            return param.AsString() or ""

        if param.StorageType == DB.StorageType.Integer:
            return str(param.AsInteger())

        if param.StorageType == DB.StorageType.Double:
            return str(param.AsDouble())

        if param.StorageType == DB.StorageType.ElementId:
            eid = param.AsElementId()
            if eid and get_id_value(eid) != -1:
                ref_el = doc.GetElement(eid)
                if ref_el:
                    try:
                        return ref_el.Name
                    except:
                        return str(get_id_value(eid))
            return ""
    except:
        return ""

    return ""


def get_element_level_name(element):
    try:
        level_id = element.LevelId
        if level_id and get_id_value(level_id) != -1:
            level = doc.GetElement(level_id)
            if level:
                return level.Name
    except:
        pass

    for pname in [
        "Reference Level",
        "Level",
        "Schedule Level",
        "Base Level",
        "Base Constraint",
        "Associated Level",
        "Host Level"
    ]:
        value = get_param_value(element, pname)
        if value and value != "-1":
            return value

    return ""


def get_workset_name(element):
    try:
        ws = doc.GetWorksetTable().GetWorkset(element.WorksetId)
        return ws.Name if ws else "Unknown"
    except:
        return "Unknown"


def set_element_workset(element, workset):
    param = element.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
    if param and not param.IsReadOnly:
        param.Set(get_id_value(workset.Id))
        return True
    return False


def is_valid_model_element(element):
    if not element or not element.Category:
        return False

    if element.Category.CategoryType != DB.CategoryType.Model:
        return False

    excluded_categories = [
        int(DB.BuiltInCategory.OST_VolumeOfInterest),
        int(DB.BuiltInCategory.OST_RvtLinks)
    ]

    if get_id_value(element.Category.Id) in excluded_categories:
        return False

    param = element.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
    if not param or param.IsReadOnly:
        return False

    return True


def get_selected_movable_elements():
    elements = []
    for eid in uidoc.Selection.GetElementIds():
        element = doc.GetElement(eid)
        if is_valid_model_element(element):
            elements.append(element)
    return elements


def get_elements_in_view(view):
    return [
        el for el in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
        if is_valid_model_element(el)
    ]


def get_all_movable_model_elements():
    return [
        el for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
        if is_valid_model_element(el)
    ]


def element_center_xy_inside_scope(element, scope_bbox):
    bbox = element.get_BoundingBox(None)
    if not bbox:
        return False

    center_x = (bbox.Min.X + bbox.Max.X) / 2.0
    center_y = (bbox.Min.Y + bbox.Max.Y) / 2.0

    return (
        scope_bbox.Min.X <= center_x <= scope_bbox.Max.X and
        scope_bbox.Min.Y <= center_y <= scope_bbox.Max.Y
    )


def get_elements_in_scope_xy(scope_box):
    bbox = scope_box.get_BoundingBox(None)
    if not bbox:
        return []

    elements = []

    for el in get_all_movable_model_elements():
        if el.Id == scope_box.Id:
            continue

        if element_center_xy_inside_scope(el, bbox):
            elements.append(el)

    return elements


def get_element_type(element):
    try:
        type_id = element.GetTypeId()
        if type_id and get_id_value(type_id) != -1:
            return doc.GetElement(type_id)
    except:
        pass
    return None


def safe_string(value):
    try:
        if value:
            return str(value)
    except:
        pass
    return ""


def get_family_and_type(element):
    family_name = ""
    type_name = ""

    element_type = get_element_type(element)

    if element_type:
        try:
            type_name = element_type.Name
        except:
            type_name = ""

        try:
            family_name = element_type.FamilyName
        except:
            family_name = ""

    if not family_name:
        family_name = element.Category.Name

    if not type_name:
        try:
            type_name = element.Name
        except:
            type_name = ""

    return safe_string(family_name), safe_string(type_name)


def get_system_name(element):
    for pname in [
        "System Name",
        "System Type",
        "System Classification",
        "Piping System Name",
        "Duct System Name"
    ]:
        value = get_param_value(element, pname)
        if value:
            return value

    try:
        mep_system = element.MEPSystem
        if mep_system:
            return mep_system.Name
    except:
        pass

    return ""


def get_element_search_text(element):
    texts = []

    try:
        texts.append(element.Category.Name)
    except:
        pass

    try:
        texts.append(element.Name)
    except:
        pass

    family, type_name = get_family_and_type(element)
    system_name = get_system_name(element)
    level_name = get_element_level_name(element)

    texts.append(family)
    texts.append(type_name)
    texts.append(system_name)
    texts.append(level_name)

    for pname in [
        "Family",
        "Family Name",
        "Type",
        "Type Name",
        "System Name",
        "System Type",
        "System Classification",
        "Piping System Name",
        "Duct System Name",
        "Description",
        "Comments",
        "Mark"
    ]:
        texts.append(get_param_value(element, pname))

    return normalize_text(" ".join([x for x in texts if x]))


def guess_target_workset(element, workset_names):
    search_text = get_element_search_text(element)
    if not search_text:
        return "None"

    workset_data = [(ws, normalize_text(ws)) for ws in workset_names]

    keyword_groups = [
        {"name": "hydrant", "element_keywords": ["hydrant", "hydrants", "landing valve"], "workset_keywords": ["hydrant", "hydrants", "landing valve"]},
        {"name": "deluge", "element_keywords": ["deluge"], "workset_keywords": ["deluge"]},
        {"name": "water curtain", "element_keywords": ["water curtain", "curtain"], "workset_keywords": ["water curtain", "curtain"]},
        {"name": "preaction", "element_keywords": ["preaction", "pre action"], "workset_keywords": ["preaction", "pre action"]},
        {"name": "dry", "element_keywords": ["dry", "dry sprinkler", "dry system", "dry pipe"], "workset_keywords": ["dry"]},
        {"name": "wet", "element_keywords": ["wet", "wet sprinkler", "wet system", "wet pipe"], "workset_keywords": ["wet"]},
        {"name": "hose", "element_keywords": ["hose", "fire hose", "hose reel", "reel"], "workset_keywords": ["hose", "fire hose", "hose reel", "reel"]},
        {"name": "sprinkler", "element_keywords": ["sprinkler", "sprinklers", "sprinkler head", "pendent", "upright", "sidewall"], "workset_keywords": ["sprinkler", "sprinklers", "sprinkler head", "head"]},
        {"name": "standpipe", "element_keywords": ["standpipe", "riser"], "workset_keywords": ["standpipe", "riser"]},
        {"name": "pump", "element_keywords": ["pump", "fire pump", "jockey pump"], "workset_keywords": ["pump", "fire pump", "jockey"]},
        {"name": "valve", "element_keywords": ["valve", "alarm valve", "control valve"], "workset_keywords": ["valve", "alarm valve", "control valve"]},
        {"name": "drain", "element_keywords": ["drain", "test drain", "main drain"], "workset_keywords": ["drain", "test drain"]},
        {"name": "flow", "element_keywords": ["flow", "flow meter", "flow switch", "waterflow"], "workset_keywords": ["flow", "flow meter", "flow switch", "waterflow"]}
    ]

    for group in keyword_groups:
        element_hit = False

        for keyword in group["element_keywords"]:
            if normalize_text(keyword) in search_text:
                element_hit = True
                break

        if not element_hit:
            continue

        for ws_name, ws_text in workset_data:
            for ws_keyword in group["workset_keywords"]:
                if normalize_text(ws_keyword) in ws_text:
                    return ws_name

        if group["name"] in ["hydrant", "deluge", "water curtain", "preaction", "dry", "wet", "hose"]:
            return "None"

    return "None"


def build_rows_from_elements(elements, workset_names):
    groups = {}

    for el in elements:
        cat = el.Category.Name
        fam, typ = get_family_and_type(el)
        sys_name = get_system_name(el)
        level_name = get_element_level_name(el)
        ws = get_workset_name(el)

        key = (cat, fam, typ, sys_name, level_name)

        if key not in groups:
            groups[key] = {
                "count": 0,
                "worksets": set(),
                "sample": el
            }

        groups[key]["count"] += 1
        groups[key]["worksets"].add(ws)

    rows = []

    for key in sorted(groups.keys()):
        cat, fam, typ, sys_name, level_name = key
        worksets = sorted(list(groups[key]["worksets"]))
        current_ws_text = ", ".join(worksets)
        count = groups[key]["count"]
        sample_element = groups[key]["sample"]
        target = guess_target_workset(sample_element, workset_names)

        rows.append(
            WorksetRow(
                False,
                cat,
                fam,
                typ,
                sys_name,
                level_name,
                current_ws_text,
                count,
                target
            )
        )

    return rows


def row_matches_element(row, element):
    if element.Category.Name != row.Category:
        return False

    family, type_name = get_family_and_type(element)
    system_name = get_system_name(element)
    level_name = get_element_level_name(element)

    if family != row.Family:
        return False
    if type_name != row.TypeName:
        return False
    if system_name != row.SystemName:
        return False
    if level_name != row.LevelName:
        return False

    return True


class BIMWorksetManager(forms.WPFWindow):
    def __init__(self):
        xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
        forms.WPFWindow.__init__(self, xaml_path)

        self.worksets = get_worksets()
        self.views = get_views()

        self.RealWorksetNames = [w.Name for w in self.worksets]
        self.WorksetNames = ["None"] + self.RealWorksetNames

        self.rows = ObservableCollection[object]()
        self.worksets_by_name = {w.Name: w for w in self.worksets}

        self.rowsGrid.DataContext = self
        self.rowsGrid.ItemsSource = self.rows

        self.zoneTargetWorksetCombo.ItemsSource = self.RealWorksetNames
        self.selectedViewCombo.ItemsSource = [
            "{} | ID {}".format(v.Name, get_id_value(v.Id)) for v in self.views
        ]

        self.categoryFilterCombo.ItemsSource = ["All"]
        self.systemFilterCombo.ItemsSource = ["All"]
        self.zoneCategoryFilterCombo.ItemsSource = ["All"]
        self.zoneSystemFilterCombo.ItemsSource = ["All"]

        if self.RealWorksetNames:
            self.zoneTargetWorksetCombo.SelectedIndex = 0

        if self.views:
            self.selectedViewCombo.SelectedIndex = 0

        self.categoryFilterCombo.SelectedIndex = 0
        self.systemFilterCombo.SelectedIndex = 0
        self.zoneCategoryFilterCombo.SelectedIndex = 0
        self.zoneSystemFilterCombo.SelectedIndex = 0

        self.workflowRulesRadio.IsChecked = True
        self.sourceCurrentViewRadio.IsChecked = True
        self.reportOnlyCheckBox.IsChecked = True

        self.reportOnlyCheckBox.Checked += self.refresh_run_state
        self.reportOnlyCheckBox.Unchecked += self.refresh_run_state

        self.refresh_scope_boxes_for_active_view()
        self.update_active_view_text()
        self.update_ui_mode()
        self.refresh_rows_click(None, None)
        self.refresh_zone_filters_click(None, None)

    def refresh_run_state(self, sender=None, args=None):
        try:
            self.runButton.IsEnabled = True
        except:
            pass

    def get_report_only(self):
        return True if self.reportOnlyCheckBox.IsChecked == True else False

    def update_active_view_text(self):
        text = get_active_view_display()
        self.currentViewText.Text = text
        self.zoneActiveViewText.Text = text

    def refresh_scope_boxes_for_active_view(self):
        self.scope_boxes = get_scope_boxes_in_active_view()
        self.scopeBoxCombo.ItemsSource = [s.Name for s in self.scope_boxes]

        if self.scope_boxes:
            self.scopeBoxCombo.SelectedIndex = 0
        else:
            self.scopeBoxCombo.ItemsSource = []
            self.statusText.Text = "No Scope Boxes visible in active view."

        self.refresh_run_state()

    def close_click(self, sender, args):
        self.Close()

    def workflow_changed(self, sender, args):
        self.update_active_view_text()
        self.refresh_scope_boxes_for_active_view()
        self.update_ui_mode()

        if self.workflowZoneRadio.IsChecked == True:
            self.refresh_zone_filters_click(None, None)

        self.refresh_run_state()

    def update_ui_mode(self):
        if self.workflowZoneRadio.IsChecked == True:
            self.zonePanel.Visibility = Visibility.Visible
            self.rulesPanel.Visibility = Visibility.Collapsed
            self.rulesSourcePanel.Visibility = Visibility.Collapsed
            self.filterPanel.Visibility = Visibility.Collapsed
            self.mappingInfoText.Text = "Zone Mode"
            self.mappingHelpText.Text = "Zone Mode uses ACTIVE VIEW + ACTIVE VIEW LEVEL. Scope Box list shows only Scope Boxes visible in active view."
            self.sourceNameText.Text = "Mode: Zone / Scope Box | Active View: {}".format(get_active_view_display())
        else:
            self.zonePanel.Visibility = Visibility.Collapsed
            self.rulesPanel.Visibility = Visibility.Visible
            self.rulesSourcePanel.Visibility = Visibility.Visible
            self.filterPanel.Visibility = Visibility.Visible
            self.mappingInfoText.Text = "Family / Type / System / Level Workset Mapping"
            self.mappingHelpText.Text = "Filter by Category or System Name. Table includes Level."
            self.sourceNameText.Text = "Mode: Family / Type Rules"

        self.refresh_run_state()

    def get_selected_scope(self):
        scope_name = self.scopeBoxCombo.SelectedItem
        if not scope_name:
            return None
        return next((s for s in self.scope_boxes if s.Name == scope_name), None)

    def get_selected_plan_view(self):
        index = self.selectedViewCombo.SelectedIndex
        if index < 0:
            return None
        return self.views[index]

    def get_zone_level_filter(self):
        active_level = get_active_view_level_name()
        return active_level if active_level else "All"

    def get_rule_level_filter(self):
        if self.sourceSelectedViewRadio.IsChecked == True:
            view = self.get_selected_plan_view()
            level_name = get_view_level_name(view)
            if level_name:
                return level_name

        if self.sourceCurrentViewRadio.IsChecked == True:
            level_name = get_active_view_level_name()
            if level_name:
                return level_name

        if self.sourceSelectionRadio.IsChecked == True:
            level_name = get_active_view_level_name()
            if level_name:
                return level_name

        return "All"

    def filter_by_level(self, elements, level_filter):
        if level_filter == "All":
            return elements
        return [el for el in elements if get_element_level_name(el) == level_filter]

    def get_zone_elements_raw(self):
        scope = self.get_selected_scope()
        if not scope:
            return []

        elements = get_elements_in_scope_xy(scope)
        level_filter = self.get_zone_level_filter()

        if level_filter != "All":
            elements = self.filter_by_level(elements, level_filter)

        return elements

    def get_zone_elements(self):
        scope = self.get_selected_scope()

        if not scope:
            forms.alert("No Scope Box visible/selected in active view.")
            return []

        category_filter = str(self.zoneCategoryFilterCombo.SelectedItem or "All")
        system_filter = str(self.zoneSystemFilterCombo.SelectedItem or "All")

        elements = self.get_zone_elements_raw()

        filtered = []
        for el in elements:
            if el.Id == scope.Id:
                continue

            category = el.Category.Name
            system_name = get_system_name(el)

            if category_filter != "All" and category != category_filter:
                continue

            if system_filter != "All" and system_name != system_filter:
                continue

            filtered.append(el)

        self.sourceNameText.Text = "Zone Source: {} | Active View: {} | Level: {}".format(
            scope.Name,
            doc.ActiveView.Name,
            self.get_zone_level_filter()
        )

        return filtered

    def refresh_zone_filters_click(self, sender, args):
        self.update_active_view_text()
        self.refresh_scope_boxes_for_active_view()

        elements = self.get_zone_elements_raw()

        categories = sorted(list(set([el.Category.Name for el in elements if el.Category])))
        systems = sorted(list(set([get_system_name(el) for el in elements])))

        categories = [c for c in categories if c]
        systems = [s for s in systems if s]

        categories.insert(0, "All")
        systems.insert(0, "All")

        self.zoneCategoryFilterCombo.ItemsSource = categories
        self.zoneSystemFilterCombo.ItemsSource = systems

        self.zoneCategoryFilterCombo.SelectedIndex = 0
        self.zoneSystemFilterCombo.SelectedIndex = 0

        self.statusText.Text = "Zone filters loaded. Active View: {} | Level: {} | Elements: {}".format(
            doc.ActiveView.Name,
            self.get_zone_level_filter(),
            len(elements)
        )

        self.refresh_run_state()

    def update_filter_dropdowns(self):
        categories = sorted(list(set([str(r.Category or "") for r in self.rows])))
        systems = sorted(list(set([str(r.SystemName or "") for r in self.rows])))

        categories = [c for c in categories if c]
        systems = [s for s in systems if s]

        categories.insert(0, "All")
        systems.insert(0, "All")

        self.categoryFilterCombo.ItemsSource = categories
        self.systemFilterCombo.ItemsSource = systems

        self.categoryFilterCombo.SelectedIndex = 0
        self.systemFilterCombo.SelectedIndex = 0

        self.refresh_run_state()

    def apply_filter_click(self, sender, args):
        category_filter = str(self.categoryFilterCombo.SelectedItem or "All")
        system_filter = str(self.systemFilterCombo.SelectedItem or "All")

        view = CollectionViewSource.GetDefaultView(self.rowsGrid.ItemsSource)

        def row_filter(row):
            if category_filter != "All" and str(row.Category or "") != category_filter:
                return False
            if system_filter != "All" and str(row.SystemName or "") != system_filter:
                return False
            return True

        view.Filter = row_filter
        view.Refresh()

        visible_count = 0
        try:
            for item in view:
                visible_count += 1
        except:
            pass

        self.statusText.Text = "Filters applied. Visible rows: {}".format(visible_count)
        self.refresh_run_state()

    def clear_filter_click(self, sender, args):
        if self.categoryFilterCombo.Items.Count > 0:
            self.categoryFilterCombo.SelectedIndex = 0

        if self.systemFilterCombo.Items.Count > 0:
            self.systemFilterCombo.SelectedIndex = 0

        view = CollectionViewSource.GetDefaultView(self.rowsGrid.ItemsSource)
        view.Filter = None
        view.Refresh()

        self.statusText.Text = "Filters cleared."
        self.refresh_run_state()

    def get_rule_source_elements(self):
        level_filter = self.get_rule_level_filter()

        if self.sourceSelectionRadio.IsChecked == True:
            self.sourceNameText.Text = "Source: Current Revit Selection | Level Filter: {}".format(level_filter)
            return self.filter_by_level(get_selected_movable_elements(), level_filter)

        if self.sourceCurrentViewRadio.IsChecked == True:
            view = doc.ActiveView
            self.sourceNameText.Text = "Source: Current Active View - {} | ID {} | Level Filter: {}".format(
                view.Name,
                get_id_value(view.Id),
                level_filter
            )
            return self.filter_by_level(get_elements_in_view(view), level_filter)

        if self.sourceSelectedViewRadio.IsChecked == True:
            view = self.get_selected_plan_view()

            if not view:
                forms.alert("Please select a view.")
                return []

            self.sourceNameText.Text = "Source: Selected View - {} | ID {} | Selected View Level: {}".format(
                view.Name,
                get_id_value(view.Id),
                level_filter
            )

            return self.filter_by_level(get_elements_in_view(view), level_filter)

        return []

    def refresh_rows_click(self, sender, args):
        elements = self.get_rule_source_elements()
        self.rows.Clear()

        if not elements:
            self.update_filter_dropdowns()
            self.statusText.Text = "No valid movable elements found. Check selected view level."
            self.refresh_run_state()
            return

        rows = build_rows_from_elements(elements, self.RealWorksetNames)

        for row in rows:
            self.rows.Add(row)

        self.update_filter_dropdowns()

        view = CollectionViewSource.GetDefaultView(self.rowsGrid.ItemsSource)
        view.Filter = None
        view.Refresh()

        self.statusText.Text = "Loaded {} elements / {} rows. Level-aware filter active.".format(
            len(elements),
            len(rows)
        )

        self.refresh_run_state()

    def check_all_click(self, sender, args):
        for row in self.rows:
            row.Enabled = True
        self.rowsGrid.Items.Refresh()
        self.refresh_run_state()

    def uncheck_all_click(self, sender, args):
        for row in self.rows:
            row.Enabled = False
        self.rowsGrid.Items.Refresh()
        self.refresh_run_state()

    def run_zone_mode(self):
        elements = self.get_zone_elements()

        if not elements:
            forms.alert("No valid movable elements found inside selected Scope Box / active view level / filters.")
            return

        target_ws_name = self.zoneTargetWorksetCombo.SelectedItem

        if not target_ws_name:
            forms.alert("Please select a target workset.")
            return

        target_ws = self.worksets_by_name.get(str(target_ws_name))

        if not target_ws:
            forms.alert("Target workset not found.")
            return

        report_only = self.get_report_only()

        checked = wrong = moved = skipped = 0
        results = []

        with revit.Transaction("BIM Workset Manager - Zone Mode"):
            for el in elements:
                checked += 1

                current_ws = get_workset_name(el)
                category = el.Category.Name
                family, type_name = get_family_and_type(el)
                system_name = get_system_name(el)
                level_name = get_element_level_name(el)

                if current_ws != target_ws_name:
                    wrong += 1

                    if report_only:
                        status = "Wrong - Report Only"
                    else:
                        if set_element_workset(el, target_ws):
                            moved += 1
                            status = "Moved"
                        else:
                            skipped += 1
                            status = "Cannot move"

                    results.append([
                        get_id_value(el.Id),
                        category,
                        family,
                        type_name,
                        system_name,
                        level_name,
                        current_ws,
                        target_ws_name,
                        status
                    ])

        show_report_window(
            "BIM Workset Manager - Zone Report",
            [
                "Zone Source: {}".format(self.sourceNameText.Text),
                "Scope Box itself was not processed.",
                "Report Only: {}".format(report_only),
                "Target Workset: {}".format(target_ws_name),
                "Elements checked: {}".format(checked),
                "Elements moved: {}".format(moved),
                "Skipped: {}".format(skipped)
            ],
            results,
            [
                "Element ID",
                "Category",
                "Family",
                "Type",
                "System Name",
                "Level",
                "Current Workset",
                "Target Workset",
                "Status"
            ]
        )

        self.statusText.Text = "Zone run done | Report Only: {} | Checked: {} | Moved: {} | Skipped: {}".format(
            report_only,
            checked,
            moved,
            skipped
        )

        self.refresh_run_state()

    def run_rules_mode(self):
        elements = self.get_rule_source_elements()

        if not elements:
            forms.alert("No valid movable elements found.")
            return

        active_rows = [r for r in self.rows if r.Enabled]

        if not active_rows:
            forms.alert("Please tick at least one row.")
            return

        report_only = self.get_report_only()

        checked = matched = wrong = moved = skipped = no_target = 0
        results = []

        with revit.Transaction("BIM Workset Manager - Rules Mode"):
            for el in elements:
                checked += 1
                matched_row = None

                for row in active_rows:
                    if row_matches_element(row, el):
                        matched_row = row
                        break

                if not matched_row:
                    continue

                matched += 1
                target_ws_name = str(matched_row.TargetWorkset or "")

                category = el.Category.Name
                family, type_name = get_family_and_type(el)
                system_name = get_system_name(el)
                level_name = get_element_level_name(el)
                current_ws = get_workset_name(el)

                if target_ws_name == "None" or target_ws_name == "":
                    no_target += 1
                    results.append([
                        get_id_value(el.Id),
                        category,
                        family,
                        type_name,
                        system_name,
                        level_name,
                        current_ws,
                        "None",
                        "Skipped - No target"
                    ])
                    continue

                target_ws = self.worksets_by_name.get(target_ws_name)

                if not target_ws:
                    skipped += 1
                    results.append([
                        get_id_value(el.Id),
                        category,
                        family,
                        type_name,
                        system_name,
                        level_name,
                        current_ws,
                        target_ws_name,
                        "Target workset not found"
                    ])
                    continue

                if current_ws != target_ws_name:
                    wrong += 1

                    if report_only:
                        status = "Wrong - Report Only"
                    else:
                        if set_element_workset(el, target_ws):
                            moved += 1
                            status = "Moved"
                        else:
                            skipped += 1
                            status = "Cannot move"

                    results.append([
                        get_id_value(el.Id),
                        category,
                        family,
                        type_name,
                        system_name,
                        level_name,
                        current_ws,
                        target_ws_name,
                        status
                    ])

        show_report_window(
            "BIM Workset Manager - Rules Report",
            [
                "Source: {}".format(self.sourceNameText.Text),
                "Report Only: {}".format(report_only),
                "Elements checked: {}".format(checked),
                "Elements matched: {}".format(matched),
                "Elements with Target None: {}".format(no_target),
                "Elements on wrong workset: {}".format(wrong),
                "Elements moved: {}".format(moved),
                "Skipped: {}".format(skipped)
            ],
            results,
            [
                "Element ID",
                "Category",
                "Family",
                "Type",
                "System Name",
                "Level",
                "Current Workset",
                "Target Workset",
                "Status"
            ]
        )

        self.statusText.Text = "Rules run done | Report Only: {} | Checked: {} | Matched: {} | Wrong: {} | Moved: {}".format(
            report_only,
            checked,
            matched,
            wrong,
            moved
        )

        self.refresh_run_state()

    def run_click(self, sender, args):
        try:
            self.runButton.IsEnabled = False

            if self.workflowZoneRadio.IsChecked == True:
                self.run_zone_mode()
            else:
                self.run_rules_mode()

        except Exception as ex:
            forms.alert("BIM Workset Manager error:\n\n{}".format(ex))

        finally:
            self.runButton.IsEnabled = True


window = BIMWorksetManager()
window.ShowDialog()