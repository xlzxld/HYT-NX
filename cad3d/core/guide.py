# -*- coding: utf-8 -*-
"""cad3d.core.guide —— 三个主入口的大白话中文说明(启动时打印, 帮用户分清该播哪个脚本)。

三个 runner 共用同一份文案, 只改这里即可全局同步(v2.13)。
"""

# (脚本文件名, 大白话一句话) —— 顺序 = 推荐的使用顺序
GUIDE_LINES = (
    ("nx_extrude_runner.py", "建模: 选图纸、定各层高度、放标准件、建分流板模型, 从图纸到 3D 一条龙"),
    ("nx_std_replace_runner.py", "换件: 把模型里已经放好的标准件换成别的规格, 没点名替换的一律不动"),
    ("nx_mold_cut_runner.py", "开框: 按分流板/加热条/标准件的位置, 给模具自动挖孔让位, 不做建模"),
)


def print_guide(current=None, session=None, ui=None):
    """提示本脚本是干啥的。

    - 控制台: 打印三个脚本的完整清单(命令行 / run_journal 场景看得见);
    - ui: 弹一个**小**提示窗, **只说本脚本**的那一句 —— 用户 2026-09-18 定案:
      "只要弹出一个小窗口即可, 现在的太大了, 哪个脚本就写哪个脚本的提示,
      不要一股脑全写上"。
    - session: 只在**没有 ui** 时兜底写 NX 信息窗口(stdout 在 NX GUI 里看不见);
      有弹窗就不往信息窗口灌那三行了(嫌大)。
    """
    lines = ["【三个脚本分别是干啥的】"]
    for name, desc in GUIDE_LINES:
        mark = "  ← 本次运行" if current == name else ""
        lines.append("  %s — %s%s" % (name, desc, mark))
    for ln in lines:
        print(ln)
    if ui is not None:
        show_guide(ui, current)
    elif session is not None:
        try:
            session.ListingWindow.Open()
            for ln in lines:
                session.ListingWindow.WriteLine(ln)
        except Exception:
            pass


def show_guide(ui, current):
    """弹小提示窗: 只说 current 这个脚本是干啥的(一行, 不列其他脚本)。"""
    for name, desc in GUIDE_LINES:
        if name != current:
            continue
        try:
            import NXOpen
            ui.NXMessageBox.Show("CAD3D · 本脚本",
                                 NXOpen.NXMessageBox.DialogType.Information,
                                 "%s\n\n%s" % (name, desc))
        except Exception:
            pass
        return
