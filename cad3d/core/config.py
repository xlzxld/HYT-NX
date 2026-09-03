# -*- coding: utf-8 -*-
"""cad3d.core.config —— 3级模块加载梯与用户配置加载。"""

import io
import os
import sys
from cad3d.core.paths import script_dir

_CFG_NOTES = []


def _note(msg):
    """提示入队(去重); 由启动弹窗/流水线日志/自测输出。"""
    if msg not in _CFG_NOTES:
        _CFG_NOTES.append(msg)


def _cfg_num(v, default):
    """任意配置值 → float; 类型/值非法(含 nan/inf)回 default, 不崩。"""
    try:
        f = float(v)
        return f if f == f and -1e308 < f < 1e308 else float(default)
    except (TypeError, ValueError):
        return float(default)


def _import_module_from_path(name, path):
    """三级模块加载梯(兼容 NX10 的 Python 3.3.2 缺 importlib.util.spec_*):
      梯1 importlib.util.spec_from_file_location (3.4+, 含 NX12/2312) —— 主路径
      梯2 imp.load_source (3.3, NX10 实机 PY003=AVAILABLE)
      梯3 compile+exec 到 ModuleType (3.x 全兼容兜底, imp 于 3.12 移除后仍可用)
    仅"能力缺失"(ImportError/AttributeError)才下梯; 真实加载错(语法/属性)直接
    抛出, 交由调用方记录, 不掩盖。"""
    ladder_err = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (ImportError, AttributeError, ValueError) as ex:
        ladder_err = "%s: %s" % (type(ex).__name__, ex)
    try:
        import imp
        if hasattr(imp, "load_source"):
            return imp.load_source(name, path)
    except (ImportError, AttributeError):
        pass
    import types
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, path, "exec"), mod.__dict__)
    if ladder_err:
        _note("importlib 不可用(%s), 已用 exec 兜底加载配置。" % ladder_err)
    return mod


def _load_user_config():
    sys.dont_write_bytecode = True   # 不生成 __pycache__(缓存可删可重建)
    base = script_dir()
    p = os.path.join(base, "nx_std_config.py")
    if not os.path.isfile(p):
        _note("配置文件 nx_std_config.py 不存在, 已回退内置默认。")
        return None
    try:
        mod = _import_module_from_path("nx_std_config", p)
        _ = (mod.CONFIG_SCHEMA_VERSION, len(mod.STD_PART_DEFAULTS),
             mod.JRT_BLEND_R_DEFAULT)
        return mod
    except Exception as ex:    # 语法错/缺关键属性/被占用 → 记录原因, 不静默
        _note("配置文件加载失败(%s: %s), 已整体回退内置默认"
              "——请检查 nx_std_config.py。" % (type(ex).__name__, ex))
        return None


_USER_CFG = _load_user_config()

# 记忆结构版本: 与 nx_extrude_params.json 里存的 schema 相同才认记忆中的
# 标准件规则; 配置文件里把版本调大即可一次性清洗旧记忆(回出厂默认)。
SCHEMA_VERSION = 2
try:
    SCHEMA_VERSION = (int(_USER_CFG.CONFIG_SCHEMA_VERSION)
                      if _USER_CFG is not None else 2)
except (TypeError, ValueError):
    SCHEMA_VERSION = 2
    _note("CONFIG_SCHEMA_VERSION 非法(应为整数), 按 2 处理。")


def _cfg(key, default):
    """读配置项(nx_std_config.py), 缺文件/缺键回默认(=原写死值)。"""
    return getattr(_USER_CFG, key, default) if _USER_CFG is not None \
        else default


def _cfg_int(key, default):
    """读配置项并转 int; 类型/值非法回 default(不崩)。"""
    try:
        return int(_cfg_num(_cfg(key, default), default))
    except (TypeError, ValueError, OverflowError):
        return int(default)


# JRT 三参默认(配置文件可改; 永不进记忆; 类型非法回默认不崩)
_JRT_BLEND_R = _cfg_num(getattr(_USER_CFG, "JRT_BLEND_R_DEFAULT", 3.9)
                        if _USER_CFG else 3.9, 3.9)
_JRT_R_STEP = _cfg_num(getattr(_USER_CFG, "JRT_R_STEP_DEFAULT", 0.1)
                       if _USER_CFG else 0.1, 0.1)
_JRT_R_MIN = _cfg_num(getattr(_USER_CFG, "JRT_R_MIN_DEFAULT", 3.7)
                      if _USER_CFG else 3.7, 3.7)
