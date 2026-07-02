# -*- coding: utf-8 -*-

import clr
import re
import os
import tempfile

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from pyrevit import revit, forms
from Autodesk.Revit.DB import *
from System.Collections.Generic import List
from System.Windows import Thickness
from System.Windows.Controls import CheckBox, GroupBox, WrapPanel, TabItem, StackPanel


doc = revit.doc
uidoc = revit.uidoc
app = doc.Application

SCRIPT_TITLE = "Select All Like"

RUN_PARAM = "BIMBOT_SAL_Run"

PARAM_GROUPS = [
    ("Pipes", "Pipe Segments", ["Pipe Segment", "Segment"]),
    ("Pipes", "Pipe Types", ["Type Name"]),
    ("Pipes", "Nominal Diameter", ["Diameter", "Nominal Diameter", "Size", "Pipe Size"]),

    ("Family Instances", "Family Instances", ["Family and Type", "Family", "Type Name"]),
    ("Family Instances", "Family Size", ["Family Size", "Size", "Nominal Size"]),
    ("Family Instances", "K-Factor", ["K-Factor", "K Factor", "KFactor"]),

    ("Flex Pipes", "Diameter", ["Diameter", "Nominal Diameter", "Size", "Pipe Size"]),

    ("Tags", "Tag Types", ["Type Name", "Family and Type"]),
]


def id_value(eid):
    try:
        return eid.IntegerValue
    except:
        try:
            return eid.Value
        except:
            return int(str(eid))


def bic_id(bic):
    try:
        return id_value(ElementId(bic))
    except:
        return None


PIPE_CATS = [bic_id(BuiltInCategory.OST_PipeCurves)]
FLEX_PIPE_CATS = [bic_id(BuiltInCategory.OST_FlexPipeCurves)]

FAMILY_INSTANCE_CATS = [
    bic_id(BuiltInCategory.OST_Sprinklers),
    bic_id(BuiltInCategory.OST_PipeFitting),
    bic_id(BuiltInCategory.OST_PipeAccessory),
    bic_id(BuiltInCategory.OST_MechanicalEquipment),
    bic_id(BuiltInCategory.OST_PlumbingFixtures),
    bic_id(BuiltInCategory.OST_GenericModel),
    bic_id(BuiltInCategory.OST_FireAlarmDevices),
    bic_id(BuiltInCategory.OST_ElectricalEquipment),
]

TAG_CATS = [
    bic_id(BuiltInCategory.OST_PipeTags),
    bic_id(BuiltInCategory.OST_PipeFittingTags),
    bic_id(BuiltInCategory.OST_PipeAccessoryTags),
    bic_id(BuiltInCategory.OST_SprinklerTags),
    bic_id(BuiltInCategory.OST_MechanicalEquipmentTags),
]


def safe_name(element):
    try:
        return element.Name
    except:
        return ""


def category_name(element):
    try:
        if element.Category:
            return element.Category.Name
    except:
        pass
    return ""


def get_cat_id(element):
    try:
        if element.Category:
            return id_value(element.Category.Id)
    except:
        pass
    return None


def normalize(value):
    try:
        return str(value).lower().replace(" ", "").replace("_", "").replace("-", "").replace("ø", "").strip()
    except:
        return ""


def clean_dn_label(value):
    txt = str(value).replace("Ø", "").replace("ø", "")
    nums = re.findall(r"\d+(?:\.\d+)?", txt)

    if nums:
        result = []
        for n in nums:
            if n.endswith(".0"):
                n = n[:-2]
            result.append("DN " + n)
        return " - ".join(result)

    return txt


def display_value(group_name, raw_value):
    if group_name in ["Family Size", "Nominal Diameter", "Diameter"]:
        return clean_dn_label(raw_value)
    return raw_value


def storage_value(param):
    try:
        if param.StorageType == StorageType.String:
            return param.AsString() or ""

        if param.StorageType == StorageType.Integer:
            return str(param.AsInteger())

        if param.StorageType == StorageType.Double:
            return param.AsValueString() or str(round(param.AsDouble(), 6))

        if param.StorageType == StorageType.ElementId:
            eid = param.AsElementId()
            ref = doc.GetElement(eid)
            if ref:
                return safe_name(ref)
            return str(id_value(eid))
    except:
        pass

    return ""


