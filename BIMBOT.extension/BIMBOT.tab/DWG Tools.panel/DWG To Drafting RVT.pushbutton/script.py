# -*- coding: utf-8 -*-
"""
DWG To Native Revit 2D

Reads a DWG through AutoCAD ActiveX/COM and creates:
- Detail Lines
- Detail Arcs
- Circles
- Polylines
- Native Revit TextNotes
- Nested block geometry
- Block attributes as TextNotes

Requirements:
- Windows
- Full AutoCAD installed
- Revit + pyRevit
- Active Revit view must support Detail Curves and TextNotes

Recommended for:
- Title Block families
- Generic Annotation families
- Drafting Views
- Legends and other compatible 2D views

Important:
- Hatches, dimensions, leaders and raster images are not fully recreated.
- Font appearance can vary if the AutoCAD font does not exist in Windows.
"""

__title__ = "DWG To\nNative 2D"
__author__ = "Sabin / BIMBOT"
__doc__ = "Convert DWG linework, symbols, blocks and text into native Revit 2D elements."

import clr
import math
import os
import re
import traceback

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
clr.AddReference("Microsoft.CSharp")

from Autodesk.Revit.DB import (
    Arc,
    BuiltInParameter,
    Color,
    Curve,
    ElementId,
    FilteredElementCollector,
    GraphicsStyleType,
    Line,
    OverrideGraphicSettings,
    TextNote,
    TextNoteOptions,
    TextNoteType,
    Transaction,
    UnitUtils,
    ViewType,
    XYZ
)

from System import Activator, Type
from System.Collections.Generic import List

from pyrevit import forms, script


# ============================================================
# REVIT CONTEXT
# ============================================================

uiapp = __revit__
uidoc = uiapp.ActiveUIDocument
doc = uidoc.Document
view = doc.ActiveView
app = uiapp.Application

output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

# DWG drawing units.
# Change this only if your DWG is not drawn in millimetres.
DWG_UNIT_TO_FEET = 1.0 / 304.8

# Geometry shorter than this value is ignored.
MIN_LENGTH = app.ShortCurveTolerance * 1.10

# Approximation settings.
CIRCLE_SEGMENTS_FALLBACK = 72
ELLIPSE_SEGMENTS = 72
SPLINE_SEGMENTS = 80

# Text settings.
DEFAULT_FONT = "Arial"
DEFAULT_TEXT_HEIGHT_MM = 2.5
MIN_TEXT_HEIGHT_MM = 0.8
MAX_TEXT_HEIGHT_MM = 100.0

# Delete an already imported DWG selected by the user after conversion.
DELETE_SELECTED_REVIT_IMPORT = False

# Create separate Revit text types based on font and text height.
CREATE_TEXT_TYPES = True

# Apply Revit element overrides based on AutoCAD colors.
PRESERVE_COLORS = True

# Create closed segment between last and first polyline point.
CLOSE_CLOSED_POLYLINES = True


# ============================================================
# GENERAL UTILITIES
# ============================================================

def alert(message, title="DWG To Native 2D"):
    forms.alert(message, title=title)


def safe_str(value, fallback=""):
    try:
        if value is None:
            return fallback
        return str(value)
    except Exception:
        return fallback


def clean_name(value, fallback="DWG"):
    text = safe_str(value, fallback).strip()

    if not text:
        text = fallback

    text = re.sub(r'[\\/:{}\[\]|;<>?`~"]', "_", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:120]


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def mm_to_feet(value):
    return float(value) / 304.8


def dwg_to_feet(value):
    return float(value) * DWG_UNIT_TO_FEET


def point_to_xyz(point, transform_2d=None):
    """
    Convert AutoCAD point array to Revit XYZ.

    transform_2d is a tuple:
    (a, b, c, d, tx, ty)
    x2 = a*x + c*y + tx
    y2 = b*x + d*y + ty
    """
    try:
        x = float(point[0])
        y = float(point[1])
    except Exception:
        return None

    if transform_2d is not None:
        a, b, c, d, tx, ty = transform_2d
        transformed_x = a * x + c * y + tx
        transformed_y = b * x + d * y + ty
        x = transformed_x
        y = transformed_y

    return XYZ(
        dwg_to_feet(x),
        dwg_to_feet(y),
        get_view_plane_z()
    )


