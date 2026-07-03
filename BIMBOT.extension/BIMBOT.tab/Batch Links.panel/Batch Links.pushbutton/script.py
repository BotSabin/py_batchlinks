# -*- coding: utf-8 -*-

from pyrevit import revit, forms, script
from pyrevit.forms import WPFWindow
from Autodesk.Revit.DB import *
from Microsoft.Win32 import OpenFileDialog
from System.Collections.Generic import Dictionary
from System import String
from System.Windows.Media import VisualTreeHelper
from System.Windows.Controls import ListViewItem
import os
import clr
import System
import json

doc = revit.doc
uidoc = __revit__.ActiveUIDocument
output = script.get_output()

SCRIPT_DIR = os.path.dirname(__file__)
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")


def load_json_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except:
        return {}


def save_json_settings(data):
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as ex:
        output.print_md("Could not save settings: {}".format(ex))
        return False


def load_ifc_engine():
    revit_exe = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName
    revit_folder = os.path.dirname(revit_exe)

    for dll in ["Revit.IFC.Common.dll", "Revit.IFC.Import.Core.dll", "Revit.IFC.Import.dll"]:
        path = os.path.join(revit_folder, dll)
        if os.path.exists(path):
            try:
                clr.AddReferenceToFileAndPath(path)
            except:
                pass


def resolve_path(path):
    if not path:
        return "Unknown"

    path = path.strip()

    if os.path.isabs(path):
        return path

    candidates = []

    try:
        host_path = doc.PathName
        if host_path:
            host_dir = os.path.dirname(host_path)
            candidates.append(os.path.abspath(os.path.join(host_dir, path)))
    except:
        pass

    try:
        user_home = os.path.expanduser("~")
        candidates.append(os.path.abspath(os.path.join(user_home, path)))
        candidates.append(os.path.abspath(os.path.join(user_home, path.replace("..\\", ""))))
        candidates.append(os.path.abspath(os.path.join(user_home, "Downloads", os.path.basename(path))))
        candidates.append(os.path.abspath(os.path.join(user_home, "Documents", os.path.basename(path))))
    except:
        pass

    candidates.append(path)

    for c in candidates:
        try:
            if c and os.path.exists(c):
                return c
        except:
            pass

    return path


