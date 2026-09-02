# -*- coding: utf-8 -*-
r"""batch_smoke.py —— CAD3D 端到端冒烟（免命令行版）。

用法：在 NX 里 菜单 工具 → 日记 → 播放，选本文件即可（和跑探针一模一样的操作）。
适用于 NX10 / NX12 / NX2312。它会：
  1) 新建一个独立工作部件；
  2) 拿一份真实测试 DXF 跑完整流水线两遍（第二遍专门验证"清理+重建"不残留/不报错）；
  3) 结束后控制台打印 `BATCH RESULT run1=True run2=True features=N`；
  4) 详细过程写到  <项目目录>\logs\nx_extrude_report.txt 。

跑完只要把那个 nx_extrude_report.txt（以及 NX 弹的任何红色报错/堆栈）发回来即可。

前置：NX 机器上要有**完整的一份项目文件夹**，包含
  nx_extrude_runner.py、nx_std_config.py、stdparts\ 、test\fixtures\3Dtest.dxf。
本文件放在项目根目录，和 nx_extrude_runner.py 同级。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import nx_extrude_runner as R   # noqa: E402

# 优先用真实夹具；不在就退回仓库自带的合成样例。
DXF = os.path.join(HERE, "test", "fixtures", "3Dtest.dxf")
if not os.path.isfile(DXF):
    alt = os.path.join(HERE, "test", "fixtures", "sample_layers.dxf")
    if os.path.isfile(alt):
        DXF = alt

print("=== CAD3D 端到端冒烟 ===")
print("runner v%s | python %s" % (R.SCRIPT_VERSION,
                                  sys.version.split()[0]))
print("dxf = %s  (存在: %s)" % (DXF, os.path.isfile(DXF)))
if not os.path.isfile(DXF):
    print("!! 没找到测试 DXF。请确认 test\\fixtures\\ 已随项目拷到本机；"
          "或在项目根跑 `python nx_extrude_runner.py --make-sample-dxf "
          "test\\fixtures\\sample_layers.dxf` 造一个。")
else:
    try:
        R.batch_run(DXF, new_part_name="CAD3D_SMOKE")
        print("报告: %s" % os.path.join(HERE, "logs", "nx_extrude_report.txt"))
    except Exception as ex:
        import traceback
        print("!! 冒烟抛异常: %s: %s" % (type(ex).__name__, ex))
        traceback.print_exc()
