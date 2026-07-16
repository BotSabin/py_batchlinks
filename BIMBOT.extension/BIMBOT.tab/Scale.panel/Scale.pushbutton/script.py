# -*- coding: utf-8 -*-
"""
Scale Complete Key Plan Family

Best-effort uniform scaling of native 2D Revit family content.

Scales:
- Symbolic Lines
- Detail Lines
- Arcs, circles, ellipses and splines
- Filled Regions
- Masking Regions
- Text Notes: position and text size
- Nested family content recursively
- Nested family instance positions

Important:
- Filled Regions are recreated automatically with the same type.
- Nested family definitions are edited and reloaded automatically.
- Labels, dimensions, imported CAD, raster images and some constrained
  elements cannot be geometrically scaled through the Revit API.

Run inside the open Key Plan RFA.
"""

__title__ = "Scale Complete\nKey Plan"
__author__ = "Sabin / BIMBOT"

import clr
import traceback

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    BuiltInParameter,
    CurveElement,
    CurveLoop,
    ElementId,
    ElementTransformUtils,
    Family,
    FamilyInstance,
    FilledRegion,
    FilteredElementCollector,
    IFamilyLoadOptions,
    LocationPoint,
    TextNote,
    TextNoteType,
    Transaction,
    TransactionStatus,
    Transform,
    View,
    XYZ
)

from System.Collections.Generic import List
from pyrevit import forms, script


# ============================================================
# REVIT CONTEXT
# ============================================================

uiapp = __revit__
uidoc = uiapp.ActiveUIDocument
root_doc = uidoc.Document
root_view = root_doc.ActiveView
output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

MIN_FACTOR = 0.01
MAX_FACTOR = 100.0
FACTOR_TOLERANCE = 0.000001

MAX_NESTED_DEPTH = 10

SCALE_CURVES = True
SCALE_REGIONS = True
SCALE_TEXT = True
SCALE_NESTED_FAMILIES = True

# For nested families, geometry is scaled around family origin.
NESTED_BASE_POINT = XYZ.Zero


# ============================================================
# GENERAL UTILITIES
# ============================================================

def alert(message, title="Scale Complete Key Plan"):
    forms.alert(
        message,
        title=title,
        warn_icon=False
    )


def safe_string(value):
    try:
        return "" if value is None else str(value)
    except Exception:
        return ""


def eid_value(element_id):
    if element_id is None:
        return -1

    try:
        return element_id.IntegerValue
    except Exception:
        try:
            return element_id.Value
        except Exception:
            return -1


def parse_factor(value):
    text = safe_string(value).strip().replace(",", ".")

    if not text:
        return None

    if text.endswith("%"):
        factor = float(text[:-1]) / 100.0
    else:
        factor = float(text)

    if factor < MIN_FACTOR or factor > MAX_FACTOR:
        raise Exception(
            "Scale factor must be between {0} and {1}.".format(
                MIN_FACTOR,
                MAX_FACTOR
            )
        )

    return factor


def validate_root_document():
    if root_doc is None:
        raise Exception("No active Revit document was found.")

    if not root_doc.IsFamilyDocument:
        raise Exception(
            "Open the Key Plan RFA in Family Editor and run the tool again."
        )

    if root_view is None:
        raise Exception("No active family view was found.")


def get_usable_view(doc):
    try:
        active_view = doc.ActiveView

        if active_view is not None and not active_view.IsTemplate:
            return active_view
    except Exception:
        pass

    for view in FilteredElementCollector(doc).OfClass(View):
        try:
            if not view.IsTemplate:
                return view
        except Exception:
            continue

    return None


def create_scale_transform(factor, base_point):
    transform = Transform.Identity

    transform.BasisX = XYZ(factor, 0.0, 0.0)
    transform.BasisY = XYZ(0.0, factor, 0.0)
    transform.BasisZ = XYZ(0.0, 0.0, factor)

    transform.Origin = XYZ(
        base_point.X * (1.0 - factor),
        base_point.Y * (1.0 - factor),
        base_point.Z * (1.0 - factor)
    )

    return transform


def scale_point(point, factor, base_point):
    return XYZ(
        base_point.X + factor * (point.X - base_point.X),
        base_point.Y + factor * (point.Y - base_point.Y),
        base_point.Z + factor * (point.Z - base_point.Z)
    )


# ============================================================
# FAMILY LOAD OPTIONS
# ============================================================