class LinkRow(object):
    def __init__(self, inst):
        self.instance = inst
        self.link_type = doc.GetElement(inst.GetTypeId())
        self.checked = False

        self.name = self.get_name()
        self.status = self.get_status()
        self.typeid = self.link_type.Id.IntegerValue
        self.link_kind = self.get_kind()
        self.workset_name = self.get_workset_name()

        self.path = self.get_path()
        self.full_path = resolve_path(self.path)

        self.source_size = self.get_source_size()
        self.cache_size = self.get_cache_size()
        self.size = self.cache_size if self.link_kind == "IFC" else self.source_size

    def get_name(self):
        try:
            ldoc = self.instance.GetLinkDocument()
            if ldoc:
                return ldoc.Title
        except:
            pass

        try:
            return Element.Name.GetValue(self.link_type)
        except:
            return "Unknown Link"

    def get_status(self):
        try:
            return "Loaded" if self.instance.GetLinkDocument() else "Unloaded"
        except:
            return "Unloaded"

    def get_kind(self):
        if ".ifc" in self.name.lower():
            return "IFC"
        return "RVT"

    def get_workset_name(self):
        try:
            p = self.instance.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
            if p:
                ws_id = WorksetId(p.AsInteger())
                ws = doc.GetWorksetTable().GetWorkset(ws_id)
                if ws:
                    return ws.Name
        except:
            pass

        return "Unknown"

    def get_path(self):
        paths = []

        try:
            ext_ref = ExternalFileUtils.GetExternalFileReference(doc, self.link_type.Id)
            if ext_ref:
                model_path = ext_ref.GetPath()
                user_path = ModelPathUtils.ConvertModelPathToUserVisiblePath(model_path)
                if user_path:
                    paths.append(user_path)
        except:
            pass

        try:
            ldoc = self.instance.GetLinkDocument()
            if ldoc and ldoc.PathName:
                paths.append(ldoc.PathName)
        except:
            pass

        for p in paths:
            if p:
                return p

        return "Unknown"

    def get_ifc_source_path(self):
        path = self.full_path

        if path and path != "Unknown" and path.lower().endswith(".ifc"):
            return path

        if path and path.lower().endswith(".ifc.rvt"):
            possible = path[:-4]
            if os.path.exists(possible):
                return possible

        filename = self.name
        if not filename.lower().endswith(".ifc"):
            filename = filename + ".ifc"

        roots = [
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Documents")
        ]

        for root in roots:
            candidate = os.path.join(root, filename)
            if os.path.exists(candidate):
                return candidate

        return "Unknown"

    def get_ifc_cache_path(self):
        source = self.get_ifc_source_path()

        if source and source != "Unknown":
            cache = source + ".RVT"
            if os.path.exists(cache):
                return cache

            cache = source + ".rvt"
            if os.path.exists(cache):
                return cache

        path = self.full_path
        if path and path != "Unknown" and path.lower().endswith(".rvt"):
            return path

        return "Unknown"

    def get_source_size(self):
        try:
            if self.link_kind == "IFC":
                source = self.get_ifc_source_path()
                if source != "Unknown" and os.path.exists(source):
                    return self.format_size(os.path.getsize(source))
                return "Unknown"

            if self.full_path and self.full_path != "Unknown" and os.path.exists(self.full_path):
                return self.format_size(os.path.getsize(self.full_path))

        except Exception as ex:
            output.print_md("Source size read error: {}".format(ex))

        return "Unknown"

    def get_cache_size(self):
        try:
            if self.link_kind == "IFC":
                cache = self.get_ifc_cache_path()
                if cache != "Unknown" and os.path.exists(cache):
                    return self.format_size(os.path.getsize(cache))
                return "Unknown"

            return self.source_size

        except Exception as ex:
            output.print_md("Cache size read error: {}".format(ex))

        return "Unknown"

    def format_size(self, size_bytes):
        try:
            size_bytes = float(size_bytes)

            if size_bytes < 1024:
                return "{} B".format(int(size_bytes))
            elif size_bytes < 1024 * 1024:
                return "{:.1f} KB".format(size_bytes / 1024)
            elif size_bytes < 1024 * 1024 * 1024:
                return "{:.1f} MB".format(size_bytes / (1024 * 1024))
            else:
                return "{:.2f} GB".format(size_bytes / (1024 * 1024 * 1024))
        except:
            return "Unknown"


