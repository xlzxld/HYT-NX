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


def print_guide(current=None, session=None):
    """打印三个脚本分别是干啥的; current 传本脚本文件名, 会加"← 本次"标记。

    ⚠️ session 一定要传: NX GUI 里播放日记时 **stdout 根本看不见**(没有控制台),
    只 print 等于没提示 —— 所以同样内容还要写进 NX 信息窗口(ListingWindow),
    那里才是用户看得见的地方(v3.2 用户反馈"中文提示没生效"后的修法)。
    """
    lines = ["【三个脚本分别是干啥的】"]
    for name, desc in GUIDE_LINES:
        mark = "  ← 本次运行" if current == name else ""
        lines.append("  %s — %s%s" % (name, desc, mark))
    for ln in lines:
        print(ln)
    if session is not None:
        try:
            session.ListingWindow.Open()
            for ln in lines:
                session.ListingWindow.WriteLine(ln)
        except Exception:
            pass
