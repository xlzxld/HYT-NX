# -*- coding: utf-8 -*-
"""
nx_stdparts.py —— 标准件放置(锚点收集/AddComponent/提升体/布尔)
========================================================================

拆分自 nx_extrude_runner.py(§5.5)。NXOpen 在函数内延迟 import。

依赖契约(由主脚本注入):
  共享对象: registry(特征登记表, 与 nx_nxcore 共享同一实例)
  常量: FEATURE_PREFIX COMP_PREFIX STD_MAX_ANCHORS
  nx_nxcore: _iter _bodies_of
  nx_rules: _rule_usable _unusable_names stdparts_dir anchors_overflow
            collect_circle_anchors _std_z _place_delta

机制定案(勿凭感觉改回): 放置后提升件内全部实体为工作部件独立体并删除装配
组件(v1.8); 布尔只减指定实体且刀具体保留(期刊 CopyTools); 逐工具容错(v1.9);
无 FLB 体可布尔或布尔未生效时保留独立体(v1.35)。
"""


def _matrix3x3(nx, flip):
    """放置姿态: 单位阵(+Z 插入) 或绕 X 180°(-Z 插入)。"""
    vals = ((1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0) if flip
            else (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    try:
        return nx.Matrix3x3(*vals)
    except TypeError:
        m = nx.Matrix3x3()
        for name, v in zip(("Xx", "Xy", "Xz", "Yx", "Yy", "Yz", "Zx", "Zy", "Zz"), vals):
            setattr(m, name, v)
        return m


# 放置/锚点/Z 基准纯逻辑(_place_delta/_center_seen/collect_circle_anchors/
# _std_z)已搬至 nx_rules.py, 由加载器再导出(同名可见, 调用方零改动)。


def _pick_target(flb_regions, cx, cy, log=None):
    """按锚点 XY 找包含它的 FLB 体。

    多个 FLB 体(多通道板)时必须命中包围盒; 一个都命中不了才兜底取第一个
    体——此时切错板的风险很高, 因此兜底一定要在日志里留痕(v1.29: 过去
    是静默兜底, 板外锚点会把孔切到别的板上且无任何提示)。
    """
    for body, b in flb_regions:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return body
    if not flb_regions:
        return None
    if log is not None:
        log("  警告: 锚点(%.3f,%.3f)不落在任何 FLB 体包围盒内, "
            "已兜底取第 1 个 FLB 体——请核对是否切错板。" % (cx, cy))
    return flb_regions[0][0]


def _promote_body(work_part, comp, feat_name, log, body_index=None):
    """组件实体 → 提升体(工作部件所有, 可直接作布尔工具)。

    body_index: None=全部实体(返回列表), 0/1=第几个实体(返回单体或 None)。
    v1.8: 逐实体容错——单个实体提升失败(如不在引用集)只跳过并记日志,
    不再让整件失败(主进胶 7 实体一案: 一个坏实体毁掉全部)。
    """
    import NXOpen.Features

    proto = comp.Prototype
    bodies = _iter(proto.Bodies)
    if not bodies:
        log("  提升失败: %s 内无实体。" % proto.Name)
        return None
    if body_index is not None:
        if body_index >= len(bodies):
            log("  提升失败: 件内只有 %d 个实体, 无第 %d 个。"
                % (len(bodies), body_index + 1))
            return None
        bodies = [bodies[body_index]]
    out = []
    for bd in bodies:
        try:
            occ = comp.FindOccurrence(bd)
            if occ is None:
                log("  提升跳过一个实体: 不在组件引用集内。")
                continue
            pb = work_part.Features.CreatePromotionBuilder(
                NXOpen.Features.Promotion.Null)
            try:
                pb.Associative = False
                pb.Body.Add(occ)
                feat = pb.CommitFeature()
            finally:
                try:
                    pb.Destroy()
                except Exception:
                    pass
            try:
                feat.SetName(feat_name if len(bodies) == 1
                             else "%s_%d" % (feat_name, len(out) + 1))
            except Exception:
                pass
            registry.add(feat)
            bs = _bodies_of(feat)
            if bs:
                out.append(bs[0])
        except Exception as ex:
            log("  提升实体失败(跳过该实体): %s" % ex)
            continue
    if body_index is not None:
        return out[0] if out else None
    return out


def _bool_one(work_part, fn, target, tool, retain_tools):
    """单工具布尔, 返回特征列表或 None(失败)。"""
    try:
        r = getattr(work_part.Features, fn)(target, False, [tool],
                                            retain_tools, False)
    except TypeError:
        try:
            r = getattr(work_part.Features, fn)(target, False, [tool],
                                                retain_tools, False, False, False)
        except Exception:
            return None
    except Exception:
        return None
    if isinstance(r, tuple):
        r = r[0]
    try:
        return [f for f in r]
    except TypeError:
        return [r]


def _bool_feature(work_part, op, target, tools, name, log, retain_tools=False):
    """布尔特征(CreateSubtractFeature/CreateUniteFeature)。

    retain_tools=True 保留工具体(切槽保件, 同期刊 CopyTools)。
    v1.9 逐工具容错: 多工具合并调用失败时逐个重试, 零相交的坏工具记日志
    跳过, 不再毁掉整次布尔(垫片第1实体零相交一案)。
    """
    fn = "CreateUniteFeature" if op == "unite" else "CreateSubtractFeature"
    tools = [t for t in tools if t is not None]
    if not tools:
        return []
    feats = None
    if len(tools) == 1:
        feats = _bool_one(work_part, fn, target, tools[0], retain_tools)
    else:
        # 多工具: 先合并试一次, 失败则逐个来
        try:
            r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                retain_tools, False)
            if isinstance(r, tuple):
                r = r[0]
            feats = list(r)
        except TypeError:
            try:
                r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                    retain_tools, False, False, False)
                if isinstance(r, tuple):
                    r = r[0]
                feats = list(r)
            except Exception:
                feats = None
        except Exception:
            feats = None
    if not feats:
        # 逐工具: 每个单独试, 失败(如零相交)跳过并记日志
        feats = []
        for t in tools:
            fs = _bool_one(work_part, fn, target, t, retain_tools)
            if fs:
                feats.extend(fs)
            else:
                log("  布尔工具跳过(与目标无交集或失败): %s"
                    % str(getattr(t, "Name", t)))
        if not feats:
            return []
    for i, f in enumerate(feats):
        try:
            f.SetName(name or ("%sBOOL_%d" % (FEATURE_PREFIX, i)))
        except Exception:
            pass
        registry.add(f)
    return feats