def get_view_plane_z():
    try:
        if view.GenLevel:
            return view.GenLevel.Elevation
    except Exception:
        pass

    try:
        return view.Origin.Z
    except Exception:
        return 0.0


VIEW_Z = get_view_plane_z()


def valid_line_points(point_1, point_2):
    if point_1 is None or point_2 is None:
        return False

    try:
        return point_1.DistanceTo(point_2) > MIN_LENGTH
    except Exception:
        return False


def compose_transform(parent, child):
    """
    Compose two 2D affine transformations.

    parent and child:
    (a, b, c, d, tx, ty)
    """
    pa, pb, pc, pd, ptx, pty = parent
    ca, cb, cc, cd, ctx, cty = child

    return (
        pa * ca + pc * cb,
        pb * ca + pd * cb,
        pa * cc + pc * cd,
        pb * cc + pd * cd,
        pa * ctx + pc * cty + ptx,
        pb * ctx + pd * cty + pty
    )


IDENTITY_2D = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def block_transform(block_reference):
    """
    Build a 2D transform from an AutoCAD BlockReference.
    """
    try:
        insertion = block_reference.InsertionPoint
        tx = float(insertion[0])
        ty = float(insertion[1])
    except Exception:
        tx = 0.0
        ty = 0.0

    try:
        rotation = float(block_reference.Rotation)
    except Exception:
        rotation = 0.0

    try:
        sx = float(block_reference.XScaleFactor)
    except Exception:
        sx = 1.0

    try:
        sy = float(block_reference.YScaleFactor)
    except Exception:
        sy = 1.0

    cosine = math.cos(rotation)
    sine = math.sin(rotation)

    return (
        sx * cosine,
        sx * sine,
        -sy * sine,
        sy * cosine,
        tx,
        ty
    )


def transformed_angle(angle, transform_2d):
    """
    Transform a text or geometry rotation through an affine transform.
    """
    try:
        dx = math.cos(angle)
        dy = math.sin(angle)

        a, b, c, d, tx, ty = transform_2d

        transformed_dx = a * dx + c * dy
        transformed_dy = b * dx + d * dy

        return math.atan2(transformed_dy, transformed_dx)
    except Exception:
        return angle


def transform_scale(transform_2d):
    """
    Approximate the resulting scale of a block transform.
    """
    try:
        a, b, c, d, tx, ty = transform_2d

        scale_x = math.sqrt(a * a + b * b)
        scale_y = math.sqrt(c * c + d * d)

        return max((scale_x + scale_y) / 2.0, 0.000001)
    except Exception:
        return 1.0


# ============================================================
# VIEW VALIDATION
# ============================================================

def validate_active_view():
    if view is None:
        raise Exception("No active Revit view was found.")

    try:
        if view.IsTemplate:
            raise Exception("The active view is a View Template.")
    except Exception:
        pass

    unsupported = []

    try:
        unsupported = [
            ViewType.ThreeD,
            ViewType.DrawingSheet,
            ViewType.Schedule,
            ViewType.Report,
            ViewType.Rendering,
            ViewType.Walkthrough
        ]
    except Exception:
        unsupported = []

    try:
        if view.ViewType in unsupported:
            raise Exception(
                "The active view does not support native Detail Curves "
                "and TextNotes.\n\n"
                "Open a Title Block family view, Drafting View, Floor Plan "
                "or another compatible 2D view."
            )
    except AttributeError:
        pass


# ============================================================
# AUTOCAD CONNECTION
# ============================================================

def get_autocad_application():
    """
    Connect to AutoCAD or create a new AutoCAD COM instance.
    """
    programmatic_ids = [
        "AutoCAD.Application.25",
        "AutoCAD.Application.24.3",
        "AutoCAD.Application.24.2",
        "AutoCAD.Application.24.1",
        "AutoCAD.Application.24",
        "AutoCAD.Application.23.1",
        "AutoCAD.Application.23",
        "AutoCAD.Application"
    ]

    errors = []

    for programmatic_id in programmatic_ids:
        try:
            com_type = Type.GetTypeFromProgID(programmatic_id)

            if com_type is None:
                continue

            acad_app = Activator.CreateInstance(com_type)
            acad_app.Visible = False
            return acad_app

        except Exception as ex:
            errors.append(
                "{0}: {1}".format(programmatic_id, safe_str(ex))
            )

    raise Exception(
        "AutoCAD ActiveX could not be started.\n\n"
        "A full version of AutoCAD must be installed on this computer.\n\n"
        + "\n".join(errors[-3:])
    )


