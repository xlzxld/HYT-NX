# -*- coding: utf-8 -*-
"""
nx_probe_len.py —— NX10 取证探针: 热咀长度对齐链路逐项 API 探测 (只读不改模型)
=============================================================================
背景: 替换热咀的"移面对齐长度"(v3.4/v3.5)在 NX2312 实机验证通过, NX10 上
不生效(替换后热咀保持统一原长)。断在哪一环没有实机证据 —— 本探针在 NX10
里把链路用到的每个 API 逐项探一遍, 结果写 logs/probe_len_out.txt。

播放方式: NX 菜单 工具 → 日记 → 播放, 选本文件。
安全: 只读探测 + "建了即毁"的 builder 试探(不 Commit, 不碰任何体), 模型零改动。
判读: 输出里每项标 OK / 缺失 / 异常; 哪一项不是 OK, 长度对齐就断在哪 ——
      把本文件和 logs/std_replace_report.txt 一起发回来即可定修法。
"""
import io
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

out = []


def say(msg):
    out.append(str(msg))
    print(msg)


def probe(label, fn):
    """跑一项探测: fn() 返回描述串; 抛异常按"缺失/异常"记录, 不中断。"""
    try:
        r = fn()
        say("  [%s] %s" % (label, r if r else "OK"))
        return True
    except Exception as ex:
        say("  [%s] 缺失或异常: %r" % (label, ex))
        return False


