# -*- coding: utf-8 -*-
"""
DWG To Revit Title Block

Creates a Revit Title Block family from DWG linework.

The tool:
1. Selects a DWG file.
2. Selects a Revit Title Block family template (.rft).
3. Creates a new family document.
4. Imports the DWG.
5. Converts supported DWG geometry to native Revit Detail Curves.
6. Creates Revit subcategories based on DWG layers.
7. Deletes the imported DWG.
8. Saves the result as an RFA family.

Supported geometry:
- Lines
- Arcs
- Polylines
- Ellipses and compatible Revit curves
- Some solid edges

Not converted automatically:
- DWG text
- AutoCAD attributes
- Revit labels
- Raster images
- Complex hatches
- Proxy objects

Compatible with:
- pyRevit
- Revit 2022–2026
- IronPython
"""

__title__ = "DWG To\nTitle Block"
__author__ = "Sabin / BIMBOT"
__doc__ = "Converts DWG linework into a native Revit Title Block family."

import clr
import os
import re
import traceback

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    Arc,
    Curve,
    DWGImportOptions,
    ElementId,
    FilteredElementCollector,
    GeometryInstance,
    GraphicsStyle,
    GraphicsStyleType,
    ImportPlacement,
    Line,
    Options,
    PolyLine,
    SaveAsOptions,
    Solid,
    Transaction,
    TransactionStatus,
    Transform,
    View,
    ViewPlan,
    ViewSheet
)

from Autodesk.Revit.UI import TaskDialog

from pyrevit import forms
from pyrevit import script


# ----------------------------------------------------------------------
# REVIT CONTEXT
# ----------------------------------------------------------------------

uiapp = __revit__
uidoc = uiapp.ActiveUIDocument
project_doc = uidoc.Document if uidoc else None
app = uiapp.Application

output = script.get_output()


# ----------------------------------------------------------------------
# SETTINGS
# ----------------------------------------------------------------------

DELETE_IMPORTED_DWG = True
CREATE_LAYER_SUBCATEGORIES = True

# Revit internal units are feet.
POINT_TOLERANCE = 0.0001
MINIMUM_CURVE_LENGTH = 0.0005

# Protection against extremely dense AutoCAD polylines.
MAX_POLYLINE_SEGMENTS = 50000


# ----------------------------------------------------------------------
# MESSAGE UTILITIES
# ----------------------------------------------------------------------

def show_message(title, message):
    """Display a Revit TaskDialog."""
    TaskDialog.Show(title, message)


def safe_string(value):
    """Safely convert an object to text."""
    if value is None:
        return ""

    try:
        return str(value)
    except Exception:
        return ""


def print_error_report(error_message):
    """Write the complete error report to the pyRevit output window."""
    error_details = traceback.format_exc()

    output.print_md("## DWG To Title Block – Error")
    output.print_md("")
    output.print_md("**Message:**")
    output.print_md("")
    output.print_md("```text")
    output.print_md(safe_string(error_message))
    output.print_md("```")
    output.print_md("")
    output.print_md("**Traceback:**")
    output.print_md("")
    output.print_md("```text")
    output.print_md(error_details)
    output.print_md("```")


# ----------------------------------------------------------------------
# NAME UTILITIES
# ----------------------------------------------------------------------

