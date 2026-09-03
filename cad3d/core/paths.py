# -*- coding: utf-8 -*-
"""cad3d.core.paths —— 系统文件定位与动态路径管理。"""

import os
import sys
import time

# 项目根目录绝对路径锚定
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def script_dir():
    """返回脚本根目录绝对路径（兼顾 NX 日记执行与外部测试调用）。"""
    return ROOT_DIR


def _get_cfg(key, default):
    """延迟安全读取用户配置，避免模块初始化时的循环引用。"""
    try:
        from cad3d.core.config import _cfg
        return _cfg(key, default)
    except Exception:
        return default


def _logs_dir():
    """获取运行生成物存放目录（动态 dlx 界面、执行日志与诊断输出）。"""
    dirname = str(_get_cfg("LOGS_DIRNAME", "logs"))
    p = os.path.join(script_dir(), dirname)
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        p = script_dir()
    return p


def _fresh_dlx_path(base_name, base_dir=None):
    """生成唯一的临时 .dlx 文件路径（时间戳后缀）。
    
    设计说明：
      Siemens NX 会根据 dlx 完整文件名缓存并强制回灌上一轮会话的数据。
      通过动态毫秒时间戳生成唯一命名，彻底杜绝历史残留数据干扰，确保每次对话框均以最新参数呈现。
      在创建新文件前，会自动清理当前目录下同前缀的旧临时文件，避免日志堆积。
    """
    d = base_dir if base_dir is not None else _logs_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    try:
        for n in os.listdir(d):
            if n.endswith(".dlx") and n.startswith(base_name):
                try:
                    os.remove(os.path.join(d, n))
                except OSError:
                    pass
    except OSError:
        pass
    return os.path.join(d, "%s_%d.dlx" % (base_name, int(time.time() * 1000) % 10 ** 10))


def _temp_dlx_path(base_name):
    """备用临时目录（%TEMP%）唯一路径生成，供紧急兜底时调用。"""
    import tempfile
    td = os.environ.get("TEMP") or tempfile.gettempdir()
    return _fresh_dlx_path(base_name, base_dir=td)


def stdparts_dir(dirname=None):
    """获取标准件库 (.prt) 存放目录路径。"""
    if dirname is None:
        dirname = str(_get_cfg("STDPARTS_DIRNAME", "stdparts"))
    return os.path.join(script_dir(), dirname)


def _json_path():
    """获取运行时参数记忆持久化 JSON 文件路径。"""
    filename = str(_get_cfg("PARAMS_FILENAME", "nx_extrude_params.json"))
    return os.path.join(script_dir(), filename)


def resolve_dxf_path(state):
    """智能解析并定位 AutoCAD DXF 图纸路径：
    1. 优先使用记忆文件中保存的历史路径；
    2. 若历史路径失效，自动搜索根目录下最新修改的 .dxf 文件。
    """
    p = (state.get("dxf_path") or "") if isinstance(state, dict) else ""
    if p and os.path.isfile(p):
        return p
    try:
        cands = [os.path.join(script_dir(), n) for n in os.listdir(script_dir())
                 if n.lower().endswith(".dxf")]
        if cands:
            return max(cands, key=os.path.getmtime)
    except OSError:
        pass
    return ""
