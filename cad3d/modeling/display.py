# -*- coding: utf-8 -*-
"""cad3d.modeling.display —— 视图与图形全量强制重绘刷新。"""


def _refresh_display(session, work_part, log=None):
    """末帧强制刷新图形显示: 复刻用户手工"图层全开 + 全部隐藏再显示 + 重建"。

    无界面/批量后新加体·组件·曲线常不自动重绘(旧版尤甚), 数据是对的, 只是视图
    没刷。交互与 batch 两条路径末尾都调它。纯显示、每步 try 兜底, 任一 API 在
    某版本缺失都跳过, 绝不影响模型正确性或中断流程。"""
    if session is None or work_part is None:
        return
    # a) 全部图层置可见(view-based, NX 老版本即有):
    try:
        import NXOpen.Layer as _NL
        _view = work_part.ModelingViews.WorkView
        _states = [_NL.StateInfo(_i, _NL.State.Visible) for _i in range(1, 257)]
        work_part.Layers.SetObjectsVisibilityOnLayer(_view, _states, True)
    except Exception:
        pass
    # a2) 上面只开了"视图里看不看得见", 图层全局状态没动 —— 全局状态是
    #     "可见但不可选"时对象仍选不中(导入的 2D 参考图最常见), 补成"可选"。
    _selectable_all_layers(work_part, log)
    # b) 逐个体/曲线 Unblank + RedisplayObject(等价"全部隐藏再显示"):
    for _coll in (getattr(work_part, "Bodies", None),
                  getattr(work_part, "Curves", None)):
        if _coll is None:
            continue
        try:
            _objs = list(_coll)
        except Exception:
            _objs = []
        for _o in _objs:
            for _m in ("Unblank", "RedisplayObject"):
                try:
                    getattr(_o, _m)()
                except Exception:
                    pass
    # c) 全量重建:
    for _inv in ("DoRebuilds", "DoUpdateAll"):
        try:
            getattr(session.UpdateManager, _inv)()
            break
        except Exception:
            pass


def _selectable_all_layers(work_part, log=None):
    """把“可见但不可选”的图层补成“可选”, 让导入的 2D 参考图能直接选中。

    背景(2026-09-18 用户报): 导入的 2D 图“能显示但选不中”, 要手工去图层设置里
    逐个打开。根因是 _refresh_display 的 (a) 步只设了“视图中的可见性”
    (view-based), 图层自身的全局状态没动 —— 状态停在“可见但不可选”时, 看得见
    也点不上。

    NX 图层状态只有 4 种(NX2312 官方文档 NXOpen.Layer.State):
      WorkLayer  = 工作层(新建对象落这)   Selectable = 可选
      Visible    = 可见但不可选           Hidden     = 不可见不可选
    本函数只做 Visible → Selectable 这一种转换:
      · 可见的保持可见、视图里不会多出东西, 只是变得能选中;
      · Hidden(用户有意隐藏的)与 WorkLayer(工作层)一律不碰。
    改状态走 StateCollection 副本 + 一次 SetStates 应用, 比逐层 SetState 快
    (后者每层都可能触发一次更新)。任一环节在某 NX 版本缺失都只跳过, 绝不影响
    模型正确性或中断流程(与 _refresh_display 同款兜底口径)。
    返回实际改动的图层数(0 = 没得改或本版本不支持)。
    """
    if work_part is None:
        return 0
    try:
        import NXOpen.Layer as _NL
    except Exception:
        return 0
    lm = getattr(work_part, "Layers", None)
    if lm is None:
        return 0
    coll = None
    changed = 0
    try:
        coll = lm.GetStates()
        for _i in range(1, 257):
            try:
                if coll.GetState(_i) == _NL.State.Visible:
                    coll.SetState(_i, _NL.State.Selectable)
                    changed += 1
            except Exception:
                continue            # 单层读不到(空层/越界)不影响其余层
        if changed:
            try:
                lm.SetStates(coll)
            except TypeError:
                lm.SetStates(coll, True)
    except Exception as ex:
        if log is not None:
            log("  图层“可选”化跳过(本 NX 无此接口或不允许): %s" % ex)
        return 0
    finally:
        if coll is not None:
            try:
                coll.FreeResource()
            except Exception:
                pass
    if changed and log is not None:
        log("  有 %d 个图层原来是“可见但不可选”, 已改成“可选”——"
            "导入的 2D 图现在能直接选中了。" % changed)
    return changed