class LinkManagerWindow(WPFWindow):
    def __init__(self, xaml_file):
        WPFWindow.__init__(self, xaml_file)

        self.rows = []
        self.all_rows = []
        self.cancel_requested = False
        self.current_filter = "ALL"

        self.populate_workset_combos()
        self.load_settings()
        self.reload_ui_rows()

        try:
            self.Closing += self.window_closing
        except:
            pass

    def window_closing(self, sender, args):
        save_json_settings(self.collect_settings())

    def populate_workset_combos(self):
        try:
            self.cmbNewLinkWorkset.Items.Clear()
            self.cmbCurrentWorkset.Items.Clear()

            if not doc.IsWorkshared:
                self.cmbNewLinkWorkset.Items.Add("Not Workshared")
                self.cmbCurrentWorkset.Items.Add("Not Workshared")

                self.cmbNewLinkWorkset.SelectedIndex = 0
                self.cmbCurrentWorkset.SelectedIndex = 0

                self.cmbNewLinkWorkset.IsEnabled = False
                self.cmbCurrentWorkset.IsEnabled = False
                self.btnMoveWorkset.IsEnabled = False
                return

            first_index = -1
            index = 0

            for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset):
                self.cmbNewLinkWorkset.Items.Add(ws.Name)
                self.cmbCurrentWorkset.Items.Add(ws.Name)

                if ws.Name.upper() in ["LINKS", "RVT LINKS", "IFC LINKS"]:
                    if first_index == -1:
                        first_index = index

                index += 1

            if self.cmbNewLinkWorkset.Items.Count > 0:
                self.cmbNewLinkWorkset.SelectedIndex = first_index if first_index >= 0 else 0

            if self.cmbCurrentWorkset.Items.Count > 0:
                self.cmbCurrentWorkset.SelectedIndex = 0

        except Exception as ex:
            output.print_md("Workset combo failed: {}".format(ex))

    def get_selected_new_link_workset_name(self):
        try:
            if self.cmbNewLinkWorkset.SelectedItem:
                return str(self.cmbNewLinkWorkset.SelectedItem)
        except:
            pass
        return ""

    def get_selected_current_workset_name(self):
        try:
            if self.cmbCurrentWorkset.SelectedItem:
                return str(self.cmbCurrentWorkset.SelectedItem)
        except:
            pass
        return ""

    def select_current_workset_combo(self, workset_name):
        try:
            for i in range(self.cmbCurrentWorkset.Items.Count):
                if str(self.cmbCurrentWorkset.Items[i]) == workset_name:
                    self.cmbCurrentWorkset.SelectedIndex = i
                    return
        except:
            pass

    def find_workset_by_name(self, name):
        if not doc.IsWorkshared or not name:
            return None

        try:
            for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset):
                if ws.Name == name:
                    return ws
        except:
            pass

        return None

    def set_instance_workset(self, inst, workset_name=None):
        if not doc.IsWorkshared or inst is None:
            return

        if not workset_name:
            workset_name = self.get_selected_new_link_workset_name()

        ws = self.find_workset_by_name(workset_name)

        if not ws:
            return

        try:
            p = inst.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)

            if p and not p.IsReadOnly:
                p.Set(ws.Id.IntegerValue)
                output.print_md("Placed link on workset: **{}**".format(ws.Name))

        except Exception as ex:
            output.print_md("Could not set link workset: {}".format(ex))

    def move_selected_link_workset(self, sender, args):
        row = self.lvLinks.SelectedItem

        if not row:
            forms.alert("Select one link first.")
            return

        target_ws_name = self.get_selected_current_workset_name()

        if not target_ws_name or target_ws_name == "Not Workshared":
            forms.alert("Select a valid workset.")
            return

        t = Transaction(doc, "Move Link To Workset")

        try:
            t.Start()
            self.set_instance_workset(row.instance, target_ws_name)
            t.Commit()

            output.print_md("Moved link **{}** to workset **{}**".format(row.name, target_ws_name))

        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass

            output.print_md("Move workset failed: {}".format(ex))

        self.reload_ui_rows()

    def load_settings(self):
        data = load_json_settings()

        self.chkRelativePath.IsChecked = bool(data.get("relative_path", True))
        self.chkReplaceExisting.IsChecked = bool(data.get("replace_existing", False))
        self.chkRebuildIFC.IsChecked = bool(data.get("rebuild_ifc_cache", False))

        try:
            self.cmbReferenceType.SelectedIndex = int(data.get("reference_type_index", 0))
        except:
            self.cmbReferenceType.SelectedIndex = 0

        try:
            self.cmbPositioning.SelectedIndex = int(data.get("positioning_index", 0))
        except:
            self.cmbPositioning.SelectedIndex = 0

        saved_ws = data.get("new_link_workset", "")
        try:
            if saved_ws:
                for i in range(self.cmbNewLinkWorkset.Items.Count):
                    if str(self.cmbNewLinkWorkset.Items[i]) == saved_ws:
                        self.cmbNewLinkWorkset.SelectedIndex = i
                        break
        except:
            pass

    def collect_settings(self):
        return {
            "relative_path": bool(self.chkRelativePath.IsChecked),
            "replace_existing": bool(self.chkReplaceExisting.IsChecked),
            "rebuild_ifc_cache": bool(self.chkRebuildIFC.IsChecked),
            "reference_type_index": int(self.cmbReferenceType.SelectedIndex),
            "positioning_index": int(self.cmbPositioning.SelectedIndex),
            "new_link_workset": self.get_selected_new_link_workset_name()
        }

    def set_status(self, text):
        self.txtStatus.Text = text
        try:
            self.Dispatcher.Invoke(lambda: None)
        except:
            pass

    def set_progress(self, current, total):
        if total <= 0:
            self.pbProgress.Value = 0
        else:
            self.pbProgress.Value = int((float(current) / float(total)) * 100.0)

    def cancel_process(self, sender, args):
        self.cancel_requested = True
        self.set_status("Cancel requested...")

    def lv_preview_right_click(self, sender, args):
        try:
            item = args.OriginalSource
            while item is not None and not isinstance(item, ListViewItem):
                item = VisualTreeHelper.GetParent(item)

            if item is not None:
                item.IsSelected = True
                item.Focus()
        except:
            pass

    def link_selected(self, sender, args):
        try:
            row = self.lvLinks.SelectedItem
            if row:
                self.txtSelectedPath.Text = row.full_path
                self.txtSelectedSize.Text = row.source_size
                self.txtSelectedCacheSize.Text = row.cache_size
                self.txtSelectedName.Text = row.name
                self.txtSelectedWorkset.Text = row.workset_name
                self.select_current_workset_combo(row.workset_name)
            else:
                self.txtSelectedPath.Text = ""
                self.txtSelectedSize.Text = ""
                self.txtSelectedCacheSize.Text = ""
                self.txtSelectedName.Text = ""
                self.txtSelectedWorkset.Text = ""
        except:
            pass

    def get_context_rows(self):
        checked = [r for r in self.rows if r.checked]

        if checked:
            return checked

        try:
            selected = self.lvLinks.SelectedItem
            if selected:
                return [selected]
        except:
            pass

        return []

    def ctx_reload(self, sender, args):
        self.run_action("reload")

    def ctx_reload_from(self, sender, args):
        rows = self.get_context_rows()

        if not rows:
            forms.alert("Select at least one link.")
            return

        if len(rows) > 1:
            forms.alert("Reload From works with one selected link at a time.")
            return

        row = rows[0]

        dialog = OpenFileDialog()
        dialog.Title = "Reload From"
        dialog.Filter = "RVT & IFC (*.rvt;*.ifc)|*.rvt;*.ifc|RVT (*.rvt)|*.rvt|IFC (*.ifc)|*.ifc"
        dialog.Multiselect = False

        if dialog.ShowDialog() != True:
            return

        filepath = dialog.FileName
        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext == ".rvt":
                model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(filepath)

                try:
                    wc = WorksetConfiguration()
                    row.link_type.LoadFrom(model_path, wc)
                    output.print_md("Reloaded from RVT: **{}**".format(filepath))
                except Exception as ex:
                    output.print_md("Direct Reload From failed, replacing link instead: {}".format(ex))
                    if self.delete_link_type(row.link_type):
                        self.link_rvt(filepath)

            elif ext == ".ifc":
                output.print_md("Reload From IFC will replace the existing IFC link.")
                if self.delete_link_type(row.link_type):
                    self.link_ifc(filepath)

            else:
                forms.alert("Unsupported file type.")

        except Exception as ex:
            output.print_md("Reload From failed: {}".format(ex))

        self.reload_ui_rows()

    def ctx_unload_me(self, sender, args):
        self.run_action("unload_me")

    def ctx_unload_all(self, sender, args):
        self.run_action("unload_all")

    def ctx_remove(self, sender, args):
        rows = self.get_context_rows()

        if not rows:
            forms.alert("Select at least one link.")
            return

        confirm = forms.alert("Remove selected link(s) completely from the project?", yes=True, no=True)

        if not confirm:
            return

        link_data = []
        seen = []

        for r in rows:
            try:
                type_id = r.link_type.Id
                type_int = type_id.IntegerValue

                if type_int not in seen:
                    seen.append(type_int)
                    link_data.append((type_id, r.name))
            except:
                pass

        t = Transaction(doc, "Remove Links")

        try:
            t.Start()

            for type_id, name in link_data:
                try:
                    doc.Delete(type_id)
                    output.print_md("Removed completely: **{}**".format(name))
                except Exception as ex:
                    output.print_md("Could not remove **{}**: {}".format(name, ex))

            t.Commit()

        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass
            output.print_md("Remove failed: {}".format(ex))

        self.reload_ui_rows()
        self.lvLinks.Items.Refresh()

    def refresh_grid(self, rows):
        self.rows = rows
        self.lvLinks.ItemsSource = self.rows
        self.lvLinks.Items.Refresh()

    def apply_filter_and_search(self):
        rows = self.all_rows

        if self.current_filter != "ALL":
            rows = [r for r in rows if r.link_kind == self.current_filter]

        text = self.txtSearch.Text.lower()
        if text:
            rows = [
                r for r in rows
                if text in r.name.lower()
                or text in r.link_kind.lower()
                or text in r.path.lower()
                or text in r.full_path.lower()
            ]

        self.refresh_grid(rows)

    def search_changed(self, sender, args):
        self.apply_filter_and_search()

    def show_all_links(self, sender, args):
        self.current_filter = "ALL"
        self.apply_filter_and_search()

    def show_rvt_links(self, sender, args):
        self.current_filter = "RVT"
        self.apply_filter_and_search()

    def show_ifc_links(self, sender, args):
        self.current_filter = "IFC"
        self.apply_filter_and_search()

    def load_links(self, sender, args):
        save_json_settings(self.collect_settings())
        self.cancel_requested = False

        dialog = OpenFileDialog()
        dialog.Title = "Select RVT or IFC files"
        dialog.Filter = "RVT (*.rvt)|*.rvt|IFC (*.ifc)|*.ifc|RVT & IFC (*.rvt;*.ifc)|*.rvt;*.ifc"
        dialog.Multiselect = True

        if dialog.ShowDialog() != True:
            return

        files = list(dialog.FileNames)
        total = len(files)

        for idx, filepath in enumerate(files):
            if self.cancel_requested:
                output.print_md("Cancelled by user.")
                break

            self.set_progress(idx + 1, total)
            self.set_status("Processing {} of {}: {}".format(idx + 1, total, os.path.basename(filepath)))

            ext = os.path.splitext(filepath)[1].lower()

            if ext == ".rvt":
                self.link_rvt(filepath)

            elif ext == ".ifc":
                self.link_ifc(filepath)

        self.reload_ui_rows()
        self.set_progress(0, 1)
        self.set_status("Done")

    def existing_link_by_name(self, filepath):
        base = os.path.splitext(os.path.basename(filepath))[0].lower()

        for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance).WhereElementIsNotElementType():
            lt = doc.GetElement(inst.GetTypeId())
            try:
                name = Element.Name.GetValue(lt).lower()
                if base in name or name in base:
                    return lt
            except:
                pass

        return None

    def delete_link_type(self, link_type):
        type_id = link_type.Id
        t = Transaction(doc, "Delete Existing Link")

        try:
            t.Start()
            doc.Delete(type_id)
            t.Commit()
            return True
        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass
            output.print_md("Could not delete existing link: {}".format(ex))
            return False

    def duplicate_guard(self, filepath):
        existing = self.existing_link_by_name(filepath)

        if not existing:
            return False

        if self.chkReplaceExisting.IsChecked:
            output.print_md("Replacing duplicate: **{}**".format(os.path.basename(filepath)))
            return not self.delete_link_type(existing)

        output.print_md("Skipped duplicate: **{}**".format(os.path.basename(filepath)))
        return True

    def link_rvt(self, filepath):
        if self.duplicate_guard(filepath):
            return

        t = Transaction(doc, "Link RVT")

        try:
            t.Start()

            relative = bool(self.chkRelativePath.IsChecked)
            options = RevitLinkOptions(relative)
            model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(filepath)

            result = RevitLinkType.Create(doc, model_path, options)
            inst = RevitLinkInstance.Create(doc, result.ElementId)

            self.set_instance_workset(inst)

            t.Commit()

            output.print_md("RVT linked: **{}**".format(filepath))
            output.print_md("Instance Id: `{}`".format(inst.Id.IntegerValue))

        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass
            output.print_md("RVT failed: **{}** -> {}".format(filepath, ex))

    def link_ifc(self, filepath):
        if self.duplicate_guard(filepath):
            return

        try:
            load_ifc_engine()

            relative = bool(self.chkRelativePath.IsChecked)
            recreate = bool(self.chkRebuildIFC.IsChecked)

            ifc_path = filepath
            cache_rvt = filepath + ".RVT"
            options = RevitLinkOptions(relative)

            try:
                t = Transaction(doc, "Link IFC")
                t.Start()

                result = RevitLinkType.CreateFromIFC(doc, ifc_path, cache_rvt, recreate, options)

                inst = RevitLinkInstance.Create(doc, result.ElementId)
                self.set_instance_workset(inst)

                t.Commit()

                output.print_md("IFC linked with CreateFromIFC: **{}**".format(filepath))
                return

            except Exception as ex:
                try:
                    if t.HasStarted():
                        t.RollBack()
                except:
                    pass
                output.print_md("CreateFromIFC failed, trying IFC importer fallback: {}".format(ex))

            from Revit.IFC.Import import Importer

            opts = Dictionary[String, String]()
            opts["Intent"] = "Reference"
            opts["Action"] = "Link"
            opts["ForceImport"] = "false"
            opts["Process3DGeometry"] = "true"
            opts["ProcessBoundingBoxGeometry"] = "true"
            opts["AlwaysProcessBoundingBoxGeometry"] = "false"
            opts["CreateDuplicateZoneGeometry"] = "true"
            opts["CreateDuplicateContainerGeometry"] = "true"
            opts["CreateLinkInstanceOnly"] = "false"

            importer = Importer.CreateImporter(doc, filepath, opts)

            if importer is None:
                output.print_md("IFC importer could not be created: **{}**".format(filepath))
                return

            importer.ReferenceIFC(doc, filepath)

            output.print_md("IFC linked using importer fallback: **{}**".format(filepath))

        except Exception as ex:
            output.print_md("IFC failed: **{}** -> {}".format(filepath, ex))

    def run_action(self, action):
        selected = self.get_context_rows()

        if not selected:
            forms.alert("Select at least one link.")
            return

        total = len(selected)

        for idx, r in enumerate(selected):
            if self.cancel_requested:
                break

            self.set_progress(idx + 1, total)
            self.set_status("{}: {}".format(action, r.name))

            try:
                if action == "reload":
                    r.link_type.Reload()
                    output.print_md("Reloaded: **{}**".format(r.name))

                elif action == "unload_all":
                    r.link_type.Unload(None)
                    output.print_md("Unloaded for all: **{}**".format(r.name))

                elif action == "unload_me":
                    if not doc.IsWorkshared:
                        output.print_md("Skipped: **{}** - Unload For Me is only available in workshared models.".format(r.name))
                    elif hasattr(r.link_type, "UnloadLocally"):
                        r.link_type.UnloadLocally(None)
                        output.print_md("Unloaded for me: **{}**".format(r.name))
                    else:
                        output.print_md("Failed: **{}** - Unload For Me is not available.".format(r.name))

            except Exception as ex:
                output.print_md("Failed: **{}** -> {}".format(r.name, ex))

        self.reload_ui_rows()
        self.set_progress(0, 1)
        self.set_status("Done")

    def check_all(self, sender, args):
        for r in self.rows:
            r.checked = True
        self.lvLinks.Items.Refresh()

    def uncheck_all(self, sender, args):
        for r in self.rows:
            r.checked = False
        self.lvLinks.Items.Refresh()

    def reload_ui_rows(self):
        instances = FilteredElementCollector(doc) \
            .OfClass(RevitLinkInstance) \
            .WhereElementIsNotElementType() \
            .ToElements()

        self.all_rows = [LinkRow(i) for i in instances]
        self.apply_filter_and_search()


xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
win = LinkManagerWindow(xaml_path)
win.ShowDialog()