def open_autocad_document(acad_app, dwg_path):
    try:
        return acad_app.Documents.Open(dwg_path, True)
    except Exception as ex:
        raise Exception(
            "AutoCAD could not open the selected DWG.\n\n{0}".format(ex)
        )


# ============================================================
# AUTOCAD COLOR HANDLING
# ============================================================

ACI_COLORS = {
    1: (255, 0, 0),
    2: (255, 255, 0),
    3: (0, 255, 0),
    4: (0, 255, 255),
    5: (0, 0, 255),
    6: (255, 0, 255),
    7: (255, 255, 255),
    8: (128, 128, 128),
    9: (192, 192, 192)
}


def true_color_to_rgb(entity):
    try:
        true_color = entity.TrueColor

        red = int(true_color.Red)
        green = int(true_color.Green)
        blue = int(true_color.Blue)

        if red >= 0 and green >= 0 and blue >= 0:
            return (
                clamp(red, 0, 255),
                clamp(green, 0, 255),
                clamp(blue, 0, 255)
            )
    except Exception:
        pass

    return None


def acad_color_to_rgb(entity, acad_doc):
    """
    Determine the effective AutoCAD color approximately.
    """
    rgb = true_color_to_rgb(entity)

    if rgb:
        return rgb

    try:
        color_index = int(entity.Color)
    except Exception:
        color_index = 7

    # ByLayer
    if color_index == 256:
        try:
            layer_name = entity.Layer
            layer = acad_doc.Layers.Item(layer_name)

            rgb = true_color_to_rgb(layer)

            if rgb:
                return rgb

            color_index = int(layer.Color)
        except Exception:
            color_index = 7

    # ByBlock: inherit where possible, otherwise black.
    if color_index == 0:
        color_index = 7

    if color_index in ACI_COLORS:
        rgb = ACI_COLORS[color_index]
    else:
        # Approximate unsupported indexed colors.
        gray = int(clamp((color_index / 255.0) * 230.0, 30, 230))
        rgb = (gray, gray, gray)

    # AutoCAD index 7 can display white or black depending on background.
    # Black is preferable on a Revit sheet.
    if color_index == 7:
        rgb = (0, 0, 0)

    return rgb


def apply_element_color(element, rgb):
    if not PRESERVE_COLORS or element is None or rgb is None:
        return

    try:
        revit_color = Color(
            int(rgb[0]),
            int(rgb[1]),
            int(rgb[2])
        )

        overrides = OverrideGraphicSettings()
        overrides.SetProjectionLineColor(revit_color)

        try:
            overrides.SetCutLineColor(revit_color)
        except Exception:
            pass

        view.SetElementOverrides(element.Id, overrides)
    except Exception:
        pass


# ============================================================
# TEXT TYPE HANDLING
# ============================================================

def get_default_text_type():
    text_types = list(
        FilteredElementCollector(doc)
        .OfClass(TextNoteType)
    )

    if not text_types:
        raise Exception(
            "No Revit Text Note type exists in this document."
        )

    return text_types[0]


def get_text_parameter(element_type, built_in_parameter):
    try:
        return element_type.get_Parameter(built_in_parameter)
    except Exception:
        return None


def set_text_type_font(text_type, font_name):
    try:
        parameter = get_text_parameter(
            text_type,
            BuiltInParameter.TEXT_FONT
        )

        if parameter and not parameter.IsReadOnly:
            parameter.Set(font_name)
    except Exception:
        pass


def set_text_type_size(text_type, height_feet):
    try:
        parameter = get_text_parameter(
            text_type,
            BuiltInParameter.TEXT_SIZE
        )

        if parameter and not parameter.IsReadOnly:
            parameter.Set(height_feet)
    except Exception:
        pass