def lookup_param_value(element, param_names):
    for pname in param_names:
        try:
            p = element.LookupParameter(pname)
            if p:
                v = storage_value(p)
                if v:
                    return v
        except:
            pass

    try:
        type_element = doc.GetElement(element.GetTypeId())
        if type_element:
            for pname in param_names:
                try:
                    p = type_element.LookupParameter(pname)
                    if p:
                        v = storage_value(p)
                        if v:
                            return v
                except:
                    pass
    except:
        pass

    return ""


def get_family_name(element):
    try:
        return element.Symbol.Family.Name
    except:
        pass

    try:
        type_element = doc.GetElement(element.GetTypeId())
        if type_element:
            return type_element.FamilyName
    except:
        pass

    return ""


def get_type_name(element):
    try:
        return element.Symbol.Name
    except:
        pass

    try:
        type_element = doc.GetElement(element.GetTypeId())
        if type_element:
            return safe_name(type_element)
    except:
        pass

    return ""


def get_system_name(element):
    try:
        p = element.LookupParameter("System Name")
        if p:
            return storage_value(p)
    except:
        pass
    return ""


def get_group_value(element, group_name, param_names):
    if group_name in ["Pipe Types", "Tag Types"]:
        return get_type_name(element)

    if group_name == "Family Instances":
        typ = get_type_name(element)
        fam = get_family_name(element)

        if typ:
            return typ
        if fam:
            return fam

        return safe_name(element)

    return lookup_param_value(element, param_names)


def get_search_text_for_element(element):
    parts = [
        get_family_name(element),
        get_type_name(element),
        get_system_name(element),
        category_name(element),
        safe_name(element)
    ]

    return normalize(" ".join([p for p in parts if p]))


def element_matches_search(element, search_text):
    if not search_text:
        return True

    return search_text in get_search_text_for_element(element)


def element_belongs_to_tab(element, tab_name):
    cid = get_cat_id(element)
    cname = category_name(element).lower()

    if tab_name == "Pipes":
        return cid in PIPE_CATS or cname == "pipes"

    if tab_name == "Flex Pipes":
        return cid in FLEX_PIPE_CATS or "flex pipe" in cname

    if tab_name == "Family Instances":
        return cid in FAMILY_INSTANCE_CATS

    if tab_name == "Tags":
        return cid in TAG_CATS or "tag" in cname

    return False


def get_project_elements():
    return list(
        FilteredElementCollector(doc)
        .WhereElementIsNotElementType()
    )


def get_project_levels():
    levels = []

    for lvl in FilteredElementCollector(doc).OfClass(Level):
        try:
            levels.append((lvl.Elevation, safe_name(lvl)))
        except:
            pass

    levels = sorted(levels, key=lambda x: x[0])

    result = ["All Levels"]

    for elev, name in levels:
        if name and name not in result:
            result.append(name)

    return result


def get_element_level_name(element):
    try:
        if hasattr(element, "LevelId"):
            lid = element.LevelId
            if lid and id_value(lid) > 0:
                lvl = doc.GetElement(lid)
                if lvl:
                    return safe_name(lvl)
    except:
        pass

    bips = [
        BuiltInParameter.FAMILY_LEVEL_PARAM,
        BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
        BuiltInParameter.SCHEDULE_LEVEL_PARAM,
        BuiltInParameter.RBS_START_LEVEL_PARAM,
        BuiltInParameter.RBS_REFERENCE_LEVEL_PARAM,
    ]

    for bip in bips:
        try:
            p = element.get_Parameter(bip)
            if p:
                v = storage_value(p)
                if v:
                    return v
        except:
            pass

    names = [
        "Level",
        "Reference Level",
        "Schedule Level",
        "Base Level",
        "Start Level",
        "Host Level",
        "Work Plane"
    ]

    for n in names:
        try:
            p = element.LookupParameter(n)
            if p:
                v = storage_value(p)
                if v:
                    return v
        except:
            pass

    return ""


def filter_elements_by_level(elements, level_name):
    if not level_name or level_name == "All Levels":
        return elements

    result = []

    for e in elements:
        try:
            if get_element_level_name(e) == level_name:
                result.append(e)
        except:
            pass

    return result


