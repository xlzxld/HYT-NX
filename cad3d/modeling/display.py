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

    三条路径逐级降级(2026-09-19 用户报 NX10 上仍选不中: StateCollection
    那套 GetStates/SetStates 接口在 NX2312 才有, 老版本整段被吞 → 补两条
    老版本就有的降级路径; 哪条走得通写进日志, 实机一眼可查):
      ① StateCollection 副本 + 一次 SetStates(NX2312 快路径, 不变);
      ② 逐层 LayerManager.GetState/SetState(逐层慢, 老版本兼容);
      ③ UF 兜底 uf.Layer.AskStatus/SetStatus(UF_LAYER API 最老版本就有;
         状态常量 UF_LAYER_SELECTABLE_LAYER=2 / VISIBLE=3 / WORK=1 /
         HIDDEN=4, 出自 NXOpen UF 头文件 uf_layer_types.h, 常量表取不到
         时按这套值兜底)。
    任一环节在某 NX 版本缺失都只跳过换下一条, 绝不影响模型正确性或中断
    流程(与 _refresh_display 同款兜底口径)。
    返回实际改动的图层数(0 = 没得改或所有路径都不支持)。
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
    changed = 0
    path = ""
    # ① StateCollection 副本路径(NX2312 快路径)
    coll = None
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
        path = "StateCollection"
    except Exception as ex:
        changed = 0
        coll = None
        if log is not None:
            log("  图层可选化: StateCollection 路径本版本不支持(%s), 走逐层降级。"
                % ex)
    finally:
        if coll is not None:
            try:
                coll.FreeResource()
            except Exception:
                pass
    # ② 逐层 GetState/SetState 路径
    if changed == 0:
        try:
            for _i in range(1, 257):
                try:
                    if lm.GetState(_i) == _NL.State.Visible:
                        lm.SetState(_i, _NL.State.Selectable)
                        changed += 1
                except Exception:
                    continue        # 单层读不到不影响其余层
            if changed:
                path = "逐层SetState"
        except Exception as ex:
            changed = 0
            if log is not None:
                log("  图层可选化: 逐层 GetState/SetState 也不支持(%s), 走 UF 兜底。"
                    % ex)
    # ③ UF 兜底(AskStatus/SetStatus, 老 NX 一定有)
    if changed == 0:
        try:
            import NXOpen.UF as _NUF
            _uf = _NUF.UFSession.GetUFSession()
            _ul = _uf.Layer
            _c_sel = getattr(_NUF.UFConstants, "UF_LAYER_SELECTABLE_LAYER", 2)
            _c_vis = getattr(_NUF.UFConstants, "UF_LAYER_VISIBLE_LAYER", 3)
            for _i in range(1, 257):
                try:
                    _st = _ul.AskStatus(_i)
                    if isinstance(_st, tuple):
                        _st = _st[0]
                    if int(_st) == _c_vis:
                        _ul.SetStatus(_i, _c_sel)
                        changed += 1
                except Exception:
                    continue        # work 层等改不动的跳过
            if changed:
                path = "UF SetStatus"
        except Exception as ex:
            changed = 0
            if log is not None:
                log("  图层可选化: UF 兜底也失败(%s) —— 本版本没法自动改图层"
                    "状态, 需要手工去 图层设置 里打开。" % ex)
    if changed and log is not None:
        log("  有 %d 个图层原来是“可见但不可选”, 已改成“可选”(%s路径) ——"
            "导入的 2D 图现在能直接选中了。" % (changed, path))
    return changed