class FamilyLoadOptions(IFamilyLoadOptions):

    def OnFamilyFound(
        self,
        family_in_use,
        overwrite_parameter_values
    ):
        overwrite_parameter_values.Value = True
        return True

    def OnSharedFamilyFound(
        self,
        shared_family,
        family_in_use,
        source,
        overwrite_parameter_values
    ):
        overwrite_parameter_values.Value = True
        return True


LOAD_OPTIONS = FamilyLoadOptions()


# ============================================================
# ELEMENT COLLECTION
# ============================================================

def get_curve_elements(doc):
    if not SCALE_CURVES:
        return []

    return list(
        FilteredElementCollector(doc)
        .OfClass(CurveElement)
        .WhereElementIsNotElementType()
    )


def get_regions(doc):
    if not SCALE_REGIONS:
        return []

    return list(
        FilteredElementCollector(doc)
        .OfClass(FilledRegion)
        .WhereElementIsNotElementType()
    )


def get_text_notes(doc):
    if not SCALE_TEXT:
        return []

    return list(
        FilteredElementCollector(doc)
        .OfClass(TextNote)
        .WhereElementIsNotElementType()
    )


def get_nested_instances(doc):
    if not SCALE_NESTED_FAMILIES:
        return []

    return list(
        FilteredElementCollector(doc)
        .OfClass(FamilyInstance)
        .WhereElementIsNotElementType()
    )


# ============================================================
# BOUNDS
# ============================================================

def get_curve_points(curve):
    if curve is None:
        return []

    try:
        return list(curve.Tessellate())
    except Exception:
        pass

    points = []

    try:
        points.append(curve.GetEndPoint(0))
        points.append(curve.GetEndPoint(1))
    except Exception:
        pass

    return points


def get_element_points(element, view):
    points = []

    if isinstance(element, CurveElement):
        try:
            return get_curve_points(element.GeometryCurve)
        except Exception:
            return []

    if isinstance(element, FilledRegion):
        try:
            for curve_loop in element.GetBoundaries():
                for curve in curve_loop:
                    points.extend(get_curve_points(curve))
        except Exception:
            pass

        return points

    if isinstance(element, TextNote):
        try:
            points.append(element.Coord)
        except Exception:
            pass

    try:
        bbox = element.get_BoundingBox(view)

        if bbox is not None:
            points.append(bbox.Min)
            points.append(bbox.Max)
    except Exception:
        pass

    return points


def calculate_bounds(doc, view):
    elements = []

    elements.extend(get_curve_elements(doc))
    elements.extend(get_regions(doc))
    elements.extend(get_text_notes(doc))
    elements.extend(get_nested_instances(doc))

    min_x = None
    min_y = None
    min_z = None
    max_x = None
    max_y = None
    max_z = None

    for element in elements:
        for point in get_element_points(element, view):
            if point is None:
                continue

            if min_x is None:
                min_x = max_x = point.X
                min_y = max_y = point.Y
                min_z = max_z = point.Z
            else:
                min_x = min(min_x, point.X)
                min_y = min(min_y, point.Y)
                min_z = min(min_z, point.Z)

                max_x = max(max_x, point.X)
                max_y = max(max_y, point.Y)
                max_z = max(max_z, point.Z)

    if min_x is None:
        return None

    return {
        "min": XYZ(min_x, min_y, min_z),
        "max": XYZ(max_x, max_y, max_z),
        "center": XYZ(
            (min_x + max_x) / 2.0,
            (min_y + max_y) / 2.0,
            (min_z + max_z) / 2.0
        )
    }


def choose_root_base_point():
    bounds = calculate_bounds(root_doc, root_view)

    if bounds is None:
        raise Exception(
            "No supported geometry was found in the family."
        )

    options = [
        "Geometry center",
        "Lower-left corner",
        "Family origin (0, 0)"
    ]

    choice = forms.SelectFromList.show(
        options,
        title="Choose scale base point",
        button_name="Continue",
        multiselect=False
    )

    if not choice:
        return None, None

    if choice == "Geometry center":
        return bounds["center"], choice

    if choice == "Lower-left corner":
        return XYZ(
            bounds["min"].X,
            bounds["min"].Y,
            bounds["center"].Z
        ), choice

    return XYZ(
        0.0,
        0.0,
        bounds["center"].Z
    ), choice


# ============================================================
# CURVES
# ============================================================

def scale_curve_element(
    curve_element,
    scale_transform
):
    try:
        original_curve = curve_element.GeometryCurve

        if original_curve is None:
            return False, "No GeometryCurve"

        scaled_curve = original_curve.CreateTransformed(
            scale_transform
        )

        curve_element.SetGeometryCurve(
            scaled_curve,
            True
        )

        return True, None

    except Exception as error:
        try:
            curve_element.GeometryCurve = scaled_curve
            return True, None
        except Exception:
            return False, safe_string(error)