def get_or_create_text_type(
        font_name,
        text_height_feet,
        text_type_cache
):
    if not CREATE_TEXT_TYPES:
        return get_default_text_type()

    height_mm = text_height_feet * 304.8
    rounded_height = round(height_mm, 2)

    key = (
        safe_str(font_name, DEFAULT_FONT).lower(),
        rounded_height
    )

    if key in text_type_cache:
        return text_type_cache[key]

    base_type = get_default_text_type()

    type_name = clean_name(
        "DWG_{0}_{1}mm".format(
            font_name or DEFAULT_FONT,
            rounded_height
        ),
        "DWG Text"
    )

    existing_types = list(
        FilteredElementCollector(doc)
        .OfClass(TextNoteType)
    )

    for existing_type in existing_types:
        try:
            if existing_type.Name == type_name:
                text_type_cache[key] = existing_type
                return existing_type
        except Exception:
            pass

    try:
        new_type_id = base_type.Duplicate(type_name)
        new_type = doc.GetElement(new_type_id)

        set_text_type_font(
            new_type,
            font_name or DEFAULT_FONT
        )

        set_text_type_size(
            new_type,
            text_height_feet
        )

        text_type_cache[key] = new_type
        return new_type

    except Exception:
        text_type_cache[key] = base_type
        return base_type


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_mtext(text):
    """
    Convert common AutoCAD MTEXT formatting codes into readable text.
    """
    value = safe_str(text)

    if not value:
        return ""

    value = value.replace("\\P", "\n")
    value = value.replace("\\~", " ")
    value = value.replace("%%d", u"°")
    value = value.replace("%%p", u"±")
    value = value.replace("%%c", u"Ø")

    # Remove grouped formatting such as {\fArial|...;Text}
    value = re.sub(r"\\[A-Za-z][^;]*;", "", value)
    value = re.sub(r"\\[LlOoKk]", "", value)
    value = value.replace("{", "")
    value = value.replace("}", "")

    # Remove stacked fraction syntax while keeping readable values.
    value = re.sub(r"\\S([^;]+);", r"\1", value)

    return value.strip()


def get_text_font(entity, acad_doc):
    try:
        style_name = entity.StyleName
        text_style = acad_doc.TextStyles.Item(style_name)

        font_file = safe_str(text_style.FontFile)

        if font_file:
            base_name = os.path.splitext(
                os.path.basename(font_file)
            )[0]

            if base_name:
                return base_name
    except Exception:
        pass

    return DEFAULT_FONT


def get_text_height(entity, parent_transform):
    try:
        height = float(entity.Height)
    except Exception:
        try:
            height = float(entity.TextHeight)
        except Exception:
            height = DEFAULT_TEXT_HEIGHT_MM

    height *= transform_scale(parent_transform)

    height_mm = height

    # Uses the DWG unit setting.
    if abs(DWG_UNIT_TO_FEET - (1.0 / 304.8)) > 0.0000001:
        height_mm = dwg_to_feet(height) * 304.8

    height_mm = clamp(
        height_mm,
        MIN_TEXT_HEIGHT_MM,
        MAX_TEXT_HEIGHT_MM
    )

    return mm_to_feet(height_mm)


def get_text_position(entity, transform_2d):
    possible_properties = [
        "TextAlignmentPoint",
        "InsertionPoint"
    ]

    for property_name in possible_properties:
        try:
            point = getattr(entity, property_name)

            if point is not None:
                return point_to_xyz(point, transform_2d)
        except Exception:
            continue

    return None


def get_text_rotation(entity, transform_2d):
    try:
        rotation = float(entity.Rotation)
    except Exception:
        rotation = 0.0

    return transformed_angle(rotation, transform_2d)


# ============================================================
# REVIT ELEMENT CREATION
# ============================================================

def create_detail_line(point_1, point_2, rgb, created_ids, stats):
    if not valid_line_points(point_1, point_2):
        stats["skipped"] += 1
        return

    try:
        line = Line.CreateBound(point_1, point_2)
        element = doc.Create.NewDetailCurve(view, line)

        apply_element_color(element, rgb)

        created_ids.Add(element.Id)
        stats["curves"] += 1

    except Exception:
        stats["failed"] += 1


def create_detail_arc_from_three_points(
        start_point,
        end_point,
        middle_point,
        rgb,
        created_ids,
        stats
):
    if (
        start_point is None
        or end_point is None
        or middle_point is None
    ):
        stats["skipped"] += 1
        return

    try:
        arc = Arc.Create(
            start_point,
            end_point,
            middle_point
        )

        element = doc.Create.NewDetailCurve(view, arc)

        apply_element_color(element, rgb)

        created_ids.Add(element.Id)
        stats["curves"] += 1

    except Exception:
        stats["failed"] += 1


