# -*- coding: utf-8 -*-
"""cad3d.pipeline.batch —— 自动化非交互批量执行与冒烟回归测试。"""

import io
import os

from cad3d.core.constants import FEATURE_PREFIX
from cad3d.core.config import SCHEMA_VERSION
from cad3d.core.paths import _logs_dir, resolve_dxf_path
from cad3d.core.logging import Log
from cad3d.core.state import (
    load_state, merge_params, merge_jrt
)
from cad3d.modeling.std_rules import merge_std_rules, sanitize_std_rule
from cad3d.modeling.nx_compat import _iter
from cad3d.modeling.std_rules import _rule_usable
from cad3d.modeling.display import _refresh_display
from cad3d.pipeline.runner import run_pipeline


def batch_run(dxf_arg=None, params_override=None, std_override=None,
              jrt_override=None, new_part_name=None):
    """run_journal 无 UI 直跑(冒烟): 新建部件 → 跑两遍(第二遍验证清理重建)。

    new_part_name 给定时无条件新建该名工作部件(批量测试确定性: 与标准件部件
    等会话内已有部件隔离, 避免 AddComponent 循环装配)。
    """
    import NXOpen
    session = NXOpen.Session.GetSession()
    if new_part_name:
        session.Parts.NewDisplay(new_part_name, NXOpen.Part.Units.Millimeters)
    elif session.Parts.Work is None:
        session.Parts.NewDisplay("cad3d_batch_test",
                                 NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    state = load_state()
    params = merge_params(state)
    if params_override:
        params.update(params_override)
    std_rules = merge_std_rules(state)
    if std_override:
        # std_override 全量接管: 批量冒烟只用显式给的规则(与 else 分支的
        # "记忆选中/可用规则"互斥)。逐条 sanitize —— 外部注入的是原始 dict,
        # 曾未经规范化直接进流程, 坏 r_max 等会在纯逻辑函数里炸 ValueError。
        # (原写法先 update 再过滤, 合并结果立即被丢弃, 等价于直接用 override)
        std_rules = {f: sanitize_std_rule(r) for f, r in std_override.items()}
    else:
        saved_sel = (state.get("selected")
                     if state.get("schema") == SCHEMA_VERSION else None)
        if saved_sel is not None and not isinstance(saved_sel, (list, tuple)):
            saved_sel = None
        if saved_sel is not None:
            keep = set(str(f) for f in saved_sel)
            std_rules = {f: r for f, r in std_rules.items() if f in keep}
        else:
            std_rules = {f: r for f, r in std_rules.items()
                         if _rule_usable(r)}
    jrt = merge_jrt(state)
    if jrt_override:
        jrt.update(jrt_override)
    dxf = dxf_arg or resolve_dxf_path(state)
    log = Log(session)
    log("【批量】图纸: %s" % dxf)
    # 配置提示由 run_pipeline 统一输出一次(曾在这里和 runner 里各打一遍)
    ok1, stats1 = run_pipeline(dxf, params, session=session, work_part=work_part,
                               log=log, std_rules=std_rules, jrt=jrt)
    ok2, stats2 = run_pipeline(dxf, params, session=session, work_part=work_part,
                               log=log, std_rules=std_rules, jrt=jrt)
    _refresh_display(session, work_part, log)
    feats = 0
    try:
        feats = len([f for f in _iter(work_part.Features)
                     if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX)])
    except Exception:
        pass
    log("【批量】连跑两遍: 第 1 遍=%s, 第 2 遍=%s, 特征 %d 个"
        % (ok1, ok2, feats))
    try:
        with io.open(os.path.join(_logs_dir(), "nx_extrude_report.txt"),
                     "w", encoding="utf-8") as f:
            f.write("\n".join(log.lines))
    except IOError:
        pass
    print("BATCH RESULT run1=%s run2=%s features=%d" % (ok1, ok2, feats))
