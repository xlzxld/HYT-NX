# -*- coding: utf-8 -*-
"""cad3d.ui.dialogs —— Block UI Styler 交互对话框与事件控制。"""

import io
import os
import time

from cad3d.core.paths import _logs_dir, resolve_dxf_path
from cad3d.core.config import _note
from cad3d.core.constants import (
    LAYER_TABLE, LAYER_CODES, DIALOG_GROUPS, JT_LINK_OPTS, JT_LINK_MODES,
    DEFAULT_JRT, JRT_FIELDS, DEFAULT_STD_RULE, LAYER_SEL_OPTS, ZMODE_OPTS,
    BOOL_OPTS, DIR_OPTS
)
from cad3d.core.state import (
    load_state, merge_params, jrt_with_memory, jt_mode_with_memory,
    derive_linked, _jt_link_values, _cx_link_values, save_state
)
from cad3d.modeling.std_rules import (
    _std_z, merge_std_rules, sanitize_std_rule, std_part_defaults
)
from cad3d.ui.dlx_builder import _opt_index


def _dlg_show(dialog):
    """跨版本弹出 BlockStyler 对话框: NX2312 用 Launch(); NX10/11/12 无 Launch
    (实机交互报 'BlockDialog' object has no attribute 'Launch')→ 用 Show()。
    按存在性选方法(Launch→Show→ReplayDialog), 2312 恒先命中 Launch=零回归。
    返回底层方法的响应码(int; Show/Launch 语义一致)。"""
    for _m in ("Launch", "Show", "ReplayDialog"):
        _f = getattr(dialog, _m, None)
        if callable(_f):
            return _f()
    raise AttributeError("BlockDialog 无 Launch/Show/ReplayDialog 显示方法")


class SelectionDialog(object):
    """第一段"标准件选择"对话框(每件一个复选框; 取消=中止整个流程)。"""

    def __init__(self, dlx_path, files, defaults):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.files = files
        self.defaults = set(defaults)
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self._shown = False
        self.result = None          # None=取消; 否则=选中文件名列表

    def show_cb(self):
        """首显后再按记忆勾选一遍(同 ParamDialog.show_cb, 防保留值覆盖)。"""
        if not getattr(self, "_shown", False):
            self._shown = True
            try:
                for i, f in enumerate(self.files):
                    b = self._find("SEL%d" % i)
                    try:
                        b.Value = (f in self.defaults)
                    except Exception:
                        pass
            except Exception:
                pass
        return 0

    def _find(self, bid):
        if bid not in self.blocks:
            b = self.theDialog.TopBlock.FindBlock(bid)
            if b is None:
                return None
            self.blocks[bid] = b
        return self.blocks[bid]

    def initialize_cb(self):
        for i, f in enumerate(self.files):
            try:
                b = self._find("SEL%d" % i)
                b.Label = f
                b.Value = (f in self.defaults)
            except Exception:
                pass

    def ok_cb(self):
        sel = []
        for i, f in enumerate(self.files):
            try:
                if bool(self._find("SEL%d" % i).Value):
                    sel.append(f)
            except Exception:
                pass
        self.result = sel
        return 0

    def cancel_cb(self):
        self.result = None
        return 0

    def Launch(self):
        try:
            _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show(
                "CAD3D", self.nx.NXMessageBox.DialogType.Error, str(ex))
        return self.result

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


