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
