# -*- coding: utf-8 -*-
"""
nx_dlx.py —— Block UI Styler 对话框(.dlx)生成器(纯字符串模板, 无 NX 依赖)
========================================================================

拆分自 nx_extrude_runner.py(§3 .dlx 对话框生成器)。只拼 XML 字符串 + 写盘,
不 import NXOpen。

依赖契约(由主脚本注入): LAYER_TABLE DIALOG_GROUPS JRT_FIELDS MANAGED_MIN
MANAGED_MAX DEFAULT_JRT ZMODE_OPTS BOOL_OPTS DIR_OPTS LAYER_SEL_OPTS
JT_LINK_OPTS script_dir _std_z default_params。
"""

import io
import os
import time


# §3 .dlx 对话框生成器(块模板取自本机 NX2312 官方样例 dlx, 见文件尾注释)
# ============================================================================

def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _blk_double(bid, title, value):
    return (
        '<Property class="UICOMP_double" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Double" type="uicomp">'
        '<item Expanded="1" class="UICOMP_double" hierarchy="" icon="styler_real" id="{id}" '
        'name="{id}" notes="" presentation="Double" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="API Name" '
        'mask="16656" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Expanded" '
        'mask="4" name="Expanded" sname="Expanded" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="HideGroup" '
        'mask="69636" name="HideGroup" sname="HideGroup" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Focus" '
        'mask="69636" name="Focus" sname="Focus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="CanFocus" '
        'mask="69636" name="CanFocus" sname="CanFocus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="KeyboardFocus" '
        'mask="69636" name="KeyboardFocus" sname="KeyboardFocus" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="CanKeyboardFocus" '
        'mask="69636" name="CanKeyboardFocus" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="ReadWrite" '
        'mask="0" name="ReadWrite" sname="RetainValue" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="UIOnly" '
        'mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_double" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="TitleVisibility" mask="0" name="TitleVisibility" sname="TitleVisibility" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="UserLockable" mask="69632" name="UserLockable" sname="UserLockable" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UIFW_spin_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_spin_options" id="Increment" mask="0" name="Increment" sname="Increment" '
        'source="1" type="double" value="1"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MinInclusive" mask="4" name="MinInclusive" sname="MinInclusive" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MaxInclusive" mask="4" name="MaxInclusive" sname="MaxInclusive" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_integer" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="ReadOnlyValue" mask="2" name="ReadOnlyValue" sname="ReadOnlyValue" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="RequiredInput" mask="69632" name="RequiredInput" sname="RequiredInput" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_value" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="AllowUnassignedValue" mask="69632" name="AllowUnassignedValue" sname="AllowUnassignedValue" '
        'source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="VisibleDecimals" mask="69632" name="VisibleDecimals" sname="VisibleDecimals" source="1" '
        'type="integer" value="2"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MaximumValue" mask="0" name="MaximumValue" sname="MaximumValue" source="1" type="double" '
        'value="1.0E+09"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="LimitCheckTolerance" mask="0" name="LimitCheckTolerance" sname="LimitCheckTolerance" '
        'source="1" type="double" value="-1"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="BalloonTooltipText" mask="0" name="BalloonTooltipText" sname="BalloonTooltipText" source="1" '
        'type="utfstring" value=""/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="BalloonTooltipImage" mask="0" name="BalloonTooltipImage" sname="BalloonTooltipImage" '
        'source="1" type="string" value=""/>'
        '<Property ClassID="UGS::UICOMP_double" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_double" id="BalloonTooltipLayout" mask="0" name="BalloonTooltipLayout" '
        'sname="BalloonTooltipLayout" source="1" type="enum" selected="0">'
        '<Option name="Horizontal" value="0"/><Option name="Vertical" value="1"/></Property>'
        '<Property ClassID="UGS::UICOMP_value" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_double" id="PresentationStyle" mask="16640" name="PresentationStyle" '
        'sname="PresentationStyle" source="1" type="enum" selected="0">'
        '<Option name="Keyin" value="0"/><Option name="Spin" value="1"/><Option name="Scale" value="2"/>'
        '<Option name="ScaleKeyin" value="3"/><Option name="Combo" value="4"/></Property>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="MinimumValue" mask="256" name="MinimumValue" sname="MinimumValue" source="1" type="double" '
        'value="-1.0E+09"/>'
        '<Property ClassID="UGS::UICOMP_double" group="Block Specific::" hierarchy="UGS::UICOMP_double" '
        'id="Value" mask="256" name="Value" sname="Value" source="4" type="double" value="{val}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_double" id="Title" '
        'mask="256" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UIFW_unit_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_unit_options" id="ShowUnitLabel" mask="0" name="ShowUnitLabel" '
        'sname="ShowUnitLabel" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UIFW_unit_options" group="Block Specific::" '
        'hierarchy="UGS::UIFW_unit_options" id="AllowUnitEdit" mask="0" name="AllowUnitEdit" '
        'sname="AllowUnitEdit" source="1" type="logical" value="False"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), val=("%.4f" % float(value)).rstrip("0").rstrip(".") or "0")


def _blk_label(bid, text, wrap=True):
    return (
        '<Property class="UICOMP_label" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Label/Bitmap" type="uicomp">'
        '<item Expanded="1" class="UICOMP_label" hierarchy="" icon="styler_label.bmp" id="{id}" '
        'name="{id}" notes="" presentation="Label/Bitmap" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{text}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_label" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_label" group="Block Specific::" hierarchy="UGS::UICOMP_label" '
        'id="WordWrap" mask="16384" name="WordWrap" sname="WordWrap" source="1" type="logical" value="%s"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, text=_esc(text), wrap="True" if wrap else "False")


def _blk_button(bid, title):
    """Action Button 块(模板: ListPointProperties.dlx 的 UICOMP_button)。

    按钮激活经 BlockStyler 的 update 回调送达(block 即该按钮), 处理见
    StdParamsDialog.update_cb / ParamDialog.update_cb。
    """
    return (
        '<Property class="UICOMP_button" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Action Button" type="uicomp">'
        '<item Expanded="1" class="UICOMP_button" hierarchy="UGS::UI::Comp::SuperPoint" '
        'icon="styler_browser_pushbutton.bmp" id="{id}" name="{id}" notes="" '
        'presentation="Action Button" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_button" id="Expanded" '
        'mask="4" name="Expanded" sname="Expanded" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="Other::" hierarchy="UGS::UICOMP_button" id="UIOnly" '
        'mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="Other::" hierarchy="UGS::UICOMP_button" id="Translated" '
        'mask="16384" name="Translated" sname="Localize" source="1" type="logical" value="True"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title))


def _blk_filebrowser(bid, title, filt):
    return (
        '<Property class="UGS::UI::Comp::NativeFileBrowser" hierarchy="UGS::UICOMP_group" id="{id}" '
        'mask="256" name="{id}" presentation="File Selection with Browse" type="uicomp">'
        '<item Expanded="1" class="UGS::UI::Comp::NativeFileBrowser" hierarchy="" '
        'icon="report_in_folder.bmp" id="{id}" name="{id}" notes="" '
        'presentation="File Selection with Browse" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Title" mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UI::Comp::NativeFileBrowser" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileSystemBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="Path" mask="0" name="Path" sname="Path" '
        'source="3" type="string" value=""/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileSystemBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="RetainStringValue" mask="0" '
        'name="RetainStringValue" sname="RetainStringValue" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UI::Comp::NativeFileBrowser" group="Block Specific::" '
        'hierarchy="UGS::UI::Comp::NativeFileBrowser" id="Filter" mask="256" name="Filter" '
        'sname="Filter" source="2" type="string" value="{filt}"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), filt=_esc(filt))


def _blk_enum(bid, title, labels, selected=0):
    """下拉选择块; labels 为中文标签列表, 值由代码按序号映射。"""
    opts = "".join('<Option name="%s" value="%d"/>' % (_esc(t), i)
                   for i, t in enumerate(labels))
    return (
        '<Property class="UICOMP_enum" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Enumeration" type="uicomp">'
        '<item Expanded="1" SupportsDisablingLogic="1" class="UICOMP_enum" hierarchy="" '
        'icon="styler_optionmenu.bmp" id="{id}" name="{id}" notes="" '
        'presentation="Enumeration" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" '
        'value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Group" mask="16384" name="Group" sname="Group" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Expanded" mask="4" name="Expanded" sname="Expanded" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanFocus" mask="69636" name="CanFocus" sname="CanFocus" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanKeyboardFocus" mask="69636" name="CanKeyboardFocus" sname="CanKeyboardFocus" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="ReadWrite" mask="0" name="ReadWrite" sname="RetainValue" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="UIOnly" mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="Translated" mask="16384" name="Translated" sname="Localize" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="TitleVisibility" mask="16384" name="TitleVisibility" sname="LabelVisibility" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="PresentationStyle" mask="16384" '
        'name="PresentationStyle" sname="PresentationStyle" source="1" type="enum" '
        'selected="0">'
        '<Option name="Option Menu" value="0"/><Option name="Radio Box" value="1"/>'
        '<Option name="Pulldown" value="2"/></Property>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MaximumValue" mask="69636" name="MaximumValue" '
        'sname="MaximumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MinimumValue" mask="69636" name="MinimumValue" '
        'sname="MinimumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles" mask="69636" name="Titles" sname="Items" '
        'source="1" type="utfstrings"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Value" mask="69636" name="Value" '
        'sname="TEMPVALUE" source="1" type="integer" value="{sel}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Title" mask="257" name="Title" sname="Label" source="1" type="utfstring" '
        'value="{title}"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles_1" mask="256" name="Titles_1" '
        'selected="{sel}" sname="Value" source="4" type="enum">{opts}</Property>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), opts=opts, sel=int(selected))


def _blk_toggle(bid, label, value):
    """复选块(模板取自本机 CheckDeepHoles_Customization.dlx 的 SaveInPart)。"""
    return (
        '<Property class="UICOMP_toggle" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Toggle" type="uicomp">'
        '<item Expanded="1" SupportsDisablingLogic="1" class="UICOMP_toggle" hierarchy="" '
        'icon="styler_toggle.bmp" id="{id}" name="{id}" notes="" presentation="Toggle" '
        'type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" '
        'value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Group" mask="16384" name="Group" sname="Group" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Expanded" mask="4" name="Expanded" sname="Expanded" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="HideGroup" mask="69636" name="HideGroup" sname="HideGroup" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Focus" mask="69636" name="Focus" sname="Focus" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="CanFocus" mask="69636" name="CanFocus" sname="CanFocus" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="KeyboardFocus" mask="69636" name="KeyboardFocus" sname="KeyboardFocus" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="CanKeyboardFocus" mask="69636" name="CanKeyboardFocus" sname="CanKeyboardFocus" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="ReadWrite" mask="0" name="ReadWrite" sname="RetainValue" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="UIOnly" mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_toggle" '
        'id="Translated" mask="16384" name="Translated" sname="Localize" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="Icon" mask="128" name="Icon" sname="Bitmap" '
        'source="3" type="string" value=""/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="BitmapOnly" mask="16384" name="BitmapOnly" '
        'sname="BitmapOnly" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_toggle" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="{label}"/>'
        '<Property ClassID="UGS::UICOMP_toggle" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_toggle" id="Value" mask="256" name="Value" sname="Value" '
        'source="4" type="logical" value="{val}"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, label=_esc(label), val="True" if value else "False")


def build_selection_dlx(files, selected):
    """第一段"标准件选择"对话框: 每个件一个复选框。"""
    children = []
    if not files:
        children.append(_blk_label("sel_hint", "stdparts 目录为空。"))
    for i, f in enumerate(files):
        children.append(_blk_toggle("SEL%d" % i, f, f in selected))
    grp = _group_item("grp_sel", "勾选本次要加载的标准件（新件默认不勾）",
                      "".join(children), columns=1)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX StdPartSelect" type="uicomp" version="1.0.0">'
        + grp +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="标准件选择"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="选择本次要加载的标准件"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" '
        'name="NavigationStyle" selected="0" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )


def _group_item(gid, title, children_xml, columns=2, collapsed=False):
    return (
        '<item Expanded="{exp}" class="UGS::UICOMP_group" hierarchy="" id="{id}" name="{id}" notes="" '
        'presentation="Group" type="uicomp"><PropertyList>'
        '<Property class="UGS::UI::Comp::Container" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_group" id="Members" mask="0" name="Members" sname="Members" source="1" '
        'type="array"><PropertyList Expanded="1" class="UGS::UI::Comp::Container" '
        'hierarchy="UGS::UICOMP_group" id="ContainerItems" mode="1">{children}</PropertyList></Property>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Title" '
        'mask="1" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Group" '
        'mask="86020" name="Group" sname="Group" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Expanded" '
        'mask="0" name="Expanded" sname="Expanded" source="2" type="logical" value="{exp}"/>'
        '<Property ClassID="UGS::UICOMP_group" group="Block Specific::" hierarchy="UGS::UICOMP_group" '
        'id="Column" mask="16384" name="Column" sname="Column" source="1" type="integer" value="{col}"/>'
        '</PropertyList></item>'
    ).format(id=gid, title=_esc(title), children=children_xml, col=columns,
            exp=("False" if collapsed else "True"))


def _opt_index(opts, value):
    for i, (v, _t) in enumerate(opts):
        if v == value:
            return i
    return 0


def build_dlx(params=None, jrt=None, jt_mode=None):
    """从 LAYER_TABLE + JRT 参数生成窗口②完整 .dlx XML(UTF-8)。
    jt_mode 给定时在普通拉伸组顶部生成"JT 联动模式"下拉(v1.37)。

    (v1.35) 删除两段式时代的休眠"标准件组"生成——三段式改造后 main 恒以
    无标准件组调用本函数, 标准件参数页由 build_std_dlx(窗口③)负责。
    """
    if params is None:
        params = default_params()
    if jrt is None:
        jrt = dict(DEFAULT_JRT)

    zh = {r[0]: r[1] for r in LAYER_TABLE}

    # 文件组
    g_file = _group_item(
        "grp_file", "输入文件",
        _blk_filebrowser("dxf_file", "DXF 文件", "*.dxf") + _blk_label(
            "hint_label",
            "提示: 起始=结束=0 的图层跳过; LS/RZ/DK 拉伸后从 FLB 减去; "
            "曲线按图层导入到 NX 图层 %d~%d, 特征名前缀 CAD3D_。"
            % (MANAGED_MIN, MANAGED_MAX)),
        columns=1)

    # 参数组(每层两个 double 块: <code>_start / <code>_end)
    groups_xml = []
    for gid, title, codes in DIALOG_GROUPS:
        children = []
        if gid == "grp_plain" and jt_mode:
            children.append(_blk_enum(
                "jt_link", "JT 联动模式",
                [t for _v, t in JT_LINK_OPTS],
                _opt_index(JT_LINK_OPTS, jt_mode)))
        for code in codes:
            s, e = params.get(code, (0.0, 0.0))
            children.append(_blk_double(code + "_start", "%s %s 起始距离" % (code, zh[code]), s))
            children.append(_blk_double(code + "_end", "%s %s 结束距离" % (code, zh[code]), e))
        # v1.21: 单列布局——DialogSizing 无自适应项(实测仅 Allow Resize/
        # Follow Policy)且块模型无宽度属性, 双列行宽超默认窗口被裁;
        # 单列后行宽≈标签+单字段, 默认窗口完整显示。
        groups_xml.append(_group_item(gid, title, "".join(children), columns=1))

    # 加热条组(JRT; 起始==结束 即停用; 区间随 FLB 联动, 底侧自动镜像;
    # 颜色/透明度按期刊固定 186/78/50, 不进界面; 块 id 统一 "jrt_"+key)
    jrt_children = [
        _blk_double("jrt_" + key, label, jrt.get(key, DEFAULT_JRT[key]))
        for key, label in JRT_FIELDS
    ]
    jrt_children.append(_blk_button("jrt_reset", "恢复默认"))
    groups_xml.append(_group_item(
        "grp_jrt", "加热条 JRT（齐平板面/入侵深度/两端倒圆+圆顶；深度0停用）",
        "".join(jrt_children), columns=1))

    dlx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX FenCengLaShen" type="uicomp" version="1.0.0">'
        + g_file + "".join(groups_xml) +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="NX 分层拉伸 (DXF→3D)"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="设置各图层拉伸参数"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" name="NavigationStyle" '
        'selected="2" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )
    return dlx


def build_std_dlx(std_rules, params):
    """第三段"标准件参数"对话框: 每件一个可收起组(13 参数块 + Z 基准值标签)。"""
    groups_xml = []
    for i, fname in enumerate(sorted(std_rules)):
        r = std_rules[fname]
        p = "SP%d_" % i
        zval = _std_z(params, r)
        children = [
            _blk_label(p + "zval", "Z基准值: %.4g" % zval),
            _blk_enum(p + "layer", "定位图层",
                      [t for _v, t in LAYER_SEL_OPTS],
                      _opt_index(LAYER_SEL_OPTS, r["layer"])),
        ] + ([]
             if r["layer"] == "CXK" else
             [_blk_double(p + "rmin", "半径min", r["r_min"]),
              _blk_double(p + "rmax", "半径max", r["r_max"])]) + [
            _blk_enum(p + "zmode", "Z基准",
                      [t for _v, t in ZMODE_OPTS],
                      _opt_index(ZMODE_OPTS, r["z_mode"])),
            _blk_double(p + "offx", "X偏移", r["off_x"]),
            _blk_double(p + "offy", "Y偏移", r["off_y"]),
            _blk_double(p + "offz", "Z偏移", r["off_z"]),
            _blk_enum(p + "bool", "布尔",
                      [t for _v, t in BOOL_OPTS],
                      _opt_index(BOOL_OPTS, r["bool_mode"])),
            _blk_enum(p + "dir", "方向",
                      [t for _v, t in DIR_OPTS],
                      _opt_index(DIR_OPTS, r["dir"])),
        ]
        # v1.19: 每件都有恢复默认按钮(无内置默认的件=恢复通用安全默认:
        # 全部图层/全半径/FLB顶/仅放置/+Z/零偏移——压线板一案)
        children.append(_blk_button(p + "reset", "恢复默认"))
        groups_xml.append(_group_item("grp_" + p, fname, "".join(children),
                                      columns=1))   # v1.21 单列; 默认展开
    if not groups_xml:
        groups_xml.append(_group_item("grp_sp_empty", "无选中标准件",
                                      _blk_label("sp_empty_hint",
                                                 "本窗口无参数可设, 直接确定执行。"),
                                      columns=1))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX StdParams" type="uicomp" version="1.0.0">'
        + "".join(groups_xml) +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="标准件参数"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="每个标准件一个格子, 点标题展开/收起"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" '
        'name="NavigationStyle" selected="2" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    )


def _logs_dir():
    """运行生成物目录(dlx/日志/调试脚印), 与脚本同级的 logs 子目录。"""
    p = os.path.join(script_dir(), "logs")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        p = script_dir()
    return p


def _fresh_dlx_path(base_name, base_dir=None):
    """唯一 dlx 路径(毫秒戳; 写前清旧)。NX 的对话框记忆按 dlx 文件名
    存取并会在显示时回灌旧值(RetainValue=False 也拦不住, 实测)——
    固定名会让历史会话的错误显示值死灰复燃(v1.17 改回固定名后"标准件
    默认值又丢失错乱"即此); 每轮唯一名让记忆永远无载体。窗口宽度不靠
    文件名记忆(NX 不跨会话记尺寸, 固定名时代用户同样每轮要拉宽),
    由 dlx 内撑宽行直接做够。"""
    d = base_dir if base_dir is not None else _logs_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    try:
        for n in os.listdir(d):
            if n.endswith(".dlx") and n.startswith(base_name):
                try:
                    os.remove(os.path.join(d, n))
                except OSError:
                    pass
    except OSError:
        pass
    return os.path.join(d, "%s_%d.dlx"
                        % (base_name, int(time.time() * 1000) % 10 ** 10))


def _temp_dlx_path(base_name):
    """%TEMP% 回退路径也用唯一名——固定名会复活 v1.14/v1.17 已根治的
    "NX 按 dlx 文件名回灌旧会话值"事故(v1.35)。"""
    return _fresh_dlx_path(base_name, base_dir=os.environ.get("TEMP") or ".")


def write_std_dlx(std_rules, params):
    """生成第三段 .dlx 到脚本目录(唯一名), 失败回退 %TEMP%(同样唯一名)。"""
    xml = build_std_dlx(std_rules, params)
    candidates = [_fresh_dlx_path("nx_std_params"), _temp_dlx_path("nx_std_params")]
    for path in candidates:
        try:
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(xml)
            return path
        except IOError:
            continue
    return None


def write_dlx(params=None, jrt=None, jt_mode=None):
    """生成窗口② .dlx 到脚本目录(唯一名), 失败回退 %TEMP%(对应 dt:find-dcl 回退链)。"""
    xml = build_dlx(params, jrt, jt_mode)
    candidates = [_fresh_dlx_path("nx_extrude_runner"),
                  _temp_dlx_path("nx_extrude_runner")]
    for path in candidates:
        try:
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(xml)
            return path
        except IOError:
            continue
    return None


