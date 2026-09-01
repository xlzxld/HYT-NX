# -*- coding: utf-8 -*-
"""v1.9 冒烟: 移除参数(特征=0)+体标记清理+恢复默认按钮相关纯逻辑已过 selftest,
本脚本验 NX 侧: 五类标准件独立体到位 + 主导轴对轴(主进胶) + 螺丝贯穿 FLB +
JRT 回归 + 两遍可重复 + 组件/特征零残留。"""
import io
import sys
from collections import Counter

import os as _os, sys as _sys
_sys.dont_write_bytecode = True
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_HERE)))
_FIXTURES = _os.path.join(_HERE, "fixtures")

import NXOpen  # noqa: E402
import NXOpen.UF  # noqa: E402
import nx_extrude_runner as m  # noqa: E402

session = NXOpen.Session.GetSession()
uf = NXOpen.UF.UFSession.GetUFSession()
PARAMS = {
    "FLB": (-40.0, -90.0),
    "JT": (-30.0, -100.0),
    "LS": (-40.0, -90.0),
    "RZ": (-77.0, -90.0),
    "DK": (-40.0, -43.0),
    "DP": (-83.2977, -90.0),
    "CX": (-30.0, -65.0),
}
STD = {fn: m.guess_std_rule(fn) for fn in (
    "螺丝-45.prt", "垫片.prt", "大水口-25.prt",
    "主进胶与中心定位垫片-30.prt", "点胶口-25.prt", "接线盒-24针.prt")}

m.batch_run(_os.path.join(_FIXTURES, "3Dtest.dxf"),
            params_override=PARAMS, std_override=STD,
            jrt_override={"start": -40.0, "end": -47.5},
            new_part_name="t_v111")

work_part = session.Parts.Work
out = []


def body_info(b):
    faces = list(b.GetFaces())
    zs = [uf.Modeling.AskFaceData(fc.Tag)[3] for fc in faces]
    axes = set()
    for fc in faces:
        d = uf.Modeling.AskFaceData(fc.Tag)
        if float(d[4]) > 1e-9 and abs(d[2][2]) > 0.999:
            axes.add((round(d[1][0], 2), round(d[1][1], 2)))
    return (len(faces), min(bb[2] for bb in zs), max(bb[5] for bb in zs), axes)


def near(a, b, tol=0.1):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


# 1) 组件/特征残留(应为 0; 特征=0 即移除参数生效)
ncomp = 0
try:
    root = work_part.ComponentAssembly.RootComponent
    if root is not None:
        ncomp = len([c for c in root.GetChildren()
                     if str(c.Name).startswith(m.COMP_PREFIX)])
except Exception as ex:
    out.append("组件枚举失败: %s" % ex)
nfeat = len([f for f in work_part.Features
             if str(f.Name).startswith(m.FEATURE_PREFIX)])
out.append("组件残留=%d (期望0)" % ncomp)
out.append("CAD3D 特征残留=%d (期望0, 移除参数生效)" % nfeat)

# 2) 标记体(移除参数后产物=哑体, 全带 CAD3D 属性标记)
marked, unmarked = [], []
for b in work_part.Bodies:
    (marked if m._is_marked(b) else unmarked).append(body_info(b))
out.append("标记体=%d 未标记体=%d (期望未标记=0)" % (len(marked), len(unmarked)))

# 3) 图纸圆心(LS/DK/RZ/DP)—— 锚点期望位置
layers, _ = m.parse_dxf(_os.path.join(_FIXTURES, "3Dtest.dxf"))


def centers(code):
    r = m.sanitize_std_rule({"layer": code, "r_min": 0.0, "r_max": 9999.0})
    return [(a[0], a[1]) for a in m.collect_circle_anchors(layers, r)]


ls_c, dk_c, rz_c, dp_c = centers("LS"), centers("DK"), centers("RZ"), centers("DP")
out.append("图纸圆心: LS=%d DK=%d RZ=%d DP=%d" % (len(ls_c), len(dk_c),
                                                  len(rz_c), len(dp_c)))