def create_circle(
        center,
        radius_dwg,
        transform_2d,
        rgb,
        created_ids,
        stats
):
    """
    Create a circle using two Revit semicircular arcs.
    """
    try:
        center_xyz = point_to_xyz(center, transform_2d)

        if center_xyz is None:
            stats["skipped"] += 1
            return

        radius = dwg_to_feet(
            float(radius_dwg) * transform_scale(transform_2d)
        )

        if radius <= MIN_LENGTH:
            stats["skipped"] += 1
            return

        right = XYZ(
            center_xyz.X + radius,
            center_xyz.Y,
            VIEW_Z
        )
        left = XYZ(
            center_xyz.X - radius,
            center_xyz.Y,
            VIEW_Z
        )
        top = XYZ(
            center_xyz.X,
            center_xyz.Y + radius,
            VIEW_Z
        )
        bottom = XYZ(
            center_xyz.X,
            center_xyz.Y - radius,
            VIEW_Z
        )

        create_detail_arc_from_three_points(
            right,
            left,
            top,
            rgb,
            created_ids,
            stats
        )

        create_detail_arc_from_three_points(
            left,
            right,
            bottom,
            rgb,
            created_ids,
            stats
        )

    except Exception:
        stats["failed"] += 1


def create_text_note(
        text,
        position,
        rotation,
        height_feet,
        font_name,
        rgb,
        text_type_cache,
        created_ids,
        stats
):
    text = clean_mtext(text)

    if not text or position is None:
        stats["skipped"] += 1
        return

    try:
        text_type = get_or_create_text_type(
            font_name,
            height_feet,
            text_type_cache
        )

        options = TextNoteOptions(text_type.Id)

        try:
            options.Rotation = rotation
        except Exception:
            pass

        text_note = TextNote.Create(
            doc,
            view.Id,
            position,
            text,
            options
        )

        apply_element_color(text_note, rgb)

        created_ids.Add(text_note.Id)
        stats["texts"] += 1

    except Exception:
        stats["failed"] += 1


# ============================================================
# AUTOCAD ENTITY READERS
# ============================================================

def get_object_name(entity):
    try:
        return safe_str(entity.ObjectName)
    except Exception:
        return ""


def read_coordinates_array(entity):
    try:
        values = list(entity.Coordinates)
    except Exception:
        return []

    points = []

    step = 2

    # Some old 3D polyline types return XYZ triplets.
    try:
        if len(values) % 3 == 0 and len(values) % 2 != 0:
            step = 3
    except Exception:
        step = 2

    index = 0

    while index + 1 < len(values):
        points.append(
            (
                float(values[index]),
                float(values[index + 1]),
                0.0
            )
        )
        index += step

    return points


def process_line(
        entity,
        transform_2d,
        rgb,
        created_ids,
        stats
):
    try:
        point_1 = point_to_xyz(
            entity.StartPoint,
            transform_2d
        )
        point_2 = point_to_xyz(
            entity.EndPoint,
            transform_2d
        )

        create_detail_line(
            point_1,
            point_2,
            rgb,
            created_ids,
            stats
        )

    except Exception:
        stats["failed"] += 1


def process_circle(
        entity,
        transform_2d,
        rgb,
        created_ids,
        stats
):
    try:
        create_circle(
            entity.Center,
            entity.Radius,
            transform_2d,
            rgb,
            created_ids,
            stats
        )
    except Exception:
        stats["failed"] += 1


def point_on_acad_arc(center, radius, angle):
    return (
        float(center[0]) + float(radius) * math.cos(angle),
        float(center[1]) + float(radius) * math.sin(angle),
        0.0
    )


def process_arc(
        entity,
        transform_2d,
        rgb,
        created_ids,
        stats
):
    try:
        center = entity.Center
        radius = float(entity.Radius)
        start_angle = float(entity.StartAngle)
        end_angle = float(entity.EndAngle)

        while end_angle <= start_angle:
            end_angle += 2.0 * math.pi

        middle_angle = (
            start_angle + end_angle
        ) / 2.0

        start_point = point_to_xyz(
            point_on_acad_arc(
                center,
                radius,
                start_angle
            ),
            transform_2d
        )

        end_point = point_to_xyz(
            point_on_acad_arc(
                center,
                radius,
                end_angle
            ),
            transform_2d
        )

        middle_point = point_to_xyz(
            point_on_acad_arc(
                center,
                radius,
                middle_angle
            ),
            transform_2d
        )

        create_detail_arc_from_three_points(
            start_point,
            end_point,
            middle_point,
            rgb,
            created_ids,
            stats
        )

    except Exception:
        stats["failed"] += 1


