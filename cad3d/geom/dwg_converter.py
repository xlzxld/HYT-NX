# -*- coding: utf-8 -*-
"""cad3d.geom.dwg_converter —— AutoCAD DWG 转 DXF 后台无头静默转换引擎。

设计目标：
  1. 允许用户在 NX 界面中直接选择 .dwg 图纸；
  2. 后台全自动探查本机 AutoCAD 环境（支持高版本 AutoCAD 2013~2026+ 的 accoreconsole.exe
     及低版本 AutoCAD 2004~2012 的 acad.exe 批处理）；
  3. 通过 /readonly 防死锁参数，即使图纸正在 AutoCAD 中打开也能无感导出；
  4. 生成符合 CAD3D 解析标准的 2004 格式 ASCII DXF，并在流水线结束后 100% 安全销毁。
"""

import os
import glob
import time
import uuid
import shutil
import subprocess
from cad3d.core.paths import script_dir, _logs_dir, _get_cfg


class DwgConversionError(Exception):
    """DWG 转换失败异常类。"""
    pass


def find_acad_executable():
    """多级自适应探测本机 AutoCAD 可执行文件路径。

    探测优先级：
      1. 用户在 nx_std_config.py 中显式指定的 ACAD_CONSOLE_PATH；
      2. Windows 注册表 HKEY_LOCAL_MACHINE / HKEY_CURRENT_USER 检索到的安装路径；
      3. C/D/E 盘标准 Program Files 默认安装路径扫描；
      4. 系统 PATH 环境变量。

    返回: (exe_path, is_core_console)
      - is_core_console 为 True 表示 accoreconsole.exe（高版本无头轻量引擎，极速 1 秒）；
      - is_core_console 为 False 表示 acad.exe（低版本经典控制台）。
      - 未找到时返回 (None, False)。
    """
    # 1. 配置文件优先
    cfg_path = _get_cfg("ACAD_CONSOLE_PATH", None)
    if cfg_path and os.path.isfile(cfg_path):
        is_core = "accoreconsole" in os.path.basename(cfg_path).lower()
        return os.path.abspath(cfg_path), is_core

    found_consoles = []
    found_acads = []

    # 2. Windows 注册表扫描
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Autodesk\AutoCAD") as key:
                    num_sub = winreg.QueryInfoKey(key)[0]
                    for i in range(num_sub):
                        ver_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, ver_name) as ver_key:
                                num_prod = winreg.QueryInfoKey(ver_key)[0]
                                for j in range(num_prod):
                                    prod_name = winreg.EnumKey(ver_key, j)
                                    try:
                                        with winreg.OpenKey(ver_key, prod_name) as prod_key:
                                            loc = winreg.QueryValueEx(prod_key, "AcadLocation")[0]
                                            c_core = os.path.join(loc, "accoreconsole.exe")
                                            c_acad = os.path.join(loc, "acad.exe")
                                            if os.path.isfile(c_core):
                                                found_consoles.append(c_core)
                                            elif os.path.isfile(c_acad):
                                                found_acads.append(c_acad)
                                    except OSError:
                                        pass
                        except OSError:
                            pass
            except OSError:
                pass
    except Exception:
        pass

    # 3. 常见盘符与目录模式扫描
    patterns_core = [
        r"C:\Program Files\Autodesk\AutoCAD 20*\accoreconsole.exe",
        r"C:\Program Files\AutoCAD 20*\accoreconsole.exe",
        r"D:\Program Files\Autodesk\AutoCAD 20*\accoreconsole.exe",
        r"D:\Program Files\AutoCAD 20*\accoreconsole.exe",
        r"E:\Program Files\Autodesk\AutoCAD 20*\accoreconsole.exe",
        r"C:\Program Files (x86)\Autodesk\AutoCAD 20*\accoreconsole.exe",
    ]
    for pat in patterns_core:
        for p in glob.glob(pat):
            if os.path.isfile(p) and p not in found_consoles:
                found_consoles.append(p)

    patterns_acad = [
        r"C:\Program Files\Autodesk\AutoCAD 20*\acad.exe",
        r"C:\Program Files\AutoCAD 20*\acad.exe",
        r"C:\Program Files (x86)\AutoCAD 20*\acad.exe",
        r"C:\Program Files (x86)\Autodesk\AutoCAD 20*\acad.exe",
        r"D:\Program Files\Autodesk\AutoCAD 20*\acad.exe",
    ]
    for pat in patterns_acad:
        for p in glob.glob(pat):
            if os.path.isfile(p) and p not in found_acads:
                found_acads.append(p)

    # 4. PATH 环境变量
    which_core = shutil.which("accoreconsole.exe")
    if which_core and which_core not in found_consoles:
        found_consoles.append(which_core)
    which_acad = shutil.which("acad.exe")
    if which_acad and which_acad not in found_acads:
        found_acads.append(which_acad)

    # 优先使用 accoreconsole.exe（高版本极速无头引擎，倒序选最新版本）
    if found_consoles:
        found_consoles.sort(reverse=True)
        return found_consoles[0], True

    # 降级使用 acad.exe（低版本经典引擎）
    if found_acads:
        found_acads.sort(reverse=True)
        return found_acads[0], False

    return None, False


