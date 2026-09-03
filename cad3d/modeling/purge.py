# -*- coding: utf-8 -*-
"""cad3d.modeling.purge —— 会话历史生成物清理与图层类别管理。"""

from cad3d.core.constants import (
    FEATURE_PREFIX, COMP_PREFIX, MANAGED_MIN, MANAGED_MAX
)
from cad3d.modeling.nx_compat import _iter, _is_marked, MARK_ATTR
from cad3d.geom.eval import dxf_fingerprints, _nx_curve_fp

_CREATED_FEATURES = []


def nx_purge(session, work_part, log, dxf_layers=None):
    """清理上一轮产物(只删自己的东西, 不碰用户图形):
    - 特征: CAD3D_ 前缀 + 本会话登记表(按所属部件过滤);
    - 已标记体: v1.9 移除参数后留下的哑体(特征已删, 按 CAD3D 属性标记
      识别; 特征删除时宿主体一并消失, 在特征/曲线/组件删除并更新后
      二次枚举, 只补删幸存的);
    - 组件: CAD3D_C_ 前缀实例;
    - 曲线: 带 CAD3D 标记属性的(任何图层); 11~70 内无标记的曲线与本次 DXF
      几何指纹比对 —— 重合=旧版(v1.2/v1.3)无标记产物, 删除重建;
      不重合=用户自有图形, 保留并警告。

    返回实际删除对象数(仅供诊断; 调用方目前忽略返回值)。
    """
    if session is None or work_part is None:
        return 0
    import NXOpen

    feats, curves, comps = [], [], []
    try:
        for f in _iter(work_part.Features):
            if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX):
                feats.append(f)
    except Exception as ex:
        log("【清理】特征枚举失败: %s" % ex)
    for f in list(_CREATED_FEATURES):               # 登记表双保险(仅本工作部件)
        try:
            if f not in feats and f.OwningPart == work_part:
                feats.append(f)
        except Exception:
            pass
    del _CREATED_FEATURES[:]
    try:                                            # 标准件组件实例
        root = work_part.ComponentAssembly.RootComponent
        if root is not None:                        # 纯部件(未成装配)时为 None
            for c in root.GetChildren():
                if str(getattr(c, "Name", "")).startswith(COMP_PREFIX):
                    comps.append(c)
    except Exception as ex:
        log("【清理】组件枚举失败: %s" % ex)

    # 曲线: 带标记的删; 范围内无标记的做指纹迁移匹配
    fps = dxf_fingerprints(dxf_layers)
    kept_warn = {}
    legacy = 0
    try:
        for c in _iter(work_part.Curves):
            try:
                lay = c.Layer
            except Exception:
                continue
            if _is_marked(c):
                curves.append(c)
            elif MANAGED_MAX >= lay >= MANAGED_MIN:
                fp = _nx_curve_fp(c)
                if fp is not None and fps.get(fp, 0) > 0:
                    fps[fp] -= 1                    # 旧版无标记产物 → 删除重建
                    curves.append(c)
                    legacy += 1
                else:
                    kept_warn[lay] = kept_warn.get(lay, 0) + 1
    except Exception as ex:
        log("【清理】曲线枚举失败: %s" % ex)

    if feats or curves or comps:
        try:
            session.UpdateManager.AddToDeleteList(feats + curves + comps)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "CAD3D 清理"))
        except Exception as ex:
            log("【清理】删除失败(可能有特征引用曲线): %s" % ex)
            return 0                    # 返回值=实际删除数, 未删成即 0

    # 已标记哑体: 特征删除后幸存的(移除参数轮产物), 二次枚举补删
    mbodies = []
    try:
        for b in _iter(work_part.Bodies):
            if _is_marked(b):
                mbodies.append(b)
    except Exception as ex:
        log("【清理】实体枚举失败: %s" % ex)
    if mbodies:
        try:
            session.UpdateManager.AddToDeleteList(mbodies)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "CAD3D 清理体"))
        except Exception as ex:
            log("【清理】已标记体删除失败: %s" % ex)
            return len(feats) + len(curves) + len(comps)   # 体未删掉
    log("【清理】已删除上一轮: 特征 %d 个, 实体 %d 个, 曲线 %d 条(含旧版无标记 %d), 组件 %d 个。"
        % (len(feats), len(mbodies), len(curves), legacy, len(comps)))
    if kept_warn:
        log("【清理】警告: 图层 %s 有 %d 条不属于本脚本的曲线, 已保留"
            "(脚本曲线将与其同层混放, 建议移到图层 1~%d 或 %d 以上)。"
            % (",".join(str(k) for k in sorted(kept_warn)),
               sum(kept_warn.values()), MANAGED_MIN - 1, MANAGED_MAX + 1))
    return len(feats) + len(curves) + len(comps) + len(mbodies)


clean_previous = nx_purge


def ensure_categories(work_part, layer_map, log):
    """为各导入图层建同名图层类别(便于用户在图层设置里按名开关)。"""
    cats = getattr(work_part, "LayerCategories", None)
    if cats is None:
        return
    for code, num in sorted(layer_map.items(), key=lambda kv: kv[1]):
        try:
            if cats.FindObject(code) is None:
                cats.CreateCategory(code, "%s (CAD3D)" % code, [num])
        except Exception:
            pass