def process_polyline(
        entity,
        transform_2d,
        rgb,
        created_ids,
        stats
):
    points = read_coordinates_array(entity)

    if len(points) < 2:
        stats["skipped"] += 1
        return

    for index in range(len(points) - 1):
        point_1 = point_to_xyz(
            points[index],
            transform_2d
        )
        point_2 = point_to_xyz(
            points[index + 1],
            transform_2d
        )

        create_detail_line(
            point_1,
            point_2,
            rgb,
            created_ids,
            stats
        )

    try:
        is_closed = bool(entity.Closed)
    except Exception:
        is_closed = False

    if is_closed and CLOSE_CLOSED_POLYLINES:
        point_1 = point_to_xyz(
            points[-1],
            transform_2d
        )
        point_2 = point_to_xyz(
            points[0],
            transform_2d
        )

        create_detail_line(
            point_1,
            point_2,
            rgb,
            created_ids,
            stats
        )


def process_text(
        entity,
        transform_2d,
        rgb,
        acad_doc,
        text_type_cache,
        created_ids,
        stats
):
    try:
        text = entity.TextString
    except Exception:
        text = ""

    position = get_text_position(
        entity,
        transform_2d
    )

    rotation = get_text_rotation(
        entity,
        transform_2d
    )

    height = get_text_height(
        entity,
        transform_2d
    )

    font = get_text_font(
        entity,
        acad_doc
    )

    create_text_note(
        text,
        position,
        rotation,
        height,
        font,
        rgb,
        text_type_cache,
        created_ids,
        stats
    )


def process_attributes(
        block_reference,
        transform_2d,
        acad_doc,
        text_type_cache,
        created_ids,
        stats
):
    try:
        has_attributes = bool(
            block_reference.HasAttributes
        )
    except Exception:
        has_attributes = False

    if not has_attributes:
        return

    try:
        attributes = block_reference.GetAttributes()
    except Exception:
        return

    for attribute in attributes:
        rgb = acad_color_to_rgb(
            attribute,
            acad_doc
        )

        process_text(
            attribute,
            transform_2d,
            rgb,
            acad_doc,
            text_type_cache,
            created_ids,
            stats
        )


def process_block_reference(
        block_reference,
        parent_transform,
        acad_doc,
        text_type_cache,
        created_ids,
        stats,
        recursion_stack
):
    try:
        block_name = safe_str(
            block_reference.EffectiveName
        )
    except Exception:
        try:
            block_name = safe_str(
                block_reference.Name
            )
        except Exception:
            block_name = ""

    if not block_name:
        stats["skipped"] += 1
        return

    # Avoid cyclic block references.
    if block_name in recursion_stack:
        stats["skipped"] += 1
        return

    local_transform = block_transform(
        block_reference
    )

    combined_transform = compose_transform(
        parent_transform,
        local_transform
    )

    process_attributes(
        block_reference,
        combined_transform,
        acad_doc,
        text_type_cache,
        created_ids,
        stats
    )

    try:
        block_definition = acad_doc.Blocks.Item(
            block_name
        )
    except Exception:
        stats["failed"] += 1
        return

    new_stack = set(recursion_stack)
    new_stack.add(block_name)

    for nested_entity in block_definition:
        process_entity(
            nested_entity,
            combined_transform,
            acad_doc,
            text_type_cache,
            created_ids,
            stats,
            new_stack
        )