def build_options(elements, level_name, search_text):
    options_by_tab = {}
    filtered_elements = filter_elements_by_level(elements, level_name)

    for tab_name, group_name, param_names in PARAM_GROUPS:
        values = {}

        for e in filtered_elements:
            try:
                if not element_belongs_to_tab(e, tab_name):
                    continue

                if not element_matches_search(e, search_text):
                    continue

                raw_value = get_group_value(e, group_name, param_names)

                if raw_value:
                    values[raw_value] = display_value(group_name, raw_value)
            except:
                pass

        if values:
            if tab_name not in options_by_tab:
                options_by_tab[tab_name] = []

            options_by_tab[tab_name].append({
                "tab_name": tab_name,
                "group_name": group_name,
                "values": values,
                "level_name": level_name
            })

    return options_by_tab


def find_param_names_for_group(group_name):
    for tab_name, gname, param_names in PARAM_GROUPS:
        if gname == group_name:
            return param_names
    return []


def element_matches_record(element, record):
    tab_name = record["tab"]
    level_name = record["level"]
    group_name = record["group"]
    selected_value = record["value"]

    if not element_belongs_to_tab(element, tab_name):
        return False

    if level_name != "All Levels":
        if get_element_level_name(element) != level_name:
            return False

    param_names = find_param_names_for_group(group_name)
    value = get_group_value(element, group_name, param_names)

    return value == selected_value


def get_matching_elements(selected_records, elements):
    matched_ids = {}
    matched = []

    for e in elements:
        try:
            for rec in selected_records:
                if element_matches_record(e, rec):
                    eid = id_value(e.Id)
                    if eid not in matched_ids:
                        matched_ids[eid] = True
                        matched.append(e)
                    break
        except:
            pass

    return matched


def select_elements(elements):
    ids = List[ElementId]()

    for e in elements:
        try:
            ids.Add(e.Id)
        except:
            pass

    uidoc.Selection.SetElementIds(ids)
    return ids.Count


def clear_selection():
    uidoc.Selection.SetElementIds(List[ElementId]())


def get_or_create_shared_param(param_name):
    original_file = app.SharedParametersFilename
    temp_file = os.path.join(tempfile.gettempdir(), "BIMBOT_SelectAllLike_SharedParameters.txt")

    if not os.path.exists(temp_file):
        open(temp_file, "w").close()

    app.SharedParametersFilename = temp_file
    shared_file = app.OpenSharedParameterFile()

    if not shared_file:
        app.SharedParametersFilename = original_file
        raise Exception("Could not open shared parameter file.")

    group = None

    for g in shared_file.Groups:
        if g.Name == "BIMBOT":
            group = g
            break

    if not group:
        group = shared_file.Groups.Create("BIMBOT")

    definition = None

    for d in group.Definitions:
        if d.Name == param_name:
            definition = d
            break

    if not definition:
        try:
            opt = ExternalDefinitionCreationOptions(param_name, SpecTypeId.String.Text)
        except:
            opt = ExternalDefinitionCreationOptions(param_name, ParameterType.Text)

        definition = group.Definitions.Create(opt)

    app.SharedParametersFilename = original_file
    return definition


def bind_run_parameter(elements):
    cats = app.Create.NewCategorySet()
    added = {}

    for e in elements:
        try:
            if e.Category and e.Category.AllowsBoundParameters:
                cid = id_value(e.Category.Id)
                if cid not in added:
                    cats.Insert(e.Category)
                    added[cid] = True
        except:
            pass

    if cats.IsEmpty:
        raise Exception("No valid categories found for binding parameter.")

    binding = app.Create.NewInstanceBinding(cats)
    definition = get_or_create_shared_param(RUN_PARAM)

    try:
        inserted = doc.ParameterBindings.Insert(definition, binding, BuiltInParameterGroup.PG_DATA)
        if not inserted:
            doc.ParameterBindings.ReInsert(definition, binding, BuiltInParameterGroup.PG_DATA)
    except:
        try:
            doc.ParameterBindings.ReInsert(definition, binding, BuiltInParameterGroup.PG_DATA)
        except:
            pass


def set_text_param(element, param_name, value):
    try:
        p = element.LookupParameter(param_name)
        if p and not p.IsReadOnly:
            p.Set(str(value))
    except:
        pass


def mark_elements_for_schedule(elements, run_id):
    for e in elements:
        set_text_param(e, RUN_PARAM, run_id)


def schedule_field_by_name(schedule_def, field_name):
    fields = schedule_def.GetSchedulableFields()

    for sf in fields:
        try:
            if sf.GetName(doc) == field_name:
                return sf
        except:
            pass

    return None