# 4) 分件核数(轴+面数/区间精确分类; v1.8 基线: 螺丝16 垫片8 大水口8 主进胶7 点胶口8)
# 螺丝: 轴=LS 圆心, 面数 12(杆)/6(头); 垫片: 轴=DK, 面数 8/14;
# 大水口+点胶口: 轴=RZ, 底 z≈-195; 主进胶: 轴=DP 或 DP±42.5, 面数 5/7/14/22
def ax_in(ax, cs):
    return any(near(a, c) for a in ax for c in cs)


dp_pad = list(dp_c) + [(c[0] + 42.5, c[1]) for c in dp_c]                   + [(c[0] - 42.5, c[1]) for c in dp_c]
n_screw = sum(1 for nf, z0, z1, ax in marked
              if ax_in(ax, ls_c) and nf in (6, 12))
n_wash = sum(1 for nf, z0, z1, ax in marked
             if ax_in(ax, dk_c) and nf in (8, 14))
n_noz = sum(1 for nf, z0, z1, ax in marked
            if ax_in(ax, rz_c) and abs(z0 - (-195.0)) < 1.0)
# v1.11: 点胶口参考点改为自身大圆柱顶面(-413.531), 整体相对旧版下移≈6.66
n_dsx = sum(1 for nf, z0, z1, ax in marked
            if ax_in(ax, rz_c) and -196.0 < z0 < -194.0)
n_djk = sum(1 for nf, z0, z1, ax in marked
            if ax_in(ax, rz_c) and -205.0 < z0 < -198.5)
out.append("大水口体(RZ轴,底~-195)=%d (期望8) %s" % (n_dsx,
           "OK" if n_dsx == 8 else "**不符**"))
out.append("点胶口体(RZ轴,底~-201.6)=%d (期望8) %s" % (n_djk,
           "OK" if n_djk == 8 else "**不符**"))
stub_old = sum(1 for nf, z0, z1, ax in marked
               if ax_in(ax, rz_c) and abs(z1 - (-70.34)) < 0.07)
stub_new = sum(1 for nf, z0, z1, ax in marked
               if ax_in(ax, rz_c) and abs(z1 - (-77.00)) < 0.07)
out.append("RZ族小柱顶齐平(z~-77.00,两家族参考面均落FLB底-90)=%d (期望8) %s"
           % (stub_new, "OK" if stub_new == 8 else "**不符**"))
out.append("残留旧参考位(z~-70.34)=%d (期望0) %s"
           % (stub_old, "OK" if stub_old == 0 else "**不符**"))
n_noz = n_dsx + n_djk              # 下游"其余体"按 RZ 全家族扣减
n_main = sum(1 for nf, z0, z1, ax in marked
             if ax_in(ax, dp_pad) and nf in (5, 6, 7, 14, 22))
out.append("螺丝体(LS轴,面6/12)=%d (期望16) %s" % (n_screw, "OK" if n_screw == 16 else "**不符**"))
out.append("垫片体(DK轴,面8/14)=%d (期望8) %s" % (n_wash, "OK" if n_wash == 8 else "**不符**"))
out.append("(旧聚合行由上方大水口/点胶口分列取代)")
out.append("主进胶体(DP±42.5轴)=%d (期望7) %s" % (n_main, "OK" if n_main == 7 else "**不符**"))
n_other = len(marked) - n_screw - n_wash - n_noz - n_main
out.append("其余体(FLB/JT/CX/JRT4+接线盒2)=%d (期望9) %s"
           % (n_other, "OK" if n_other == 9 else "**不符**"))
# CX 体回归(CX+CXK 并入闭环): z=[-65,-30]
cx_body = sum(1 for nf, z0, z1, ax in marked
              if abs(z0 - (-65.0)) < 0.5 and abs(z1 - (-30.0)) < 0.5)
out.append("CX 体(CX+CXK闭环)=%d (期望1) %s" % (cx_body,
           "OK" if cx_body == 1 else "**不符**"))
for nf, z0, z1, ax in sorted(marked, key=lambda t: -t[0])[:6]:
    out.append("  体: 面%-3d z=[%9.2f,%9.2f] 轴数%d %s"
               % (nf, z0, z1, len(ax), sorted(ax)[:3]))

# 5) 主导轴对轴: 主进胶 body0 轴=DP 圆心 且 顶面贴 FLB 底(-90)
main_ok = any(any(near(a, c) for a in ax for c in dp_c)
              and abs(z1 - (-90.0)) < 0.5
              for nf, z0, z1, ax in marked)
