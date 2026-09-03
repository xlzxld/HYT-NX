# -*- coding: utf-8 -*-
"""cad3d.core.paths —— 路径与文件定位工具。"""

import os
import sys
import time

# 统一锚定项目根目录: cad3d/core/paths.py 向上三级即为根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def script_dir():
    """脚本所在根目录(兼顾 journal 播放与外部模块调用)。"""
    return ROOT_DIR


def _logs_dir():
    """运行生成物目录(dlx/日志/调试脚印), 与脚本同级的 logs 子目录。"""
    p = os.path.join(script_dir(), "logs")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        p = script_dir()
    return p


def _fresh_dlx_path(base_name, base_dir=None):
    """唯一 dlx 路径(毫秒戳; 写前清旧)。NX 的对话框记忆按 dlx 文件名
    存取并会在显示时回灌旧值(RetainValue=False 也拦不住, 实测)——
    固定名会让历史会话的错误显示值死灰复燃(v1.17 改回固定名后"标准件
    默认值又丢失错乱"即此); 每轮唯一名让记忆永远无载体。窗口宽度不靠
    文件名记忆(NX 不跨会话记尺寸, 固定名时代用户同样每轮要拉宽),
    由 dlx 内撑宽行直接做够。"""
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
    return os.path.join(d, "%s_%d.dlx"
                        % (base_name, int(time.time() * 1000) % 10 ** 10))


def _temp_dlx_path(base_name):
    """%TEMP% 回退路径也用唯一名——固定名会复活 v1.14/v1.17 已根治的
    "NX 按 dlx 文件名回灌旧会话值"事故(v1.35)。"""
    import tempfile
    td = os.environ.get("TEMP") or tempfile.gettempdir()
    return _fresh_dlx_path(base_name, base_dir=td)


def stdparts_dir(dirname="stdparts"):
    """标准件目录 = 脚本同级的 dirname(默认 stdparts)。"""
    return os.path.join(script_dir(), dirname)


def _json_path():
    """参数记忆 JSON 路径。"""
    return os.path.join(script_dir(), "nx_extrude_params.json")


def resolve_dxf_path(state):
    """DXF 路径: 记忆值优先, 否则脚本目录最新 *.dxf。"""
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