def process_entity(
        entity,
        transform_2d,
        acad_doc,
        text_type_cache,
        created_ids,
        stats,
        recursion_stack
):
    object_name = get_object_name(entity)

    rgb = acad_color_to_rgb(
        entity,
        acad_doc
    )

    if object_name == "AcDbLine":
        process_line(
            entity,
            transform_2d,
            rgb,
            created_ids,
            stats
        )

    elif object_name == "AcDbCircle":
        process_circle(
            entity,
            transform_2d,
            rgb,
            created_ids,
            stats
        )

    elif object_name == "AcDbArc":
        process_arc(
            entity,
            transform_2d,
            rgb,
            created_ids,
            stats
        )

    elif object_name in [
        "AcDbPolyline",
        "AcDb2dPolyline",
        "AcDb3dPolyline"
    ]:
        process_polyline(
            entity,
            transform_2d,
            rgb,
            created_ids,
            stats
        )

    elif object_name in [
        "AcDbText",
        "AcDbMText",
        "AcDbAttribute",
        "AcDbAttributeDefinition"
    ]:
        process_text(
            entity,
            transform_2d,
            rgb,
            acad_doc,
            text_type_cache,
            created_ids,
            stats
        )

    elif object_name in [
        "AcDbBlockReference",
        "AcDbMInsertBlock"
    ]:
        process_block_reference(
            entity,
            transform_2d,
            acad_doc,
            text_type_cache,
            created_ids,
            stats,
            recursion_stack
        )

    else:
        stats["unsupported"] += 1


# ============================================================
# USER INTERFACE
# ============================================================

def select_dwg_path():
    return forms.pick_file(
        file_ext="dwg",
        title="Select the DWG to convert"
    )


def select_autocad_space():
    options = [
        "Model Space",
        "Paper Space",
        "Model Space + Paper Space"
    ]

    selected = forms.SelectFromList.show(
        options,
        title="Select AutoCAD space",
        button_name="Convert",
        multiselect=False
    )

    return selected


# ============================================================
# MAIN
# ============================================================

def main():
    acad_app = None
    acad_doc = None
    transaction = None

    try:
        validate_active_view()

        dwg_path = select_dwg_path()

        if not dwg_path:
            return

        if not os.path.isfile(dwg_path):
            raise Exception(
                "The selected DWG file does not exist."
            )

        selected_space = select_autocad_space()

        if not selected_space:
            return

        acad_app = get_autocad_application()
        acad_doc = open_autocad_document(
            acad_app,
            dwg_path
        )

        created_ids = List[ElementId]()
        text_type_cache = {}

        stats = {
            "curves": 0,
            "texts": 0,
            "failed": 0,
            "skipped": 0,
            "unsupported": 0
        }

        transaction = Transaction(
            doc,
            "Convert DWG to native Revit 2D"
        )

        transaction.Start()

        if selected_space in [
            "Model Space",
            "Model Space + Paper Space"
        ]:
            for entity in acad_doc.ModelSpace:
                process_entity(
                    entity,
                    IDENTITY_2D,
                    acad_doc,
                    text_type_cache,
                    created_ids,
                    stats,
                    set()
                )

        if selected_space in [
            "Paper Space",
            "Model Space + Paper Space"
        ]:
            for entity in acad_doc.PaperSpace:
                process_entity(
                    entity,
                    IDENTITY_2D,
                    acad_doc,
                    text_type_cache,
                    created_ids,
                    stats,
                    set()
                )

        transaction.Commit()
        transaction = None

        try:
            acad_doc.Close(False)
            acad_doc = None
        except Exception:
            pass

        try:
            acad_app.Quit()
            acad_app = None
        except Exception:
            pass

        if created_ids.Count > 0:
            try:
                uidoc.Selection.SetElementIds(
                    created_ids
                )
                uidoc.ShowElements(
                    created_ids
                )
            except Exception:
                pass

        alert(
            "Conversion completed.\n\n"
            "Native curves created: {0}\n"
            "Native text notes created: {1}\n"
            "Unsupported AutoCAD objects: {2}\n"
            "Skipped objects: {3}\n"
            "Failed objects: {4}\n\n"
            "The DWG itself was not imported into Revit, so there is "
            "no ImportInstance to delete.\n\n"
            "Check text fonts, alignment and symbols before saving."
            .format(
                stats["curves"],
                stats["texts"],
                stats["unsupported"],
                stats["skipped"],
                stats["failed"]
            ),
            "DWG To Native 2D"
        )

    except Exception as error:
        if transaction is not None:
            try:
                transaction.RollBack()
            except Exception:
                pass

        output.print_md("## DWG To Native 2D – Error")
        output.print_md("```text")
        output.print_md(traceback.format_exc())
        output.print_md("```")

        alert(
            "Conversion failed:\n\n{0}\n\n"
            "See the pyRevit output window for the full report."
            .format(error),
            "DWG To Native 2D – Error"
        )

    finally:
        if acad_doc is not None:
            try:
                acad_doc.Close(False)
            except Exception:
                pass

        if acad_app is not None:
            try:
                acad_app.Quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()