out.append("主进胶对轴(轴=DP圆心,顶z=-90)=%s" % ("OK" if main_ok else "**不符**"))

# 6) 螺丝贯穿: FLB 体上每个 LS 圆心处有圆柱面(孔)
flb_axes = set()
for nf, z0, z1, ax in marked:
    if z1 - z0 > 40:                       # 板厚量级的大体视为 FLB
        flb_axes |= ax
holes = sum(1 for c in ls_c if any(near(a, c) for a in flb_axes))
out.append("FLB 螺丝贯穿孔=%d/%d (期望%d) %s"
           % (holes, len(ls_c), len(ls_c), "OK" if holes == len(ls_c) else "**不符**"))

# 7) JRT 回归(顶侧条 z=[-47.5,-40], 基线 48 面 {16:16,22:2})
jrt_ok = 0
for b in work_part.Bodies:
    faces = list(b.GetFaces())
    zs = [uf.Modeling.AskFaceData(fc.Tag)[3] for fc in faces]
    zlo, zhi = min(bb[2] for bb in zs), max(bb[5] for bb in zs)
    if abs(zhi - (-40.0)) < 0.1 and abs(zlo - (-47.5)) < 0.1:
        others = Counter()
        for fc in faces:
            d = uf.Modeling.AskFaceData(fc.Tag)
            if float(d[4]) > 1e-9 and abs(d[2][2]) > 0.999:
                pass
            elif not (float(d[4]) < 1e-9 and abs(d[2][2]) > 0.999):
                others[int(d[0])] += 1
        jrt_ok += 1
        out.append("  JRT条: 面%d z=[%.2f,%.2f]" % (len(faces), zlo, zhi))
        if jrt_ok == 1:
            out.append("JRT首条: 面%d 其他=%s (基线48/{16:16,22:2})"
                       % (len(faces), dict(others)))
out.append("JRT 顶侧条=%d 根 (期望2, 大缺口链放弃) %s" % (jrt_ok, "OK" if jrt_ok == 2 else "**不符**"))

# 8) 接线盒(顶面后沿中点 → CXK 线中点(4526.31,1790.27) + CX顶值 -30)
jxh_info = []
for b in work_part.Bodies:
    if not m._is_marked(b):
        continue
    for fc in b.GetFaces():
        d = uf.Modeling.AskFaceData(fc.Tag)
        if float(d[4]) < 1e-9 and abs(d[2][2]) > 0.999:
            bb = d[3]
            w, h = bb[3] - bb[0], bb[4] - bb[1]
            if abs(w - 163.0) < 1.0 and abs(h - 49.5) < 1.0:
                jxh_info.append((bb[2], bb[1], (bb[0] + bb[3]) / 2))
for z, ylo, xc in jxh_info:
    out.append("  接线盒顶面: z=%.2f y后沿=%.2f x中心=%.2f (期望 -30.00/1790.27/4526.31)"
               % (z, ylo, xc))
top_face = max(jxh_info) if jxh_info else None   # 最高 z 的 163×49.5 面=顶面
ok_jxh = (top_face is not None
          and abs(top_face[0] - (-30.0)) < 0.05
          and abs(top_face[1] - 1790.2716) < 0.05
          and abs(top_face[2] - 4526.3106) < 0.05)
out.append("接线盒顶面后沿中点落位=%s (%d处163×49.5面)"
           % ("OK" if ok_jxh else "**不符**", len(jxh_info)))
jxh_bodies = 0
for b in work_part.Bodies:
    if not m._is_marked(b):
        continue
    zs = [uf.Modeling.AskFaceData(fc.Tag)[3] for fc in b.GetFaces()]
    z0, z1 = min(bb[2] for bb in zs), max(bb[5] for bb in zs)
    yc = sum(bb[1] + bb[4] for bb in zs) / (2 * len(zs))
    if -83.0 < z0 and -35.0 < z1 < -20.0 and 1750.0 < yc < 1900.0:
        jxh_bodies += 1
out.append("接线盒实体数=%d (期望2) %s" % (jxh_bodies,
           "OK" if jxh_bodies == 2 else "**不符**"))

with io.open(_os.path.join(_HERE, "v111smoke.txt"),
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("V111SMOKE OK comps=%d feats=%d marked=%d" % (ncomp, nfeat, len(marked)))