# ============================================================
# FILLED AND MASKING REGIONS
# ============================================================

def transform_curve_loop(
    original_loop,
    scale_transform
):
    new_loop = CurveLoop()

    for curve in original_loop:
        new_loop.Append(
            curve.CreateTransformed(scale_transform)
        )

    return new_loop


def transform_region_boundaries(
    region,
    scale_transform
):
    loops = List[CurveLoop]()

    for original_loop in region.GetBoundaries():
        loops.Add(
            transform_curve_loop(
                original_loop,
                scale_transform
            )
        )

    return loops


def copy_string_parameters(source, target):
    source_parameters = source.Parameters

    for source_parameter in source_parameters:
        try:
            if source_parameter.IsReadOnly:
                continue

            target_parameter = target.get_Parameter(
                source_parameter.Definition
            )

            if (
                target_parameter is None
                or target_parameter.IsReadOnly
            ):
                continue

            storage_name = safe_string(
                source_parameter.StorageType
            )

            if storage_name == "String":
                target_parameter.Set(
                    source_parameter.AsString() or ""
                )
        except Exception:
            continue


def recreate_region(
    doc,
    view,
    region,
    scale_transform
):
    """
    Recreates the region with its exact original FilledRegionType.

    The type itself contains the masking/fill settings, so the new
    region retains the original appearance.
    """

    try:
        type_id = region.GetTypeId()

        if type_id is None or eid_value(type_id) < 0:
            return None, False, "Invalid region type"

        boundaries = transform_region_boundaries(
            region,
            scale_transform
        )

        new_region = FilledRegion.Create(
            doc,
            type_id,
            view.Id,
            boundaries
        )

        if new_region is None:
            return None, False, "FilledRegion.Create returned None"

        copy_string_parameters(
            region,
            new_region
        )

        old_id = region.Id

        doc.Delete(old_id)

        return new_region, True, None

    except Exception as error:
        return None, False, safe_string(error)


# ============================================================
# TEXT NOTES
# ============================================================

def get_text_size(text_type):
    try:
        parameter = text_type.get_Parameter(
            BuiltInParameter.TEXT_SIZE
        )

        if parameter:
            return parameter.AsDouble()
    except Exception:
        pass

    return None


def set_text_size(text_type, size):
    try:
        parameter = text_type.get_Parameter(
            BuiltInParameter.TEXT_SIZE
        )

        if parameter and not parameter.IsReadOnly:
            parameter.Set(size)
            return True
    except Exception:
        pass

    return False


def get_scaled_text_type(
    doc,
    text_note,
    factor,
    cache
):
    original_type_id = text_note.GetTypeId()

    key = (
        eid_value(original_type_id),
        round(factor, 6)
    )

    if key in cache:
        return cache[key]

    original_type = doc.GetElement(
        original_type_id
    )

    if not isinstance(original_type, TextNoteType):
        return original_type_id

    original_size = get_text_size(
        original_type
    )

    if original_size is None:
        return original_type_id

    new_name = "{0}_Scale_{1}".format(
        original_type.Name,
        safe_string(round(factor, 4)).replace(".", "_")
    )

    for text_type in (
        FilteredElementCollector(doc)
        .OfClass(TextNoteType)
    ):
        try:
            if text_type.Name == new_name:
                cache[key] = text_type.Id
                return text_type.Id
        except Exception:
            continue

    try:
        new_type_id = original_type.Duplicate(
            new_name
        )

        new_type = doc.GetElement(
            new_type_id
        )

        set_text_size(
            new_type,
            original_size * factor
        )

        cache[key] = new_type_id

        return new_type_id

    except Exception:
        return original_type_id


def scale_text_note(
    doc,
    text_note,
    factor,
    base_point,
    text_type_cache
):
    try:
        original_point = text_note.Coord

        target_point = scale_point(
            original_point,
            factor,
            base_point
        )

        movement = target_point.Subtract(
            original_point
        )

        ElementTransformUtils.MoveElement(
            doc,
            text_note.Id,
            movement
        )

        new_type_id = get_scaled_text_type(
            doc,
            text_note,
            factor,
            text_type_cache
        )

        if (
            new_type_id is not None
            and new_type_id != text_note.GetTypeId()
        ):
            text_note.ChangeTypeId(
                new_type_id
            )

        return True, None

    except Exception as error:
        return False, safe_string(error)