def clean_name(value, fallback="DWG Layer"):
    """
    Create a valid and readable Revit name.

    Removes characters that can cause issues in Revit category names
    and file names.
    """
    text = safe_string(value).strip()

    if not text:
        text = fallback

    text = re.sub(r"[\{\}\[\]\|;<>?`~]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > 120:
        text = text[:120]

    if not text:
        text = fallback

    return text


def element_id_value(element_id):
    """
    Return the numerical value of an ElementId.

    Supports both older and newer Revit API versions.
    """
    if element_id is None:
        return -1

    try:
        return element_id.IntegerValue
    except Exception:
        try:
            return element_id.Value
        except Exception:
            return -1


# ----------------------------------------------------------------------
# GEOMETRY UTILITIES
# ----------------------------------------------------------------------

def point_key(point):
    """
    Generate a rounded coordinate key.

    Used for duplicate curve detection.
    """
    if point is None:
        return None

    return (
        int(round(point.X / POINT_TOLERANCE)),
        int(round(point.Y / POINT_TOLERANCE)),
        int(round(point.Z / POINT_TOLERANCE))
    )


def normalize_endpoint_order(start_key, end_key):
    """Normalize endpoint order for duplicate detection."""
    if start_key is None or end_key is None:
        return start_key, end_key

    if start_key > end_key:
        return end_key, start_key

    return start_key, end_key


def curve_key(curve):
    """
    Create a unique key for a curve.

    Reversed lines are treated as duplicate geometry.
    """
    if curve is None:
        return None

    try:
        start_point = curve.GetEndPoint(0)
        end_point = curve.GetEndPoint(1)

        start_key = point_key(start_point)
        end_key = point_key(end_point)

        start_key, end_key = normalize_endpoint_order(
            start_key,
            end_key
        )

        curve_type_name = curve.GetType().Name

        if isinstance(curve, Arc):
            try:
                center_key = point_key(curve.Center)
                radius_key = int(
                    round(curve.Radius / POINT_TOLERANCE)
                )

                return (
                    curve_type_name,
                    start_key,
                    end_key,
                    center_key,
                    radius_key
                )
            except Exception:
                pass

        return (
            curve_type_name,
            start_key,
            end_key
        )

    except Exception:
        return None


def is_valid_curve(curve):
    """Check whether a curve can reasonably be created in Revit."""
    if curve is None:
        return False

    try:
        if not curve.IsBound:
            return False
    except Exception:
        pass

    try:
        curve_length = curve.Length
    except Exception:
        return False

    if curve_length < MINIMUM_CURVE_LENGTH:
        return False

    return True


def transform_curve(curve, transformation):
    """Apply a Revit Transform to a curve."""
    if curve is None:
        return None

    if transformation is None:
        transformation = Transform.Identity

    try:
        return curve.CreateTransformed(transformation)
    except Exception:
        return curve


# ----------------------------------------------------------------------
# FAMILY VIEW
# ----------------------------------------------------------------------

def is_usable_family_view(view):
    """
    Check whether the view can be used for DWG import and Detail Curves.
    """
    if view is None:
        return False

    try:
        if view.IsTemplate:
            return False
    except Exception:
        pass

    try:
        if isinstance(view, ViewSheet):
            return False
    except Exception:
        pass

    try:
        if not view.CanBePrinted:
            # Some family editor views may still work, so this is not
            # treated as an absolute rejection.
            pass
    except Exception:
        pass

    return True


def get_family_creation_view(family_doc):
    """
    Find a suitable 2D view inside the new Title Block family.

    Priority:
    1. Active family view
    2. Non-template ViewPlan
    3. Any non-template and non-sheet view
    """
    if family_doc is None:
        return None

    try:
        active_view = family_doc.ActiveView

        if is_usable_family_view(active_view):
            return active_view
    except Exception:
        pass

    try:
        plan_views = FilteredElementCollector(
            family_doc
        ).OfClass(ViewPlan)

        for view in plan_views:
            if is_usable_family_view(view):
                return view
    except Exception:
        pass

    try:
        all_views = FilteredElementCollector(
            family_doc
        ).OfClass(View)

        for view in all_views:
            if is_usable_family_view(view):
                return view
    except Exception:
        pass

    return None


# ----------------------------------------------------------------------
# DWG LAYER HANDLING
# ----------------------------------------------------------------------

def get_graphics_style_name(doc, geometry_object):
    """
    Retrieve the DWG layer name using the GeometryObject GraphicsStyleId.
    """
    if doc is None or geometry_object is None:
        return None

    try:
        graphics_style_id = geometry_object.GraphicsStyleId

        if graphics_style_id is None:
            return None

        if element_id_value(graphics_style_id) < 0:
            return None

        graphics_style = doc.GetElement(graphics_style_id)

        if not isinstance(graphics_style, GraphicsStyle):
            return None

        graphics_category = graphics_style.GraphicsStyleCategory

        if graphics_category is None:
            return None

        return graphics_category.Name

    except Exception:
        return None


def find_existing_subcategory(parent_category, category_name):
    """Find an existing family subcategory by name."""
    if parent_category is None:
        return None

    target_name = safe_string(category_name).strip().lower()

    if not target_name:
        return None

    try:
        subcategories = parent_category.SubCategories

        for subcategory in subcategories:
            try:
                if subcategory.Name.strip().lower() == target_name:
                    return subcategory
            except Exception:
                continue
    except Exception:
        pass

    return None


def get_or_create_subcategory(
        family_doc,
        family_category,
        layer_name,
        subcategory_cache
):
    """
    Create one Revit subcategory for each DWG layer.
    """
    if not CREATE_LAYER_SUBCATEGORIES:
        return None

    if family_doc is None or family_category is None:
        return None

    safe_layer_name = clean_name(
        layer_name,
        "DWG Layer"
    )

    cache_key = safe_layer_name.lower()

    if cache_key in subcategory_cache:
        return subcategory_cache[cache_key]

    existing_subcategory = find_existing_subcategory(
        family_category,
        safe_layer_name
    )

    if existing_subcategory is not None:
        subcategory_cache[cache_key] = existing_subcategory
        return existing_subcategory

    try:
        categories = family_doc.Settings.Categories

        new_subcategory = categories.NewSubcategory(
            family_category,
            safe_layer_name
        )

        subcategory_cache[cache_key] = new_subcategory
        return new_subcategory

    except Exception:
        return None


def get_projection_graphics_style(subcategory):
    """Return the projection GraphicsStyle of a subcategory."""
    if subcategory is None:
        return None

    try:
        return subcategory.GetGraphicsStyle(
            GraphicsStyleType.Projection
        )
    except Exception:
        return None


def assign_curve_style(detail_curve, graphics_style):
    """Assign a Revit line style to a Detail Curve."""
    if detail_curve is None or graphics_style is None:
        return

    try:
        detail_curve.LineStyle = graphics_style
    except Exception:
        pass


# ----------------------------------------------------------------------
# NATIVE CURVE CREATION
# ----------------------------------------------------------------------

def create_native_detail_curve(
        family_doc,
        family_view,
        source_curve,
        transformation,
        layer_name,
        family_category,
        subcategory_cache,
        created_curve_keys,
        statistics
):
    """
    Convert one source curve into a native Revit Detail Curve.
    """
    native_curve = transform_curve(
        source_curve,
        transformation
    )

    if not is_valid_curve(native_curve):
        statistics["skipped"] += 1
        return None

    geometry_key = curve_key(native_curve)

    if (
        geometry_key is not None
        and geometry_key in created_curve_keys
    ):
        statistics["duplicates"] += 1
        return None

    try:
        detail_curve = family_doc.FamilyCreate.NewDetailCurve(
            family_view,
            native_curve
        )

        if detail_curve is None:
            statistics["failed"] += 1
            return None

        if geometry_key is not None:
            created_curve_keys.add(geometry_key)

        subcategory = get_or_create_subcategory(
            family_doc,
            family_category,
            layer_name,
            subcategory_cache
        )

        graphics_style = get_projection_graphics_style(
            subcategory
        )

        assign_curve_style(
            detail_curve,
            graphics_style
        )

        statistics["created"] += 1

        return detail_curve

    except Exception:
        statistics["failed"] += 1
        return None


def create_polyline_segments(
        family_doc,
        family_view,
        polyline,
        transformation,
        layer_name,
        family_category,
        subcategory_cache,
        created_curve_keys,
        statistics
):
    """
    Convert a DWG PolyLine into individual Revit Detail Lines.
    """
    try:
        points = list(polyline.GetCoordinates())
    except Exception:
        statistics["failed"] += 1
        return

    if len(points) < 2:
        statistics["skipped"] += 1
        return

    segment_count = len(points) - 1

    if segment_count > MAX_POLYLINE_SEGMENTS:
        statistics["polyline_limit"] += 1
        return

    if transformation is None:
        transformation = Transform.Identity

    for index in range(segment_count):
        try:
            source_start = points[index]
            source_end = points[index + 1]

            start_point = transformation.OfPoint(source_start)
            end_point = transformation.OfPoint(source_end)

            if (
                start_point is None
                or end_point is None
            ):
                statistics["skipped"] += 1
                continue

            if (
                start_point.DistanceTo(end_point)
                < MINIMUM_CURVE_LENGTH
            ):
                statistics["skipped"] += 1
                continue

            line = Line.CreateBound(
                start_point,
                end_point
            )

            create_native_detail_curve(
                family_doc,
                family_view,
                line,
                Transform.Identity,
                layer_name,
                family_category,
                subcategory_cache,
                created_curve_keys,
                statistics
            )

        except Exception:
            statistics["failed"] += 1


def process_solid_edges(
        family_doc,
        family_view,
        solid,
        transformation,
        layer_name,
        family_category,
        subcategory_cache,
        created_curve_keys,
        statistics
):
    """
    Convert compatible edges from imported solids into Detail Curves.

    Some AutoCAD objects can appear as Solid geometry in the Revit API.
    """
    if solid is None:
        return

    try:
        edges = solid.Edges
    except Exception:
        return

    for edge in edges:
        try:
            edge_curve = edge.AsCurve()

            create_native_detail_curve(
                family_doc,
                family_view,
                edge_curve,
                transformation,
                layer_name,
                family_category,
                subcategory_cache,
                created_curve_keys,
                statistics
            )

        except Exception:
            statistics["failed"] += 1


# ----------------------------------------------------------------------
# GEOMETRY RECURSION
# ----------------------------------------------------------------------

def process_geometry_object(
        family_doc,
        family_view,
        geometry_object,
        current_transform,
        inherited_layer_name,
        family_category,
        subcategory_cache,
        created_curve_keys,
        statistics
):
    """
    Recursively process Revit geometry extracted from the imported DWG.
    """
    if geometry_object is None:
        return

    local_layer_name = get_graphics_style_name(
        family_doc,
        geometry_object
    )

    layer_name = (
        local_layer_name
        or inherited_layer_name
        or "DWG Layer"
    )

    if current_transform is None:
        current_transform = Transform.Identity

    # Nested DWG blocks are exposed as GeometryInstance objects.
    if isinstance(geometry_object, GeometryInstance):
        try:
            instance_transform = geometry_object.Transform

            combined_transform = current_transform.Multiply(
                instance_transform
            )

            symbol_geometry = geometry_object.GetSymbolGeometry()

            for nested_object in symbol_geometry:
                process_geometry_object(
                    family_doc,
                    family_view,
                    nested_object,
                    combined_transform,
                    layer_name,
                    family_category,
                    subcategory_cache,
                    created_curve_keys,
                    statistics
                )

        except Exception:
            statistics["failed"] += 1

        return

    if isinstance(geometry_object, Curve):
        create_native_detail_curve(
            family_doc,
            family_view,
            geometry_object,
            current_transform,
            layer_name,
            family_category,
            subcategory_cache,
            created_curve_keys,
            statistics
        )
        return

    if isinstance(geometry_object, PolyLine):
        create_polyline_segments(
            family_doc,
            family_view,
            geometry_object,
            current_transform,
            layer_name,
            family_category,
            subcategory_cache,
            created_curve_keys,
            statistics
        )
        return

    if isinstance(geometry_object, Solid):
        process_solid_edges(
            family_doc,
            family_view,
            geometry_object,
            current_transform,
            layer_name,
            family_category,
            subcategory_cache,
            created_curve_keys,
            statistics
        )
        return

    statistics["unsupported"] += 1


def convert_import_instance(
        family_doc,
        family_view,
        import_instance,
        family_category
):
    """
    Extract all compatible geometry from the imported DWG and create
    native Revit Detail Curves.
    """
    statistics = {
        "created": 0,
        "duplicates": 0,
        "skipped": 0,
        "failed": 0,
        "unsupported": 0,
        "polyline_limit": 0
    }

    geometry_options = Options()
    geometry_options.ComputeReferences = False
    geometry_options.IncludeNonVisibleObjects = True

    try:
        geometry_options.View = family_view
    except Exception:
        pass

    geometry = import_instance.get_Geometry(
        geometry_options
    )

    if geometry is None:
        return statistics

    subcategory_cache = {}
    created_curve_keys = set()

    for geometry_object in geometry:
        process_geometry_object(
            family_doc,
            family_view,
            geometry_object,
            Transform.Identity,
            "DWG Layer",
            family_category,
            subcategory_cache,
            created_curve_keys,
            statistics
        )

    return statistics


# ----------------------------------------------------------------------
# DWG IMPORT
# ----------------------------------------------------------------------

def import_dwg(
        family_doc,
        family_view,
        dwg_path
):
    """
    Import the DWG into the selected family view.

    Returns the imported Revit element or None.
    """
    import_options = DWGImportOptions()

    import_options.Placement = ImportPlacement.Origin
    import_options.ThisViewOnly = True
    import_options.VisibleLayersOnly = False
    import_options.AutoCorrectAlmostVHLines = True
    import_options.OrientToView = True

    imported_id_reference = clr.Reference[ElementId]()

    import_result = family_doc.Import(
        dwg_path,
        import_options,
        family_view,
        imported_id_reference
    )

    if not import_result:
        return None

    imported_element_id = imported_id_reference.Value

    if imported_element_id is None:
        return None

    if element_id_value(imported_element_id) < 0:
        return None

    return family_doc.GetElement(
        imported_element_id
    )


# ----------------------------------------------------------------------
# FILE SELECTION
# ----------------------------------------------------------------------

def select_input_files():
    """Ask the user for DWG, RFT template and output RFA paths."""

    dwg_path = forms.pick_file(
        file_ext="dwg",
        title="Select the DWG title block"
    )

    if not dwg_path:
        return None, None, None

    template_path = forms.pick_file(
        file_ext="rft",
        title="Select a Revit Title Block family template"
    )

    if not template_path:
        return None, None, None

    suggested_name = os.path.splitext(
        os.path.basename(dwg_path)
    )[0]

    suggested_name = clean_name(
        suggested_name,
        "Converted Title Block"
    )

    output_path = forms.save_file(
        file_ext="rfa",
        default_name=suggested_name + ".rfa",
        title="Save the converted Revit Title Block family"
    )

    if not output_path:
        return None, None, None

    if not output_path.lower().endswith(".rfa"):
        output_path += ".rfa"

    return (
        dwg_path,
        template_path,
        output_path
    )


# ----------------------------------------------------------------------
# SAVE FAMILY
# ----------------------------------------------------------------------

def save_family_document(
        family_doc,
        output_path
):
    """Save the generated family with compact file settings."""
    save_options = SaveAsOptions()
    save_options.OverwriteExistingFile = True
    save_options.Compact = True
    save_options.MaximumBackups = 1

    family_doc.SaveAs(
        output_path,
        save_options
    )


# ----------------------------------------------------------------------
# RESULT REPORT
# ----------------------------------------------------------------------

def build_success_report(
        statistics,
        output_path
):
    """Create the final result message."""
    return (
        "The Title Block family was created successfully.\n\n"
        "Native Detail Curves created: {0}\n"
        "Duplicate curves ignored: {1}\n"
        "Short or invalid curves ignored: {2}\n"
        "Unsupported geometry objects: {3}\n"
        "Failed geometry objects: {4}\n"
        "Oversized polylines ignored: {5}\n\n"
        "Saved file:\n{6}\n\n"
        "Important limitations:\n"
        "• DWG text is not converted into Revit text or labels.\n"
        "• AutoCAD attributes are not converted into parameters.\n"
        "• Hatches and raster images are not converted automatically.\n\n"
        "Open the generated family and add the required Revit Labels, "
        "such as Sheet Number, Sheet Name, Project Name, Drawn By, "
        "Checked By, Date and Revision."
    ).format(
        statistics["created"],
        statistics["duplicates"],
        statistics["skipped"],
        statistics["unsupported"],
        statistics["failed"],
        statistics["polyline_limit"],
        output_path
    )


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    """Main tool workflow."""

    dwg_path = None
    template_path = None
    output_path = None

    family_doc = None
    transaction = None
    family_saved = False

    try:
        dwg_path, template_path, output_path = select_input_files()

        if not dwg_path:
            return

        if not os.path.isfile(dwg_path):
            show_message(
                "DWG To Title Block",
                "The selected DWG file does not exist."
            )
            return

        if not os.path.isfile(template_path):
            show_message(
                "DWG To Title Block",
                "The selected Revit family template does not exist."
            )
            return

        if os.path.exists(output_path):
            overwrite_result = forms.alert(
                "The selected RFA file already exists.\n\n"
                "Do you want to overwrite it?",
                title="DWG To Title Block",
                yes=True,
                no=True
            )

            if not overwrite_result:
                return

        # Create a new family using the selected Title Block template.
        family_doc = app.NewFamilyDocument(
            template_path
        )

        if family_doc is None:
            raise Exception(
                "Revit could not create a family using the selected "
                "RFT template."
            )

        if not family_doc.IsFamilyDocument:
            raise Exception(
                "The selected template did not create a valid "
                "Revit family document."
            )

        family_view = get_family_creation_view(
            family_doc
        )

        if family_view is None:
            raise Exception(
                "No suitable family view was found.\n\n"
                "Please select a valid Revit Title Block family template."
            )

        try:
            family_category = (
                family_doc.OwnerFamily.FamilyCategory
            )
        except Exception:
            family_category = None

        if family_category is None:
            raise Exception(
                "The selected family template does not contain a valid "
                "Title Block family category."
            )

        transaction = Transaction(
            family_doc,
            "Convert DWG to native Title Block"
        )

        transaction.Start()

        import_instance = import_dwg(
            family_doc,
            family_view,
            dwg_path
        )

        if import_instance is None:
            raise Exception(
                "The DWG could not be imported into the Title Block "
                "family.\n\n"
                "Check that:\n"
                "• The DWG is valid and not corrupted.\n"
                "• The DWG is not open exclusively in AutoCAD.\n"
                "• The selected RFT is a valid Title Block template.\n"
                "• The DWG units and geometry are valid."
            )

        statistics = convert_import_instance(
            family_doc,
            family_view,
            import_instance,
            family_category
        )

        if DELETE_IMPORTED_DWG:
            try:
                family_doc.Delete(
                    import_instance.Id
                )
            except Exception:
                pass

        transaction.Commit()
        transaction = None

        if statistics["created"] <= 0:
            raise Exception(
                "No compatible native linework was created.\n\n"
                "The DWG may contain only:\n"
                "• Text\n"
                "• AutoCAD attributes\n"
                "• Raster images\n"
                "• Complex hatches\n"
                "• Proxy objects\n"
                "• Unsupported geometry\n\n"
                "Convert the DWG objects to basic Lines, Polylines and "
                "Arcs in AutoCAD, then try again."
            )

        save_family_document(
            family_doc,
            output_path
        )

        family_saved = True

        success_report = build_success_report(
            statistics,
            output_path
        )

        show_message(
            "DWG To Title Block",
            success_report
        )

        # Close the temporary document before reopening the saved family.
        try:
            family_doc.Close(False)
            family_doc = None
        except Exception:
            pass

        # Open and activate the newly created RFA.
        try:
            uiapp.OpenAndActivateDocument(
                output_path
            )
        except Exception:
            pass

    except Exception as error:
        # Roll back a transaction that is still open.
        if transaction is not None:
            try:
                if (
                    transaction.GetStatus()
                    == TransactionStatus.Started
                ):
                    transaction.RollBack()
            except Exception:
                pass

        print_error_report(error)

        show_message(
            "DWG To Title Block – Error",
            "{0}\n\n"
            "The complete error report was written to the "
            "pyRevit output window.".format(
                safe_string(error)
            )
        )

    finally:
        if family_doc is not None:
            try:
                family_doc.Close(False)
            except Exception:
                pass


if __name__ == "__main__":
    main()