def add_field_by_name(schedule_def, field_name):
    sf = schedule_field_by_name(schedule_def, field_name)

    if not sf:
        return None

    try:
        return schedule_def.AddField(sf)
    except:
        return None


def try_add_first_available_field(schedule_def, field_names):
    for fname in field_names:
        try:
            field = add_field_by_name(schedule_def, fname)
            if field:
                return field
        except:
            pass
    return None


def get_schedule_category_ids(elements):
    cats = {}

    for e in elements:
        try:
            if e.Category:
                cid = id_value(e.Category.Id)
                if cid not in cats:
                    cats[cid] = e.Category
        except:
            pass

    return cats.values()


def unique_schedule_name(base_name):
    existing = set()

    for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            existing.add(v.Name)
        except:
            pass

    if base_name not in existing:
        return base_name

    index = 1
    while True:
        name = "{}_{:02d}".format(base_name, index)
        if name not in existing:
            return name
        index += 1


def category_schedule_name(category):
    try:
        return category.Name
    except:
        return "Schedule"


def create_schedule_for_category(category, run_id):
    schedule = ViewSchedule.CreateSchedule(doc, category.Id)
    schedule.Name = unique_schedule_name(category_schedule_name(category))

    definition = schedule.Definition
    definition.IsItemized = False

    run_field = add_field_by_name(definition, RUN_PARAM)

    if run_field:
        try:
            definition.AddFilter(
                ScheduleFilter(run_field.FieldId, ScheduleFilterType.Equal, run_id)
            )
            run_field.IsHidden = True
        except:
            pass

    family_type_field = try_add_first_available_field(
        definition,
        [
            "Family and Type",
            "Type",
            "Type Name",
            "Family"
        ]
    )

    size_field = try_add_first_available_field(
        definition,
        [
            "Size",
            "Diameter",
            "Nominal Diameter"
        ]
    )

    length_field = try_add_first_available_field(
        definition,
        [
            "Length",
            "Lungime"
        ]
    )

    try:
        count_field = definition.AddField(ScheduleFieldType.Count)
    except:
        count_field = None

    if family_type_field:
        try:
            definition.AddSortGroupField(
                ScheduleSortGroupField(family_type_field.FieldId)
            )
        except:
            pass

    if size_field:
        try:
            definition.AddSortGroupField(
                ScheduleSortGroupField(size_field.FieldId)
            )
        except:
            pass

    if length_field:
        try:
            length_field.DisplayType = ScheduleFieldDisplayType.Totals
        except:
            pass

    try:
        definition.ShowGrandTotal = True
        definition.ShowGrandTotalTitle = True
        definition.ShowGrandTotalCount = True
    except:
        pass

    return schedule


def save_as_revit_schedules(elements):
    if not elements:
        forms.alert("No elements selected for schedule.", title=SCRIPT_TITLE)
        return

    run_id = "SAL"

    with revit.Transaction("BIMBOT Save Select All Like Schedule"):
        bind_run_parameter(elements)
        mark_elements_for_schedule(elements, run_id)

        categories = get_schedule_category_ids(elements)
        created = []

        for cat in categories:
            try:
                sch = create_schedule_for_category(cat, run_id)
                created.append(sch.Name)
            except:
                pass

    if created:
        forms.alert(
            "Revit schedules created:\n\n" + "\n".join(created),
            title="Save in Revit",
            warn_icon=False
        )
    else:
        forms.alert("No schedules were created.", title=SCRIPT_TITLE)