# ============================================================
# NESTED FAMILY INSTANCES
# ============================================================

def move_nested_instance(
    doc,
    instance,
    factor,
    parent_base_point
):
    """
    Moves the insertion point according to the parent scale.
    The instance's family definition is scaled separately.
    """

    try:
        location = instance.Location

        if not isinstance(location, LocationPoint):
            return False, "Nested family has no LocationPoint"

        old_point = location.Point

        new_point = scale_point(
            old_point,
            factor,
            parent_base_point
        )

        movement = new_point.Subtract(
            old_point
        )

        ElementTransformUtils.MoveElement(
            doc,
            instance.Id,
            movement
        )

        return True, None

    except Exception as error:
        return False, safe_string(error)


# ============================================================
# DOCUMENT SCALING
# ============================================================

def scale_document_native_elements(
    doc,
    view,
    factor,
    base_point,
    include_nested_positions=True
):
    statistics = {
        "curves": 0,
        "regions": 0,
        "texts": 0,
        "instances_moved": 0,
        "failed": 0
    }

    failed_messages = []
    text_type_cache = {}

    scale_transform = create_scale_transform(
        factor,
        base_point
    )

    curves = get_curve_elements(doc)
    regions = get_regions(doc)
    texts = get_text_notes(doc)
    instances = get_nested_instances(doc)

    transaction = Transaction(
        doc,
        "Scale native family geometry"
    )

    transaction.Start()

    for curve_element in curves:
        success, error = scale_curve_element(
            curve_element,
            scale_transform
        )

        if success:
            statistics["curves"] += 1
        else:
            statistics["failed"] += 1
            failed_messages.append(
                "Curve {0}: {1}".format(
                    eid_value(curve_element.Id),
                    error
                )
            )

    # Copy list because existing regions are deleted and recreated.
    for region in list(regions):
        new_region, success, error = recreate_region(
            doc,
            view,
            region,
            scale_transform
        )

        if success:
            statistics["regions"] += 1
        else:
            statistics["failed"] += 1
            failed_messages.append(
                "Region {0}: {1}".format(
                    eid_value(region.Id),
                    error
                )
            )

    for text_note in texts:
        success, error = scale_text_note(
            doc,
            text_note,
            factor,
            base_point,
            text_type_cache
        )

        if success:
            statistics["texts"] += 1
        else:
            statistics["failed"] += 1
            failed_messages.append(
                "Text {0}: {1}".format(
                    eid_value(text_note.Id),
                    error
                )
            )

    if include_nested_positions:
        for instance in instances:
            success, error = move_nested_instance(
                doc,
                instance,
                factor,
                base_point
            )

            if success:
                statistics["instances_moved"] += 1
            else:
                statistics["failed"] += 1
                failed_messages.append(
                    "Nested instance {0}: {1}".format(
                        eid_value(instance.Id),
                        error
                    )
                )

    transaction.Commit()

    return statistics, failed_messages


# ============================================================
# RECURSIVE NESTED FAMILY SCALING
# ============================================================

def get_unique_nested_families(doc):
    families = {}
    result = []

    for instance in get_nested_instances(doc):
        try:
            family = instance.Symbol.Family

            if family is None:
                continue

            key = family.UniqueId

            if key in families:
                continue

            families[key] = True
            result.append(family)

        except Exception:
            continue

    return result