def _clean_stale_temp_files(max_age_seconds=3600):
    """清理 logs 目录下超时的历史残留临时转换文件。"""
    try:
        ld = _logs_dir()
        now = time.time()
        for f in os.listdir(ld):
            if f.startswith(("_temp_dwg_", "_dwg_scr_")):
                full = os.path.join(ld, f)
                try:
                    if now - os.path.getmtime(full) > max_age_seconds:
                        os.remove(full)
                except Exception:
                    pass
    except Exception:
        pass


def convert_dwg_to_dxf(dwg_path, out_dxf=None, timeout=60, log=None):
    """将 AutoCAD DWG 图纸无头静默转换为 2004 ASCII DXF。

    参数:
      dwg_path: 输入 .dwg 文件绝对路径。
      out_dxf:  输出 .dxf 文件绝对路径（若为 None 则在 logs/ 下自动生成唯一临时文件）。
      timeout:  执行超时保护阈值（秒，默认 60s）。
      log:      日志回调函数。

    返回:
      生成的 .dxf 文件的绝对路径。

    异常:
      若未找到 AutoCAD 或转换失败，抛出 DwgConversionError 并附带清晰指引。
    """
    if not dwg_path or not os.path.isfile(dwg_path):
        raise DwgConversionError("指定的 DWG 图纸文件不存在:\n%s" % (dwg_path or "(空)"))

    _clean_stale_temp_files()

    exe_path, is_core = find_acad_executable()
    if not exe_path:
        raise DwgConversionError(
            "未能自动转换 DWG 文件：未检测到本机已安装的 AutoCAD 运行程序。\n\n"
            "【解决方式】\n"
            "1. 若已安装 AutoCAD 但安装在特殊盘符，请在 nx_std_config.py 中配置 ACAD_CONSOLE_PATH；\n"
            "2. 或直接在 AutoCAD 中将图纸另存为 2004 格式的 .dxf 文件后重新选择。"
        )

    logs_dir = _logs_dir()
    tag = "%d_%s" % (int(time.time()), uuid.uuid4().hex[:8])

    if out_dxf is None:
        out_dxf = os.path.join(logs_dir, "_temp_dwg_%s.dxf" % tag)

    scr_path = os.path.join(logs_dir, "_dwg_scr_%s.scr" % tag)
    out_dxf_escaped = out_dxf.replace("\\", "/")
    dwg_path_escaped = dwg_path.replace("\\", "/")

    # 构建跨版本通用 AutoLISP 导出脚本：
    # 1. 关闭对话框提示 (FILEDIA 0)；
    # 2. 若是旧版 acad.exe 则补发 OPEN 指令；
    # 3. 优先执行 DXFOUT 导出 2004 格式（16位精度）；若老版本无 _v 选项则直接以默认精度导出；
    # 4. 强制无损退出 (QUIT _Y)。
    if is_core:
        scr_lines = [
            '(setvar "FILEDIA" 0)',
            '(command "_.dxfout" "%s" "_v" "2004" "16")' % out_dxf_escaped,
            '(if (not (findfile "%s")) (command "_.dxfout" "%s" "16"))'
            % (out_dxf_escaped, out_dxf_escaped),
            '(command "_.QUIT" "_Y")',
            '',
        ]
        cmd = [exe_path, "/i", dwg_path, "/s", scr_path, "/readonly"]
    else:
        # 低版本 acad.exe 兼容模式
        scr_lines = [
            '(setvar "FILEDIA" 0)',
            '(command "_.OPEN" "%s")' % dwg_path_escaped,
            '(command "_.dxfout" "%s" "_v" "2004" "16")' % out_dxf_escaped,
            '(if (not (findfile "%s")) (command "_.dxfout" "%s" "16"))'
            % (out_dxf_escaped, out_dxf_escaped),
            '(command "_.QUIT" "_Y")',
            '',
        ]
        cmd = [exe_path, "/nologo", "/b", scr_path]

    try:
        with open(scr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(scr_lines))
    except Exception as ex:
        raise DwgConversionError("创建临时转换脚本失败: %s" % ex)

    if log:
        log("【DWG 转换】启动后台转换: %s -> DXF (%s)"
            % (os.path.basename(dwg_path), "accoreconsole" if is_core else "acad"))

    try:
        t0 = time.time()
        # 使用二进制流读取 stdout/stderr，彻底杜绝中文 Windows GBK 解码异常
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False
        )
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        raise DwgConversionError("AutoCAD 转换图纸超时（超过 %d 秒），进程已终止。" % timeout)
    except Exception as ex:
        raise DwgConversionError("调用 AutoCAD 转换进程失败: %s" % ex)
    finally:
        try:
            if os.path.isfile(scr_path):
                os.remove(scr_path)
        except Exception:
            pass

    if not os.path.isfile(out_dxf) or os.path.getsize(out_dxf) == 0:
        err_msg = "DWG 转 DXF 失败，未生成有效 DXF 文件。"
        if proc.returncode != 0:
            err_msg += " (AutoCAD 退出码: %d)" % proc.returncode
        raise DwgConversionError(err_msg)

    if log:
        log("【DWG 转换】转换成功: 大小 %.1f KB, 耗时 %.2f 秒"
            % (os.path.getsize(out_dxf) / 1024.0, elapsed))

    return os.path.abspath(out_dxf)