class SelectAllLikeWindow(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.WPFWindow.__init__(self, xaml_file)

        self.txtSearch.TextChanged += self.txtSearch_TextChanged
        self.cmbLevel.SelectionChanged += self.cmbLevel_SelectionChanged
        self.btnSave.Click += self.btnSave_Click
        self.btnClear.Click += self.btnClear_Click
        self.btnExit.Click += self.btnExit_Click

        self.project_elements = get_project_elements()
        self.level_names = get_project_levels()
        self.checkboxes = []
        self.checked_records = {}
        self.is_clearing = False
        self.matched_elements = []

        self.load_levels()
        self.rebuild_tabs()
        self.update_count()

    def load_levels(self):
        self.cmbLevel.Items.Clear()

        for lvl in self.level_names:
            self.cmbLevel.Items.Add(lvl)

        self.cmbLevel.SelectedIndex = 0

    def current_level(self):
        try:
            return str(self.cmbLevel.SelectedItem)
        except:
            return "All Levels"

    def current_search(self):
        try:
            return normalize(self.txtSearch.Text)
        except:
            return ""

    def make_key(self, tab_name, level_name, group_name, raw_value):
        return tab_name + "||" + level_name + "||" + group_name + "||" + raw_value

    def save_current_checks(self):
        if self.is_clearing:
            return

        for cb in self.checkboxes:
            try:
                key = str(cb.Tag)

                if cb.IsChecked:
                    self.checked_records[key] = True
                elif key in self.checked_records:
                    del self.checked_records[key]
            except:
                pass

    def rebuild_tabs(self):
        self.save_current_checks()

        level_name = self.current_level()
        search_text = self.current_search()

        options_by_tab = build_options(
            self.project_elements,
            level_name,
            search_text
        )

        self.tabOptions.Items.Clear()
        self.checkboxes = []

        for tab_name in ["Pipes", "Family Instances", "Flex Pipes", "Tags"]:
            tab = TabItem()
            tab.Header = tab_name

            panel = StackPanel()
            panel.Margin = Thickness(6)

            if tab_name in options_by_tab:
                for data in options_by_tab[tab_name]:
                    gb = GroupBox()
                    gb.Header = data["group_name"]
                    gb.Margin = Thickness(4)

                    wrap = WrapPanel()
                    wrap.Margin = Thickness(4)

                    sorted_items = sorted(data["values"].items(), key=lambda x: x[1])

                    for raw_value, label_value in sorted_items:
                        key = self.make_key(
                            tab_name,
                            level_name,
                            data["group_name"],
                            raw_value
                        )

                        cb = CheckBox()
                        cb.Content = label_value
                        cb.Tag = key
                        cb.Margin = Thickness(8, 4, 18, 4)
                        cb.MinWidth = 170

                        if key in self.checked_records:
                            cb.IsChecked = True

                        cb.Checked += self.checkbox_changed
                        cb.Unchecked += self.checkbox_changed

                        wrap.Children.Add(cb)
                        self.checkboxes.append(cb)

                    gb.Content = wrap
                    panel.Children.Add(gb)

            tab.Content = panel
            self.tabOptions.Items.Add(tab)

        self.update_count()

    def get_selected_records(self):
        self.save_current_checks()

        records = []

        for key in self.checked_records.keys():
            try:
                parts = key.split("||")
                if len(parts) >= 4:
                    records.append({
                        "tab": parts[0],
                        "level": parts[1],
                        "group": parts[2],
                        "value": "||".join(parts[3:])
                    })
            except:
                pass

        return records

    def update_count(self):
        records = self.get_selected_records()

        if not records:
            self.matched_elements = []
            self.txtCount.Text = "Count: 0"
            clear_selection()
            return

        self.matched_elements = get_matching_elements(records, self.project_elements)
        self.txtCount.Text = "Count: {0}".format(len(self.matched_elements))
        select_elements(self.matched_elements)

    def checkbox_changed(self, sender, args):
        if self.is_clearing:
            return
        self.update_count()

    def cmbLevel_SelectionChanged(self, sender, args):
        try:
            self.rebuild_tabs()
        except:
            pass

    def txtSearch_TextChanged(self, sender, args):
        try:
            self.rebuild_tabs()
        except:
            pass

    def btnSave_Click(self, sender, args):
        self.update_count()

        if not self.matched_elements:
            forms.alert("No elements selected.", title=SCRIPT_TITLE)
            return

        save_as_revit_schedules(self.matched_elements)

    def btnClear_Click(self, sender, args):
        self.is_clearing = True
        self.checked_records = {}

        for cb in self.checkboxes:
            try:
                cb.IsChecked = False
            except:
                pass

        self.is_clearing = False
        self.matched_elements = []
        self.txtCount.Text = "Count: 0"
        clear_selection()

    def btnExit_Click(self, sender, args):
        self.Close()


try:
    xaml_file = __file__.replace("script.py", "ui.xaml")
    win = SelectAllLikeWindow(xaml_file)
    win.ShowDialog()

except Exception as ex:
    forms.alert(str(ex), title=SCRIPT_TITLE)