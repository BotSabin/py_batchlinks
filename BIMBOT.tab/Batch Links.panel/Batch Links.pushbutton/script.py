# -*- coding: utf-8 -*-

from pyrevit import revit, forms, script
from pyrevit.forms import WPFWindow
from Autodesk.Revit.DB import *
from Microsoft.Win32 import OpenFileDialog
from System.Collections.Generic import Dictionary
from System import String
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
        return ""

    path = path.strip()

    if os.path.isabs(path):
        return path

    try:
        host_path = doc.PathName
        if host_path:
            host_dir = os.path.dirname(host_path)
            return os.path.abspath(os.path.join(host_dir, path))
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

        self.path = self.get_path()
        self.full_path = resolve_path(self.path)
        self.size = self.get_size()

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

    def get_size(self):
        paths_to_try = []

        if self.full_path and self.full_path != "Unknown":
            paths_to_try.append(self.full_path)

            if self.full_path.lower().endswith(".ifc"):
                paths_to_try.append(self.full_path + ".RVT")
                paths_to_try.append(self.full_path + ".rvt")

        for p in paths_to_try:
            try:
                if p and os.path.exists(p):
                    return self.format_size(os.path.getsize(p))
            except:
                pass

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

        self.load_settings()
        self.reload_ui_rows()

        if not doc.IsWorkshared:
            try:
                self.btnUnloadForMe.IsEnabled = False
                self.btnUnloadForMe.ToolTip = "Unload For Me is only available in workshared models."
            except:
                pass

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

    def collect_settings(self):
        return {
            "relative_path": bool(self.chkRelativePath.IsChecked),
            "replace_existing": bool(self.chkReplaceExisting.IsChecked),
            "rebuild_ifc_cache": bool(self.chkRebuildIFC.IsChecked),
            "reference_type_index": int(self.cmbReferenceType.SelectedIndex),
            "positioning_index": int(self.cmbPositioning.SelectedIndex)
        }

    def apply_settings(self, sender, args):
        if save_json_settings(self.collect_settings()):
            self.set_status("Settings saved.")
            forms.alert("Settings saved.")

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

    def link_selected(self, sender, args):
        try:
            row = self.lvLinks.SelectedItem
            if row:
                self.txtSelectedPath.Text = row.full_path
                self.txtSelectedSize.Text = row.size
                self.txtSelectedName.Text = row.name
            else:
                self.txtSelectedPath.Text = ""
                self.txtSelectedSize.Text = ""
                self.txtSelectedName.Text = ""
        except:
            pass

    def copy_selected_path(self, sender, args):
        try:
            row = self.lvLinks.SelectedItem
            if row:
                System.Windows.Clipboard.SetText(row.full_path)
                self.set_status("Path copied.")
        except Exception as ex:
            forms.alert("Could not copy path: {}".format(ex))

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

    def show_cad_links(self, sender, args):
        forms.alert("CAD Links support coming in v3.2.")

    def show_pointcloud_links(self, sender, args):
        forms.alert("Point Cloud support coming in v3.2.")

    def show_nwc_links(self, sender, args):
        forms.alert("NWC/NWD support coming in v3.2.")

    def load_links(self, sender, args):
        self.cancel_requested = False

        dialog = OpenFileDialog()
        dialog.Title = "Select RVT or IFC files"
        dialog.Filter = "RVT & IFC (*.rvt;*.ifc)|*.rvt;*.ifc|RVT (*.rvt)|*.rvt|IFC (*.ifc)|*.ifc"
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
        t = Transaction(doc, "Delete Existing Link")

        try:
            t.Start()
            doc.Delete(link_type.Id)
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

            if self.chkRebuildIFC.IsChecked:
                folder = os.path.dirname(filepath)
                name = os.path.splitext(os.path.basename(filepath))[0]
                cache_rvt = os.path.join(folder, name + ".ifc.RVT")

                if os.path.exists(cache_rvt):
                    try:
                        os.remove(cache_rvt)
                        output.print_md("Deleted IFC cache: **{}**".format(cache_rvt))
                    except Exception as ex:
                        output.print_md("Could not delete IFC cache: **{}** -> {}".format(cache_rvt, ex))

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

            output.print_md("IFC linked using Revit IFC engine: **{}**".format(filepath))

        except Exception as ex:
            output.print_md("IFC failed: **{}** -> {}".format(filepath, ex))

    def reload_selected(self, sender, args):
        self.run_action("reload")

    def unload_for_me(self, sender, args):
        self.run_action("unload_me")

    def unload_for_all(self, sender, args):
        self.run_action("unload_all")

    def run_action(self, action):
        selected = [r for r in self.rows if r.checked]

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