def _usable_parts(rules, log):
    """(v1.30) 过滤出已配置参考点的可用规则; 未配置的收集并写日志。"""
    unusable = _unusable_names(rules)
    usable = {f: r for f, r in rules.items() if _rule_usable(r)}
    if unusable:
        log("【标准件】提示: 以下标准件未在 nx_std_config.py 填写参考点"
            "(ref), 本次跳过: " + ", ".join(unusable)
            + "。请实测后在 config 精确文件名行中填写。")
    return usable, unusable


def place_std_parts(session, work_part, layers, flb_regions, params, std_rules, log,
                    stats=None):
    """阶段 6: 按规则放置 stdparts 标准件(独立体)并按需布尔。

    v1.8: 放置后提升件内全部实体为工作部件独立体并删除装配组件(与用户
    手工复制粘贴一致); 旋转件 XY 自动对轴; 布尔只减指定实体且刀具体保留。
    v1.9: 存活独立体登记进 stats["STD"]["bodies"](纯切割 SUBTRACT 模式
    体已删除, 不登记), 供阶段 8 移除参数统一收集。
    v1.30: 参考点=用户在 config 按文件名填写的 ref(必需;
    未填的件在 _usable_parts 过滤阶段已排除并提示)。
    """
    import NXOpen as nx
    import NXOpen.Features

    if stats is None:
        stats = {}
    std_stats = {"curves": 0, "profiles": 0, "features": 0,
                 "bodies": [], "note": ""}
    if not std_rules:
        stats["STD"] = std_stats
        return
    no_ref = []
    log("【标准件】开始: %d 个件规则。" % len(std_rules))
    ca = work_part.ComponentAssembly
    for fname in sorted(std_rules):
        rule = std_rules[fname]
        if not _rule_usable(rule):
            no_ref.append(fname)
            continue
        path = os.path.join(stdparts_dir(), fname)
        if not os.path.isfile(path):
            log("【标准件】%s: 文件缺失, 跳过。" % fname)
            continue
        if anchors_overflow([], rule):
            # 指纹护栏(空图层+半径上限≥999)先于收集——规则配错时不必先在
            # 数万实体上白白扫描一遍(v1.35)
            log("【标准件】%s: 规则指纹命中护栏(图层=%s 半径%.4g~%.4g, "
                "空图层+大半径=全图放置会卡死), 跳过。请到标准件参数页"
                "检查/恢复默认。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        anchors = collect_circle_anchors(layers, rule)
        if not anchors:
            log("【标准件】%s: 无匹配锚点(图层=%s 半径%.4g~%.4g), 跳过。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        if len(anchors) > STD_MAX_ANCHORS:
            log("【标准件】%s: 锚点 %d 个超过护栏 %d——规则疑似配错, "
                "跳过。请到标准件参数页检查/恢复默认。"
                % (fname, len(anchors), STD_MAX_ANCHORS))
            continue

        flip = (rule["dir"] == "-Z")
        z = _std_z(params, rule)
        stem = os.path.splitext(fname)[0]
        ref = rule.get("ref")
        ref_xy = (float(ref[0]), float(ref[1]))
        ref_z = float(ref[2])
        off = (float(rule.get("off_x", 0.0)), float(rule.get("off_y", 0.0)),
               float(rule.get("off_z", 0.0)))
        log("【标准件】%s: 参考点=配置值 XY=(%.3f,%.3f) Z=%.3f 偏移=(%.3f,%.3f,%.3f)"
            % (fname, ref_xy[0], ref_xy[1], ref_z, off[0], off[1], off[2]))
        n_ok = n_bool = n_body = 0
        for i, anch in enumerate(anchors):
            cx, cy = anch[0], anch[1]
            m3 = _matrix3x3(nx, flip)
            name = "%s%s_%d" % (COMP_PREFIX, stem, i + 1)
            try:
                # 放置公式: basePoint = 锚点 + _place_delta(锚点−R·ref+off;
                # -Z 时 ref 随姿态旋转, v1.35)
                dx, dy, dz = _place_delta((ref_xy[0], ref_xy[1], ref_z),
                                          flip, off)
                pos = nx.Point3d(cx + dx, cy + dy, z + dz)
                try:
                    comp, _ls = ca.AddComponent(path, "MODEL", name, pos, m3, -1)
                except TypeError:
                    comp = ca.AddComponent(path, "MODEL", name, pos, m3, -1, False)
                n_ok += 1
            except Exception as ex:
                log("  %s 位置 %d 放置失败: %s" % (fname, i + 1, ex))
                continue

            # 独立体: 提升件内全部实体 → 删除装配组件(与用户手工粘贴一致)
            tools_all = _promote_body(work_part, comp,
                                      "%sBODY_%s_%d" % (FEATURE_PREFIX, stem, i + 1),
                                      log, body_index=None)
            tools_all = [t for t in (tools_all or []) if t is not None]
            n_body += len(tools_all)
            try:
                session.UpdateManager.AddToDeleteList([comp])
                session.UpdateManager.DoUpdate(
                    session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删组件"))
            except Exception as ex:
                log("  %s 位置 %d 组件删除失败(提升体不受影响): %s"
                    % (fname, i + 1, ex))

            bm = rule["bool_mode"]
            if bm in ("SUBTRACT", "PLACE_SUBTRACT", "UNITE") and tools_all:
                # v1.9: 布尔实体字段已删——件内全部实体一起当刀具(用户确认;
                # 位置对了不会有什么影响, 逐工具容错兜底零相交实体)
                target = _pick_target(flb_regions, cx, cy, log=log)
                if target is None:
                    # 无 FLB 体可布尔: 独立体按放置保留——不能走 SUBTRACT 删体
                    # 分支(否则孔没切、件也没了, v1.35 修复)
                    log("  %s 位置 %d: 无 FLB 体可布尔, 独立体保留(按放置处理)。"
                        % (fname, i + 1))
                    std_stats["bodies"].extend(tools_all)
                else:
                    op = "unite" if bm == "UNITE" else "subtract"
                    fs = _bool_feature(work_part, op, target, tools_all,
                                       "%s%s_%s_%d" % (FEATURE_PREFIX,
                                                       "UNI" if op == "unite" else "SUB",
                                                       stem, i + 1), log,
                                       retain_tools=True)  # 刀具体保留(用户确认)
                    if fs:
                        n_bool += 1
                    if bm == "SUBTRACT":
                        if fs:
                            # 纯切割模式: 布尔已生效才删残留刀具体(孔已切出)
                            try:
                                session.UpdateManager.AddToDeleteList(tools_all)
                                session.UpdateManager.DoUpdate(
                                    session.SetUndoMark(
                                        nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删多余体"))
                            except Exception:
                                pass
                        else:
                            # 布尔未生效(无交集/失败): 保留独立体防凭空消失
                            log("  %s 位置 %d: 布尔未生效, 独立体保留。"
                                % (fname, i + 1))
                            std_stats["bodies"].extend(tools_all)
                    else:
                        std_stats["bodies"].extend(tools_all)
            elif tools_all:
                std_stats["bodies"].extend(tools_all)
        log("【标准件】%s: 放置 %d 处, 独立体 %d 个%s (Z=%.4g, %s)。"
            % (fname, n_ok, n_body,
               (", 布尔 %d 处" % n_bool) if n_bool else "",
               z, rule["bool_mode"]))
    std_stats["profiles"] = len(std_stats["bodies"])
    if no_ref:
        log("【标准件】提示: %d 件未配置参考点已跳过: %s"
            % (len(no_ref), ", ".join(no_ref)))
    stats["STD"] = std_stats