def main():
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    wp = session.Parts.Work

    # ── 0. 版本与部件 ────────────────────────────────────────────────
    say("=== NX10 长度对齐链路探针 ===")
    try:
        say("NX 版本: %s" % session.GetEnvironmentVariableValue("UGII_VERSION"))
    except Exception as ex:
        say("NX 版本: 读不到(%r)" % ex)
    say("工作部件: %s" % (wp.Name if wp is not None else "(无 —— 只探 API, 不碰模型)"))
    say("")

    # ── 1. 图层"可选"化三条路径(display._selectable_all_layers 用) ────
    say("[1] 图层状态接口")
    if wp is not None:
        lm = wp.Layers
        try:
            coll = lm.GetStates()
            probe("Layers.GetStates", lambda: "OK(返回 %s)" % type(coll).__name__)
        except Exception as ex:
            say("  [Layers.GetStates] 缺失或异常: %r" % ex)
        else:
            try:
                coll.FreeResource()
            except Exception:
                pass
        probe("Layers.GetState(2)", lambda: str(lm.GetState(2)))
        try:
            import NXOpen.Layer as NL
            say("  [Layer.State 枚举] Visible=%s Selectable=%s"
                % (int(NL.State.Visible), int(NL.State.Selectable)))
        except Exception as ex:
            say("  [Layer.State 枚举] 缺失或异常: %r" % ex)
    else:
        say("  (无工作部件, 跳过需部件的项)")
    try:
        _uc = NXOpen.UF.UFConstants
        say("  [UFConstants] SELECTABLE=%s VISIBLE=%s (应为 2/3, uf_layer_types.h)"
            % (_uc.UF_LAYER_SELECTABLE_LAYER, _uc.UF_LAYER_VISIBLE_LAYER))
    except Exception as ex:
        say("  [UFConstants] 缺失或异常: %r" % ex)
    probe("uf.Layer.AskStatus(1)", lambda: "work 层状态=%s" % (uf.Layer.AskStatus(1),))
    say("")

    # ── 2. 移面(同步建模「移动面」)链路 ──────────────────────────────
    say("[2] 移面链路(nozzle_len._move_faces_z)")
    feats = wp.Features if wp is not None else None
    makers = {}
    if feats is not None:
        for name in sorted(dir(feats)):
            if name.startswith("Create") and "MoveFace" in name:
                makers[name] = getattr(feats, name)
        say("  [Create*MoveFace* 清单] %s" % (", ".join(sorted(makers)) or "一个都没有"))
    else:
        say("  (无工作部件, 跳过)")
    bld = None

    def _mk():
        null_tok = NXOpen.Features.AdmMoveFace.Null
        b = makers["CreateAdmMoveFaceBuilder"](null_tok) \
            if "CreateAdmMoveFaceBuilder" in makers \
            else makers["CreateMoveFaceBuilder"](NXOpen.Features.MoveFace.Null)
        return b

    def _motion():
        bld.Motion.Option = NXOpen.GeometricUtilities.ModlMotion.Options.DeltaXyz
        bld.Motion.DeltaEnum = \
            NXOpen.GeometricUtilities.ModlMotion.Delta.ReferenceAcsWorkPart
        bld.Motion.DeltaXc.SetFormula("0")
        bld.Motion.DeltaZc.SetFormula("1.0")
        return "Motion=DeltaXyz 可设"

    def _facerules():
        _sc = wp.ScRuleFactory
        say("  [ScRuleFactory] %s" % type(_sc).__name__)
        return "存在(CreateRuleFaceDumb 能否建待实弹验证)"

    def _facetoggles():
        n = 0
        for attr in ("RelationScope", "CloneScope", "UseFindClone",
                     "CoplanarEnabled", "CoaxialEnabled", "TangentEnabled",
                     "RigidBodyFaceEnabled"):
            if hasattr(bld.FaceToMove, attr):
                n += 1
        return "FaceToMove 7 个开关里 %d 个可寻址" % n

    def _onapplypre():
        return "OK" if hasattr(bld, "OnApplyPre") else "无 OnApplyPre"

    if feats is not None and makers:
        try:
            bld = _mk()
            probe("Create*MoveFaceBuilder(建+毁, 不 Commit)", lambda: "建成")
            probe("Motion.DeltaXyz", _motion)
            probe("ScRuleFactory", _facerules)
            probe("FaceToMove 开关", _facetoggles)
            probe("OnApplyPre", _onapplypre)
        except Exception as ex:
            say("  [移面 builder] 建不出来: %r" % ex)
        finally:
            if bld is not None:
                try:
                    bld.Destroy()
                except Exception:
                    pass
    say("")

    # ── 3. 去参数 + 定位点回位(点对点移动对象)链路 ──────────────────
    say("[3] 去参与点对点回位(nozzle_len._deparameterize_bodies /"
        " _move_bodies_point_to_point)")
    if feats is not None:
        probe("Features.CreateRemoveParametersBuilder",
              lambda: "OK" if hasattr(feats, "CreateRemoveParametersBuilder")
              else "缺失")
    probe("BaseFeatures.CreateMoveObjectBuilder",
          lambda: "OK" if (wp is not None and
                           hasattr(wp.BaseFeatures, "CreateMoveObjectBuilder"))
          else "缺失")
    probe("ModlMotion.Options.PointToPoint",
          lambda: str(NXOpen.GeometricUtilities.ModlMotion.Options.PointToPoint))
    probe("Points.CreatePoint",
          lambda: "OK" if (wp is not None and hasattr(wp.Points, "CreatePoint"))
          else "缺失")
    mo = None
    if wp is not None and hasattr(wp.BaseFeatures, "CreateMoveObjectBuilder"):
        try:
            mo = wp.BaseFeatures.CreateMoveObjectBuilder(
                NXOpen.Features.MoveObject.Null)
            probe("MoveObjectBuilder.TransformMotion",
                  lambda: "OK" if hasattr(mo, "TransformMotion") else "缺失")
            probe("ObjectToMoveObject",
                  lambda: "OK" if hasattr(mo, "ObjectToMoveObject") else "缺失")

            def _p2p():
                t = mo.TransformMotion
                t.Option = NXOpen.GeometricUtilities.ModlMotion.Options.PointToPoint
                t.DeltaEnum = \
                    NXOpen.GeometricUtilities.ModlMotion.Delta.ReferenceAcsWorkPart
                return "PointToPoint 可设"

            probe("TransformMotion 点对点设置", _p2p)
        except Exception as ex:
            say("  [移动对象 builder] 建不出来: %r" % ex)
        finally:
            if mo is not None:
                try:
                    mo.Destroy()
                except Exception:
                    pass
    say("")

    # ── 4. 量长口径依赖(纯读) ────────────────────────────────────────
    say("[4] 量长依赖(UF 面数据/包围盒, 纯读)")
    probe("UFSession 面数据(uf.Modl)", lambda: "OK" if hasattr(uf, "Modl") else "缺失")

    say("")
    say("=== 探针结束(模型零改动)。把本文件连同 logs/std_replace_report.txt"
        "一起发回。 ===")

    # 落盘 logs/probe_len_out.txt(与 diag_len 同惯例, UTF-8)
    logs = os.path.join(_ROOT, "logs")
    if not os.path.isdir(logs):
        os.makedirs(logs)
    p = os.path.join(logs, "probe_len_out.txt")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("probe -> %s" % p)


main()