def recursively_scale_nested_families(
    parent_doc,
    factor,
    processed_family_ids,
    depth=0
):
    report = []

    if depth > MAX_NESTED_DEPTH:
        report.append(
            "Maximum nested family depth reached."
        )
        return report

    nested_families = get_unique_nested_families(
        parent_doc
    )

    for family in nested_families:
        family_key = safe_string(family.UniqueId)

        if family_key in processed_family_ids:
            continue

        processed_family_ids.add(
            family_key
        )

        nested_doc = None

        try:
            # EditFamily requires that parent_doc is not modifiable.
            nested_doc = parent_doc.EditFamily(
                family
            )

            if nested_doc is None:
                report.append(
                    "Could not edit nested family: {0}".format(
                        family.Name
                    )
                )
                continue

            nested_view = get_usable_view(
                nested_doc
            )

            if nested_view is None:
                report.append(
                    "No usable view in nested family: {0}".format(
                        family.Name
                    )
                )
                nested_doc.Close(False)
                nested_doc = None
                continue

            # First process deeper nested definitions.
            deeper_report = recursively_scale_nested_families(
                nested_doc,
                factor,
                processed_family_ids,
                depth + 1
            )

            report.extend(
                deeper_report
            )

            # Scale nested family content about its own insertion origin.
            statistics, failures = scale_document_native_elements(
                nested_doc,
                nested_view,
                factor,
                NESTED_BASE_POINT,
                include_nested_positions=True
            )

            loaded = nested_doc.LoadFamily(
                parent_doc,
                LOAD_OPTIONS
            )

            report.append(
                (
                    "{0}: curves={1}, regions={2}, texts={3}, "
                    "instances={4}, loaded={5}"
                ).format(
                    family.Name,
                    statistics["curves"],
                    statistics["regions"],
                    statistics["texts"],
                    statistics["instances_moved"],
                    loaded
                )
            )

            for failure in failures[:10]:
                report.append(
                    "{0}: {1}".format(
                        family.Name,
                        failure
                    )
                )

            nested_doc.Close(False)
            nested_doc = None

        except Exception as error:
            report.append(
                "Nested family {0}: {1}".format(
                    getattr(family, "Name", "Unknown"),
                    safe_string(error)
                )
            )

            if nested_doc is not None:
                try:
                    nested_doc.Close(False)
                except Exception:
                    pass

    return report


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        validate_root_document()

        factor_text = forms.ask_for_string(
            default="0.75",
            prompt=(
                "Enter the uniform scale factor.\n\n"
                "Examples:\n"
                "0.50 = half size\n"
                "0.75 = 25% smaller\n"
                "1.50 = 50% larger\n"
                "150% = 50% larger"
            ),
            title="Scale Complete Key Plan"
        )

        if factor_text is None:
            return

        factor = parse_factor(
            factor_text
        )

        if abs(factor - 1.0) <= FACTOR_TOLERANCE:
            alert(
                "Scale factor is 1.0. Nothing was changed."
            )
            return

        root_base_point, base_description = choose_root_base_point()

        if root_base_point is None:
            return

        confirmation = forms.alert(
            (
                "Scale the complete Key Plan family?\n\n"
                "Factor: {0}\n"
                "Base point: {1}\n\n"
                "The tool will process:\n"
                "• Symbolic and Detail Lines\n"
                "• Filled and Masking Regions\n"
                "• Text Notes\n"
                "• Nested family definitions\n"
                "• Nested family positions\n\n"
                "Make sure you saved a backup copy."
            ).format(
                factor,
                base_description
            ),
            title="Scale Complete Key Plan",
            yes=True,
            no=True
        )

        if not confirmation:
            return

        # Nested families must be edited when the parent document
        # does not have an open transaction.
        nested_report = recursively_scale_nested_families(
            root_doc,
            factor,
            set()
        )

        root_statistics, root_failures = scale_document_native_elements(
            root_doc,
            root_view,
            factor,
            root_base_point,
            include_nested_positions=True
        )

        result = (
            "Complete Key Plan scaling finished.\n\n"
            "Factor: {0}\n"
            "Base point: {1}\n\n"
            "Root family:\n"
            "Curves scaled: {2}\n"
            "Regions scaled: {3}\n"
            "Text Notes scaled: {4}\n"
            "Nested instances moved: {5}\n"
            "Failed elements: {6}\n\n"
            "Nested families processed: {7}"
        ).format(
            factor,
            base_description,
            root_statistics["curves"],
            root_statistics["regions"],
            root_statistics["texts"],
            root_statistics["instances_moved"],
            root_statistics["failed"],
            len(nested_report)
        )

        alert(
            result,
            "Scale Complete Key Plan – Finished"
        )

        output.print_md(
            "## Scale Complete Key Plan Report"
        )

        output.print_md(
            "**Factor:** `{0}`".format(factor)
        )

        if nested_report:
            output.print_md(
                "### Nested families"
            )

            for line in nested_report:
                output.print_md(
                    "- {0}".format(line)
                )

        if root_failures:
            output.print_md(
                "### Root family elements not scaled"
            )

            for line in root_failures:
                output.print_md(
                    "- `{0}`".format(line)
                )

    except Exception as error:
        output.print_md(
            "## Scale Complete Key Plan – Error"
        )

        output.print_md("```text")
        output.print_md(
            traceback.format_exc()
        )
        output.print_md("```")

        alert(
            (
                "Scaling failed:\n\n{0}\n\n"
                "See the pyRevit output window for the complete report."
            ).format(error),
            "Scale Complete Key Plan – Error"
        )


if __name__ == "__main__":
    main()