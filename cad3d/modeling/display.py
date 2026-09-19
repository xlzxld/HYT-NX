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
    """把图层补成“可选”, 让导入的 2D 参考图能直接选中。

    背景(2026-09-18 用户报): 导入的 2D 图“能显示但选不中”, 要手工去图层设置里
    逐个打开。根因是 _refresh_display 的 (a) 步只设了“视图中的可见性”
    (view-based), 图层自身的全局状态没动。

    (2026-09-19 NX10 实机取证升级): 探针盘点 256 层 = work 1 + 可选 5 +
    **隐藏 250**, “可见不可选”为 0 —— 曲线导在 101~122 层、状态是“隐藏”,
    (a) 步把视图可见性强制打开所以**看得到**, 但隐藏层的对象**天然选不中**。
    因此本函数做两种转换: 可见(3)→可选(2) **和 隐藏(4)→可选(2)**, 等价于
    手工“图层全开”的后半步 —— 画面不会多出东西((a) 步早已把显示全开了),
    只是看得到的都变得能选。工作层(1)一律不碰。

    NX 图层状态 4 种(NX2312 官方文档 NXOpen.Layer.State):
      WorkLayer  = 工作层(新建对象落这)   Selectable = 可选
      Visible    = 可见但不可选           Hidden     = 不可见不可选

    三条路径逐级降级(哪条走得通写进日志, 实机一眼可查):
      ① StateCollection 副本 + 一次 SetStates(NX2312 快路径);
      ② 逐层 LayerManager.GetState/SetState(逐层慢, 老版本兼容);
      ③ UF 兜底 uf.Layer.AskStatus/SetStatus(UF_LAYER API 最老版本就有;
         状态常量 UF_LAYER_SELECTABLE_LAYER=2 / VISIBLE=3 / HIDDEN=4 /
         WORK=1, 出自 NXOpen UF 头文件 uf_layer_types.h, 常量表取不到
         时按这套值兜底; NX10 实测 AskStatus(1)=1 与此编号吻合)。
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
                _st = coll.GetState(_i)
                if _st in (_NL.State.Visible, _NL.State.Hidden):
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
                    _st = lm.GetState(_i)
                    if _st in (_NL.State.Visible, _NL.State.Hidden):
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
            # UFConstants 缺常量时按 uf_layer_types.h 值兜底(work=1,
            # selectable=2, visible=3, hidden=4); NX10 实测 AskStatus(1)=1
            # (工作层)与此编号吻合(2026-09-19 探针)。
            _c_sel = getattr(_NUF.UFConstants, "UF_LAYER_SELECTABLE_LAYER", 2)
            _c_vis = getattr(_NUF.UFConstants, "UF_LAYER_VISIBLE_LAYER", 3)
            _c_hid = getattr(_NUF.UFConstants, "UF_LAYER_HIDDEN_LAYER", 4)
            n_ask = n_vis = n_set = 0
            _sample = None
            for _i in range(1, 257):
                try:
                    _st = _ul.AskStatus(_i)
                    if isinstance(_st, tuple):
                        _st = _st[0]
                    _st = int(_st)
                    n_ask += 1
                    if _sample is None:
                        _sample = (_i, _st)
                    if _st in (_c_vis, _c_hid):
                        n_vis += 1
                        _ul.SetStatus(_i, _c_sel)
                        n_set += 1
                except Exception:
                    continue        # work 层等改不动的跳过
            if n_set:
                changed = n_set
                path = "UF SetStatus"
            elif log is not None:
                # 0 改动不再静默: 写清读到什么、改了几层, 下一轮实机一眼定位
                log("  图层可选化 UF 兜底读完: 能读状态 %d 层, 其中“可见/隐藏"
                    "待改”%d 层, 改成可选成功 %d 层%s。0 改动 = 图层状态号或 "
                    "SetStatus 与预期不符, 请把日志发回。"
                    % (n_ask, n_vis, n_set,
                       ("; 状态样例: 第%d层=%d" % _sample) if _sample else ""))
        except Exception as ex:
            changed = 0
            if log is not None:
                log("  图层可选化: UF 兜底也失败(%s) —— 本版本没法自动改图层"
                    "状态, 需要手工去 图层设置 里打开。" % ex)
    if changed and log is not None:
        log("  有 %d 个图层原来是“可见/隐藏但不可选”, 已全部改成“可选”"
            "(%s路径, 等价手工图层全开) —— 导入的 2D 图现在能直接选中了。"
            % (changed, path))
    return changed