class _BlockDialogBase(object):
    """BlockStyler 对话框公共基类: 块查找/读写辅助 + 标准件行收集。

    (三段式改造抽出: ParamDialog(窗口②) 与 StdParamsDialog(窗口③) 共用,
    改字段只改一处。)子类需设置: theDialog/std_files/std_rules。
    """

    def _find(self, bid):
        if bid not in self.blocks:
            b = self.theDialog.TopBlock.FindBlock(bid)
            if b is None:
                return None
            self.blocks[bid] = b
        return self.blocks[bid]

    def _set_label(self, bid, text):
        try:
            self._find(bid).Label = text
        except Exception:
            pass

    def _dbg_footprint(self, msg):
        """回调异常写调试脚印(独立文件 logs/nx_dialog_debug.txt), 不静默——
        吞错无痕迹曾致"联动坏了无从排查"(历史事故同型, v1.35)。"""
        try:
            with io.open(os.path.join(_logs_dir(), "nx_dialog_debug.txt"),
                         "a", encoding="utf-8") as f:
                f.write("[%s] %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                          type(self).__name__, msg))
        except Exception:
            pass

    def _get_double(self, bid, fallback):
        try:
            v = self._find(bid).Value
            return float(v) if v is not None else fallback
        except Exception:
            return fallback

    def _enum_idx_of(self, b):
        """枚举当前序号(真实 UI 值): ValueAsString 标签反查第一优先——
        它反映界面真实显示项; .Value 次之; GetProperties().GetInteger
        【末位不用】—— v1.15 实测该通道与界面脱钩(写进属性副本, 界面
        仍显示 XML 内嵌值; OK 收集时读到初始 0 → 规则全变"空图层/全
        半径", 执行时全图层海量放置卡死一案)。fallback 由调用方处理。
        """
        try:
            s = b.ValueAsString
            if s:
                return s                     # 调用方用标签时直接拿字符串
        except Exception:
            pass
        try:
            v = b.Value
            if isinstance(v, (int, float)):
                return int(v)
        except Exception:
            pass
        return -1

    def _set_enum_idx(self, bid, idx, labels=None):
        """枚举置选中序号, 逐通道尝试+读回验证(v1.18 实测定案):
        ①Value=int; ②PropertyList.SetEnum("Value", idx)——枚举属性是
        独立类型, v1.14 用 SetInteger 类型不符=写不进(恢复默认改不动
        图层/布尔/方向/Z基准一案); ③SetEnumAsString(需 labels);
        ④SetInteger 兜底。全部失败只静默(收集侧 ValueAsString 仍以
        界面真实显示为准)。"""
        try:
            b = self._find(bid)
        except Exception:
            return
        idx = int(idx)

        def ok():
            got = self._enum_idx_of(b)
            if isinstance(got, str):
                return bool(labels) and got in labels \
                    and labels.index(got) == idx
            return got == idx

        for kind in ("value", "setenum", "setenumstr", "setint"):
            props = None
            try:
                if kind == "value":
                    b.Value = idx
                elif kind == "setenum":
                    props = b.GetProperties()
                    props.SetEnum("Value", idx)
                elif kind == "setenumstr":
                    if labels:
                        props = b.GetProperties()
                        props.SetEnumAsString("Value", labels[idx])
                else:
                    props = b.GetProperties()
                    props.SetInteger("Value", idx)
            except Exception:
                pass
            finally:
                if props is not None:   # PropertyList 用完即释放(v1.35)
                    try:
                        props.Dispose()
                    except Exception:
                        pass
            if ok():
                return

    def _apply_dialog_sizing(self, log=None):
        """显示时把对话框尺寸策略设为自适应内容(宽度一案)。

        NX2312 的 dlx 块模型没有宽度属性(double/label/对话框官方全属性
        表已验证, 仅字符串块有按字符数的 Width), 对话框尺寸唯一钩子是
        TopBlock.DialogSizing(运行时才有, TopBlock 显示前为 None)。
        这里读成员表, 挑含 auto/fit/content 的项设置; 都没有就不动。
        探查结果写脚本目录 nx_dialog_debug.txt(独立脚印文件, 批量测试
        的 report.txt 不会覆盖它)——同时也是 show 回调是否触发的证据。
        """
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        info = []
        try:
            tb = self.theDialog.TopBlock
            if tb is None:
                info.append("TopBlock=None(show 未触发或对话框未就绪)")
            else:
                try:
                    members = [str(m) for m in
                               (tb.GetDialogSizingMembers() or [])]
                except Exception as ex:
                    members = []
                    info.append("成员表读失败: %r" % ex)
                try:
                    cur = str(tb.DialogSizingAsString)
                except Exception as ex:
                    cur = "读失败:%r" % ex
                pick = None
                for m in members:
                    low = m.lower()
                    if any(k in low for k in ("auto", "fit", "content")):
                        pick = m
                        break
                info.append("成员=%s 当前=%s → 选%s"
                            % (members or "空", cur, pick or "不动"))
                if pick and pick != cur:
                    try:
                        tb.DialogSizingAsString = pick
                        info.append("已设置(AsString)")
                    except Exception:
                        _pl = None
                        try:
                            _pl = tb.GetProperties()
                            _pl.SetEnum("DialogSizing", pick)
                            info.append("已设置(SetEnum)")
                        except Exception as ex:
                            info.append("设置失败: %r" % ex)
                        finally:
                            if _pl is not None:
                                try:
                                    _pl.Dispose()
                                except Exception:
                                    pass
        except Exception as ex:
            info.append("异常: %r" % ex)
        try:
            with io.open(os.path.join(_logs_dir(), "nx_dialog_debug.txt"),
                         "a", encoding="utf-8") as f:
                f.write("[%s] %s %s\n" % (stamp, type(self).__name__,
                                           "; ".join(info)))
        except IOError:
            pass
        if log:
            log("【对话框】%s" % "; ".join(info))

    def _get_enum_idx(self, bid, fallback, labels=None):
        """枚举当前序号: 真实 UI 值(_enum_idx_of, 标签反查优先) →
        labels 里定位; 都失败才用 fallback。"""
        b = self._find(bid)
        got = self._enum_idx_of(b)
        if isinstance(got, str):
            if labels and got in labels:
                return labels.index(got)
            return fallback
        if got >= 0:
            return got
        return fallback

    def _collect_std(self):
        """对话框标准件行 → 规则表(序号映射语义值; 枚举读取带标签反查)。"""
        rules = {}
        for i, fname in enumerate(self.std_files):
            pfx = "SP%d_" % i
            r = dict(self.std_rules.get(fname, DEFAULT_STD_RULE))
            li = min(self._get_enum_idx(pfx + "layer", 0,
                                        [t for _v, t in LAYER_SEL_OPTS]),
                     len(LAYER_SEL_OPTS) - 1)
            r["layer"] = LAYER_SEL_OPTS[li][0]
            zi = min(self._get_enum_idx(pfx + "zmode", 0,
                                        [t for _v, t in ZMODE_OPTS]),
                     len(ZMODE_OPTS) - 1)
            r["z_mode"] = ZMODE_OPTS[zi][0]
            bi = min(self._get_enum_idx(pfx + "bool", 0,
                                        [t for _v, t in BOOL_OPTS]),
                     len(BOOL_OPTS) - 1)
            r["bool_mode"] = BOOL_OPTS[bi][0]
            di = min(self._get_enum_idx(pfx + "dir", 0,
                                        [t for _v, t in DIR_OPTS]),
                     len(DIR_OPTS) - 1)
            r["dir"] = DIR_OPTS[di][0]
            r["r_min"] = self._get_double(pfx + "rmin", r["r_min"])
            r["r_max"] = self._get_double(pfx + "rmax", r["r_max"])
            r["off_x"] = self._get_double(pfx + "offx", r["off_x"])
            r["off_y"] = self._get_double(pfx + "offy", r["off_y"])
            r["off_z"] = self._get_double(pfx + "offz", r["off_z"])
            _old_rule = self.std_rules.get(fname) or {}
            if (str(_old_rule.get("layer") or "").upper() == "CXK"
                    and r["layer"] != "CXK"):
                r["r_min"], r["r_max"] = 0.0, 15.0
                _note("【%s】定位图层由 CXK 改为 %s: 半径筛选此前未在"
                      "界面显示, 已重置为 0~15, 请在窗口③核对。"
                      % (fname, r["layer"]))
            rules[fname] = sanitize_std_rule(r)
        return rules


class ParamDialog(_BlockDialogBase):
    def __init__(self, dlx_path, std_rules=None, selected=None,
                 execute_on_ok=True, execute_fn=None):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.theSession = NXOpen.Session.GetSession()
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddApplyHandler(self.apply_cb)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddUpdateHandler(self.update_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self.result_params = None
        self.result_dxf = None
        self.result_jrt = None
        self.result_mode = None
        self.execute_on_ok = execute_on_ok
        self.execute_fn = execute_fn
        self.state = load_state()
        self.params = merge_params(self.state)
        self.std_rules_all = merge_std_rules(self.state)
        self.std_rules = std_rules if std_rules is not None else self.std_rules_all
        self.std_files = sorted(self.std_rules.keys())
        self.selected = list(selected) if selected is not None \
            else sorted(self.std_rules.keys())
        self.jrt = jrt_with_memory(self.state, self.params)
        self.jt_mode = jt_mode_with_memory(self.state)
        self._shown = False
        self._initializing = False

    def _current_jt_mode(self):
        """读 jt_link 枚举当前模式(标签优先, 序号次之; 失败回上次模式)。"""
        b = self._find("jt_link")
        if b is not None:
            try:
                s = b.ValueAsString
                if s and s in JT_LINK_MODES:
                    return s
            except Exception:
                pass
            try:
                return JT_LINK_OPTS[int(b.Value)][0]
            except Exception:
                pass
        return self.jt_mode

    def _get_path(self):
        b = self._find("dxf_file")
        try:
            return str(b.Path) or ""
        except Exception:
            try:
                pl = self.theDialog.GetBlockProperties("dxf_file")
                return str(pl.GetString("Path")) or ""
            except Exception:
                return ""

    def initialize_cb(self):
        self._prefill_all()

    def _invalid_response(self):
        try:
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Invalid
        except Exception:
            return 1

    def _dxf_valid_or_warn(self):
        p = self._get_path()
        if p and os.path.isfile(p):
            return True
        try:
            self.theUI.NXMessageBox.Show(
                "CAD3D", self.nx.NXMessageBox.DialogType.Warning,
                "DXF 文件不存在或路径无效:\n%s\n\n请重新选择有效的 .dxf 图纸。"
                % (p or "(未选择)"))
        except Exception:
            pass
        return False

    def _prefill_all(self):
        self._initializing = True
        try:
            self._set_label("grp_file", "输入文件")
            self._set_label("grp_flb", DIALOG_GROUPS[0][1])
            self._set_label("grp_plain", DIALOG_GROUPS[1][1])
            self._set_label("grp_sub", DIALOG_GROUPS[2][1])
            try:
                self._set_enum_idx("jt_link",
                                   _opt_index(JT_LINK_OPTS, self.jt_mode),
                                   [t for _v, t in JT_LINK_OPTS])
            except Exception:
                pass
            zh = {r[0]: r[1] for r in LAYER_TABLE}
            for _gid, _t, codes in DIALOG_GROUPS:
                for code in codes:
                    zh_name = zh.get(code, code)
                    self._set_label(code + "_start", "%s %s 起始距离" % (code, zh_name))
                    self._set_label(code + "_end", "%s %s 结束距离" % (code, zh_name))
                    s, e = self.params.get(code, (0.0, 0.0))
                    try:
                        self._find(code + "_start").Value = s
                        self._find(code + "_end").Value = e
                    except Exception:
                        pass
            try:
                self.theDialog.TopBlock.Label = "NX 分层拉伸 (DXF→3D)"
            except Exception:
                pass
            p = self.state.get("dxf_path") or resolve_dxf_path(self.state)
            try:
                self._find("dxf_file").Path = p
            except Exception:
                pass
            for key, _label in JRT_FIELDS:
                try:
                    self._find("jrt_" + key).Value = self.jrt.get(key)
                except Exception:
                    pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
        finally:
            self._initializing = False

    def show_cb(self):
        if not getattr(self, "_shown", False):
            self._shown = True
            self._prefill_all()
            self._apply_dialog_sizing()
        return 0

    def update_cb(self, block):
        if getattr(self, "_initializing", False):
            return 0
        try:
            try:
                if block is self._find("jrt_reset"):
                    s0 = self._get_double("FLB_start", 0.0)
                    e0 = self._get_double("FLB_end", 0.0)
                    jrt = dict(DEFAULT_JRT)
                    js, je = derive_linked(max(s0, e0), min(s0, e0)).get(
                        "JRT", (DEFAULT_JRT["start"], DEFAULT_JRT["end"]))
                    jrt["start"], jrt["end"] = js, je
                    for key, _label in JRT_FIELDS:
                        try:
                            self._find("jrt_" + key).Value = jrt[key]
                        except Exception:
                            pass
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jrt_reset 异常: %r" % ex)
            try:
                if block is self._find("jt_link"):
                    self.jt_mode = self._current_jt_mode()
                    s0 = self._get_double("FLB_start", 0.0)
                    e0 = self._get_double("FLB_end", 0.0)
                    v1, v2 = _jt_link_values(max(s0, e0), min(s0, e0),
                                             self.jt_mode)
                    self._find("JT_start").Value = v1
                    self._find("JT_end").Value = v2
                    cs, ce = _cx_link_values(v1)
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jt_link 异常: %r" % ex)
            try:
                if block in (self._find("JT_start"), self._find("JT_end")):
                    cs, ce = _cx_link_values(self._get_double("JT_start", 0.0))
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                    return 0
            except Exception as ex:
                self._dbg_footprint("update_cb jt->cx 异常: %r" % ex)
            flb_s = self._find("FLB_start")
            flb_e = self._find("FLB_end")
            if block in (flb_s, flb_e):
                s = self._get_double("FLB_start", 0.0)
                e = self._get_double("FLB_end", 0.0)
                linked = derive_linked(max(s, e), min(s, e),
                                       jt_mode=self._current_jt_mode())
                for code, (v1, v2) in linked.items():
                    for suffix, val in (("_start", v1), ("_end", v2)):
                        bid = ("jrt" if code == "JRT" else code) + suffix
                        try:
                            self._find(bid).Value = val
                        except Exception:
                            pass
                cs, ce = _cx_link_values(linked["JT"][0])
                try:
                    self._find("CX_start").Value = cs
                    self._find("CX_end").Value = ce
                except Exception:
                    pass
        except Exception as ex:
            self._dbg_footprint("update_cb(%r) 异常: %r"
                                % (getattr(block, "Name", block), ex))
        return 0

    def cancel_cb(self):
        self.result_params = None
        self.result_jrt = None
        self.result_dxf = None
        self.result_mode = None
        return 0

    def _collect(self):
        params = {}
        for code in LAYER_CODES:
            d_s, d_e = self.params.get(code, (0.0, 0.0))
            s = self._get_double(code + "_start", d_s)
            e = self._get_double(code + "_end", d_e)
            params[code] = (s, e)
        if "JT" in params and "CX" in params:
            params["CX"] = _cx_link_values(params["JT"][0])
        return params

    def _collect_jrt(self):
        jrt = dict(DEFAULT_JRT)
        for key, _label in JRT_FIELDS:
            jrt[key] = self._get_double("jrt_" + key, jrt[key])
        return jrt

    def _execute(self):
        if not self._dxf_valid_or_warn():
            return self._invalid_response()
        params = self._collect()
        jrt = self._collect_jrt()
        dxf = self._get_path()
        if not self.execute_on_ok:
            self.result_params = params
            self.result_jrt = jrt
            self.result_dxf = dxf
            self.result_mode = self._current_jt_mode()
            return 0
        std_rules = self._collect_std()
        self.params = params
        self.std_rules = std_rules
        self.jrt = jrt
        exec_fn = self.execute_fn
        if exec_fn is None:
            from cad3d.pipeline.runner import execute_pipeline
            exec_fn = execute_pipeline
        ok = exec_fn(dxf, params, jrt, std_rules, self.theSession,
                     std_rules_all=self.std_rules_all,
                     selected=self.selected, ui=self.theUI,
                     jt_link_mode=self._current_jt_mode())
        return 0 if ok else 1

    def apply_cb(self):
        try:
            return self._execute()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def ok_cb(self):
        try:
            return self._execute()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def Launch(self):
        try:
            return _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Cancel

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


class StdParamsDialog(_BlockDialogBase):
    """第三段"标准件参数"对话框: 每件一个可收起组, OK/Apply 执行, 取消中止。"""

    def __init__(self, dlx_path, std_rules, params, jrt, dxf, selected,
                 std_rules_all=None, jt_mode=None, execute_fn=None):
        import NXOpen
        import NXOpen.BlockStyler
        self.nx = NXOpen
        self.theSession = NXOpen.Session.GetSession()
        self.theUI = NXOpen.UI.GetUI()
        self.theDialog = self.theUI.CreateDialog(dlx_path)
        self.theDialog.AddApplyHandler(self.apply_cb)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddUpdateHandler(self.update_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.show_cb)
        except Exception:
            pass
        self.blocks = {}
        self._shown = False
        self._initializing = False
        self.std_rules = std_rules
        self.std_files = sorted(std_rules.keys())
        self.params = params
        self.jrt = jrt
        self.jt_mode = jt_mode
        self.dxf = dxf
        self.execute_fn = execute_fn
        self.selected = list(selected) if selected is not None else self.std_files
        self.std_rules_all = std_rules_all if std_rules_all is not None \
            else dict(std_rules)

    def initialize_cb(self):
        self._prefill_all()

    def _prefill_all(self):
        self._initializing = True
        try:
            for i, fname in enumerate(self.std_files):
                r = self.std_rules[fname] if isinstance(self.std_rules.get(fname), dict) else {}
                pfx = "SP%d_" % i
                self._set_enum_idx(pfx + "layer",
                                   _opt_index(LAYER_SEL_OPTS, r.get("layer", "")))
                self._set_enum_idx(pfx + "zmode",
                                   _opt_index(ZMODE_OPTS, r.get("z_mode", "FLB_TOP")))
                self._set_enum_idx(pfx + "bool",
                                   _opt_index(BOOL_OPTS, r.get("bool_mode", "PLACE")))
                self._set_enum_idx(pfx + "dir",
                                   _opt_index(DIR_OPTS, r.get("dir", "+Z")))
                for key, fld in (("rmin", "r_min"), ("rmax", "r_max"),
                                 ("offx", "off_x"),
                                 ("offy", "off_y"), ("offz", "off_z")):
                    try:
                        self._find(pfx + key).Value = r.get(fld, 0.0)
                    except Exception:
                        pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
        finally:
            self._initializing = False

    def show_cb(self):
        if not getattr(self, "_shown", False):
            self._shown = True
            self._prefill_all()
            self._apply_dialog_sizing()
        return 0

    def update_cb(self, block):
        if getattr(self, "_initializing", False):
            return 0
        try:
            for i, fname in enumerate(self.std_files):
                bid = "SP%d_reset" % i
                try:
                    if block is self._find(bid):
                        self._reset_std(i)
                        break
                except Exception:
                    continue
        except Exception:
            pass
        return 0

    def _reset_std(self, i):
        fname = self.std_files[i]
        r = sanitize_std_rule(std_part_defaults(fname))
        self.std_rules[fname] = r
        pfx = "SP%d_" % i
        self._set_enum_idx(pfx + "layer",
                           _opt_index(LAYER_SEL_OPTS, r["layer"]),
                           [t for _v, t in LAYER_SEL_OPTS])
        self._set_enum_idx(pfx + "zmode",
                           _opt_index(ZMODE_OPTS, r["z_mode"]),
                           [t for _v, t in ZMODE_OPTS])
        self._set_enum_idx(pfx + "bool",
                           _opt_index(BOOL_OPTS, r["bool_mode"]),
                           [t for _v, t in BOOL_OPTS])
        self._set_enum_idx(pfx + "dir",
                           _opt_index(DIR_OPTS, r["dir"]),
                           [t for _v, t in DIR_OPTS])
        for key, fld in (("rmin", "r_min"), ("rmax", "r_max"),
                         ("offx", "off_x"),
                         ("offy", "off_y"), ("offz", "off_z")):
            try:
                self._find(pfx + key).Value = r[fld]
            except Exception:
                pass
        try:
            self._set_label(pfx + "zval",
                            "Z基准值: %.4g" % _std_z(self.params, r))
        except Exception:
            pass

    def cancel_cb(self):
        return 0

    def _execute(self):
        try:
            rules = self._collect_std()
            exec_fn = self.execute_fn
            if exec_fn is None:
                from cad3d.pipeline.runner import execute_pipeline
                exec_fn = execute_pipeline
            ok = exec_fn(self.dxf, self.params, self.jrt, rules,
                         self.theSession,
                         std_rules_all=self.std_rules_all,
                         selected=self.selected, ui=self.theUI,
                         jt_link_mode=self.jt_mode)
            return 0 if ok else 1
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return 1

    def apply_cb(self):
        return self._execute()

    def ok_cb(self):
        return self._execute()

    def Launch(self):
        try:
            return _dlg_show(self.theDialog)
        except Exception as ex:
            self.theUI.NXMessageBox.Show("CAD3D", self.nx.NXMessageBox.DialogType.Error,
                                         str(ex))
            return self.nx.BlockStyler.BlockDialog.DialogResponse.Cancel

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None
