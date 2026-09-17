# -*- coding: utf-8 -*-
"""make_portable_pkg.py —— 一键生成"老旧机器移植包"（zip）。

在开发机上跑（普通 Python 3 即可，不需要 NX）。它做四件事：
  1. 前置体检：stdparts\\ 的 .prt 数、tools\\NX向下兼容工具\\xt\\ 的 .x_t 数
  2. 按白名单拷出"老旧机器最小运行集"（清单见 docs\\移植手册.md §2）
  3. 生成目标机专用的 convert\\ 目录（**纯 ASCII 路径**，NX 只会看到这里）
     + 一键降级标准件.bat（目标机双击即完成降级）
  4. 打成 zip

用法::

    python make_portable_pkg.py                      # 输出到项目同级的 HYT-NX-portable
    python make_portable_pkg.py --out D:\\pkg          # 自定义输出目录
    python make_portable_pkg.py --allow-missing-xt   # x_t 还没导出也先打包（目标机降级会失败）
    python make_portable_pkg.py --no-zip             # 只出文件夹，不压缩

设计要点（别改回去）：
  - 包名用 ASCII（HYT-NX-portable）。NX10 跑在本地代码页(GBK)模式，路径带中文会报
    "期望的是语言环境数据，但检测到 UTF8 数据"，中文目录名会直接踩这个坑。
  - convert\\ 下只放 import_xt_to_prt.py + xt\\*.x_t，全部 ASCII；
    产出目录 x_t转prt\\ 由 Python（Unicode 安全）创建，NX 全程看不到中文。
  - 目标机的降级必须在那台机器上跑：产出的 .prt 格式 = 执行导入那台 NX 的版本，
    在 NX2312 上导入只会得到又一个 2312 的 prt，对老旧机器毫无意义。
"""

import argparse
import io
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))          # <root>\tools\移植工具
ROOT = os.path.dirname(os.path.dirname(HERE))              # <root>
CONVERT_TOOL = os.path.join(ROOT, "tools", "NX向下兼容工具")
XT_DIR = os.path.join(CONVERT_TOOL, "xt")
STDPARTS = os.path.join(ROOT, "stdparts")

PKG_NAME = "HYT-NX-portable"
MARKER = ".hyt_portable_marker"
EXPECT_PRT = 14
EXPECT_XT = 14

# ── 白名单：老旧机器最小运行集 ────────────────────────────────────────────
WHITELIST_FILES = [
    "nx_extrude_runner.py",     # NX 日记主入口
    "nx_mold_cut_runner.py",    # 模具开框入口
    "nx_std_config.py",         # 业务配置（exec 加载，缺了会整体回退内置默认）
    "batch_smoke.py",           # 端到端冒烟（验收用）
]
WHITELIST_DIRS = [
    "cad3d",                    # 全部核心代码
    "stdparts",                 # 标准件库（目标机降级后覆盖）
]
WHITELIST_FIXTURES = ["3Dtest.dxf", "sample_layers.dxf"]
WHITELIST_DOCS = ["移植手册.md", "使用手册.md"]

# ── 目标机一键降级脚本：模板外置 + 强制校验 ───────────────────────────
# 内容放在 convert_bat_template.txt，必须是**纯 ASCII + CRLF**。
# 为什么外置而不是内联字符串：模板可以被独立编辑和校验，读进来时强制验
# 编码/换行，出问题在打包阶段就当场炸掉，而不是等到老机器上才炸。
# 详见 docs\移植手册.md §10「维护者必读：两个 .bat 的编码红线」。
BAT_TEMPLATE = os.path.join(HERE, "convert_bat_template.txt")


def _check_bat_template():
    """校验降级 bat 模板，不达标就当场终止。

    规则（2026-09-16 更新，两条都是踩过坑换来的）：

    1. **必须 GBK(cp936) + CRLF，不能有 BOM。**
       中文 Windows 的 cmd 按本地代码页(936) **逐字节**读 .bat。
       存成 UTF-8 会让解析器丢同步，报满屏 `'EV' 不是内部或外部命令`；
       而要让中文提示正确显示，就必须存成 GBK，并在 bat 开头 `chcp 936`。

    2. **中文字符的 GBK 尾字节不能落在 shell 元字符 `| & < > ^ "` 上。**
       在正常 936 系统上不会误读，但万一系统代码页不是 936，这些字节会被
       当成管道/重定向/转义符，可能把一行拆坏。本仓库模板实测为 0 个，由本
       函数守住 —— 以后改中文文案如果踩到，会在这里被拦下并指出偏移。
    """
    if not os.path.isfile(BAT_TEMPLATE):
        _die("找不到 bat 模板：%s" % BAT_TEMPLATE)
    with open(BAT_TEMPLATE, "rb") as f:
        raw = f.read()

    if raw[:3] == b"\xef\xbb\xbf":
        _die("bat 模板带了 UTF-8 BOM，cmd 会把首行 @echo off 执行失败：%s"
             % BAT_TEMPLATE)
    try:
        raw.decode("gbk")
    except UnicodeDecodeError as ex:
        _die("bat 模板不是合法 GBK（偏移 %d：%r）。\n"
             "cmd 按本地代码页 936 逐字节读 .bat，模板必须存成 GBK + CRLF。"
             % (ex.start, raw[ex.start:ex.end]))
    if b"\n" in raw.replace(b"\r\n", b""):
        _die("bat 模板混用了裸 LF 换行，必须全部 CRLF：%s" % BAT_TEMPLATE)

    meta = set(b'|&<>^"')
    bad = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b >= 0x81 and i + 1 < len(raw) and 0x40 <= raw[i + 1] <= 0xFE:
            if raw[i + 1] in meta:
                bad.append(i)
            i += 2
        else:
            i += 1
    if bad:
        _die("bat 模板里有 %d 个中文字符的 GBK 尾字节是 shell 元字符"
             "（首个偏移 %d）。在非 936 代码页的系统上可能被误读成 "
             "| & < > ^ \" ，把命令行拆坏，请改一下那句文案：%s"
             % (len(bad), bad[0], BAT_TEMPLATE))
    return True


def _log(msg):
    print(msg)


def _die(msg):
    _log("错误: %s" % msg)
    sys.exit(1)


def _count(d, ext):
    if not os.path.isdir(d):
        return 0
    return len([n for n in os.listdir(d) if n.lower().endswith(ext)])


def _ignore(_d, names):
    return [n for n in names
            if n in ("__pycache__", ".ruff_cache") or n.endswith(".pyc")]


def _prepare_dst(dst):
    """安全准备输出目录：只清自己产出的包，绝不动陌生的已有目录。

    标记文件在建立目录后**立刻**写入 —— 这样上次跑到一半崩掉的半成品也能被
    认出来并干净重建，而不是卡在"拒绝覆盖"上。
    """
    if os.path.isdir(dst):
        if not os.path.isfile(os.path.join(dst, MARKER)):
            _die("输出目录已存在且不是本脚本产出的包，拒绝覆盖：\n  %s\n"
                 "请换一个 --out，或先手工确认后删掉它。" % dst)
        shutil.rmtree(dst)
    elif os.path.exists(dst):
        _die("输出路径已被一个文件占用：%s" % dst)
    os.makedirs(dst)
    with io.open(os.path.join(dst, MARKER), "w", encoding="utf-8") as f:
        f.write("此文件由 tools\\移植工具\\make_portable_pkg.py 生成，"
                "用于防止误删已有目录。可随包分发。\n")


def _health_check(allow_missing_xt):
    """前置体检：缺件就报，不静默打半个包。"""
    n_prt = _count(STDPARTS, ".prt")
    _log("[体检] stdparts  .prt = %d  (期望 %d)" % (n_prt, EXPECT_PRT))
    if n_prt != EXPECT_PRT:
        _die("stdparts 里的 .prt 数量不是 %d，先确认标准件库是否完整。" % EXPECT_PRT)

    n_xt = _count(XT_DIR, ".x_t")
    _log("[体检] convert\\xt .x_t = %d  (期望 %d)" % (n_xt, EXPECT_XT))
    if n_xt != EXPECT_XT:
        if not allow_missing_xt:
            _die("x_t 交换件不齐（%d/%d）。先在 NX2312 里跑一次 "
                 "tools\\NX向下兼容工具\\export_xt.py，或用 一键打包移植包.bat。\n"
                 "只想先看包结构、不要求能降级，可加 --allow-missing-xt。"
                 % (n_xt, EXPECT_XT))
        _log("[警告] x_t 不齐，仍继续打包 —— 目标机的一键降级会失败！")

    empty = []
    if os.path.isdir(XT_DIR):
        for n in sorted(os.listdir(XT_DIR)):
            if n.lower().endswith(".x_t"):
                p = os.path.join(XT_DIR, n)
                if os.path.getsize(p) == 0:
                    empty.append(n)
    if empty:
        _die("以下 x_t 是空文件，重新导出后再打包：%s" % ", ".join(empty))


def _copy_whitelist(dst):
    for f in WHITELIST_FILES:
        src = os.path.join(ROOT, f)
        if not os.path.isfile(src):
            _die("白名单文件不存在：%s" % src)
        shutil.copy2(src, os.path.join(dst, f))

    for d in WHITELIST_DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            _die("白名单目录不存在：%s" % src)
        shutil.copytree(src, os.path.join(dst, d), ignore=_ignore)

    fx = os.path.join(dst, "test", "fixtures")
    os.makedirs(fx)
    for f in WHITELIST_FIXTURES:
        src = os.path.join(ROOT, "test", "fixtures", f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(fx, f))

    dd = os.path.join(dst, "docs")
    os.makedirs(dd)
    for f in WHITELIST_DOCS:
        src = os.path.join(ROOT, "docs", f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dd, f))


def _build_convert(dst):
    """生成目标机专用 convert\\（纯 ASCII）+ 一键降级标准件.bat。"""
    conv = os.path.join(dst, "convert")
    os.makedirs(conv)

    journal = os.path.join(CONVERT_TOOL, "import_xt_to_prt.py")
    if not os.path.isfile(journal):
        _die("找不到导入脚本：%s" % journal)
    shutil.copy2(journal, os.path.join(conv, "import_xt_to_prt.py"))

    dst_xt = os.path.join(conv, "xt")
    os.makedirs(dst_xt)
    if os.path.isdir(XT_DIR):
        for n in sorted(os.listdir(XT_DIR)):
            if n.lower().endswith(".x_t"):
                shutil.copy2(os.path.join(XT_DIR, n), os.path.join(dst_xt, n))

    bat = os.path.join(dst, "一键降级标准件.bat")
    _check_bat_template()                      # 有问题在这里当场炸，不静默产出坏 bat
    shutil.copyfile(BAT_TEMPLATE, bat)         # 逐字节照搬，不做任何再编码


def _write_manifest(dst):
    lines = [
        "HYT-NX 老旧机器移植包",
        "=" * 40,
        "",
        "这是给 NX 10 / NX 12 等老旧机器用的最小运行包。",
        "",
        "【第 1 步】把这个包放到纯英文路径下（例如 C:\\nxpkg\\），不能有中文目录名。",
        ("           NX10 跑在 GBK 模式，中文路径会报"
         "「期望的是语言环境数据，但检测到 UTF8 数据」。"),
        "",
        "【第 2 步】双击本目录的「一键降级标准件.bat」。",
        "          它会调用本机 NX 把 convert\\xt\\ 里的 .x_t 还原成本机版本的 .prt，",
        "          并自动拷进 stdparts\\ 覆盖同名。看到 DONE 即成功。",
        "",
        "【第 3 步】打开 NX，新建一个毫米部件，播放根目录的 batch_smoke.py 验收。",
        "          最后一行应为：BATCH RESULT run1=True run2=True",
        "",
        "【日常使用】NX 里 工具 → 日记 → 播放，选 nx_extrude_runner.py。",
        "",
        "详细说明见 docs\\移植手册.md（完整移植流程）与 docs\\使用手册.md（日常操作）。",
        "",
        "注意：stdparts\\ 里的 .prt 在降级前仍是 NX2312 母版，老机器打不开——",
        "      这是正常的，跑完第 2 步就换成本机版本了。",
        "      这批降级后的 .prt 是「哑实体」（无特征树），别再拷回开发机覆盖母版。",
        "",
    ]
    with io.open(os.path.join(dst, "移植包说明.txt"), "w",
                 encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines))


def _zip(dst):
    zpath = dst + ".zip"
    if os.path.isfile(zpath):
        os.remove(zpath)
    base = os.path.dirname(dst)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(dst):
            for n in files:
                full = os.path.join(root, n)
                z.write(full, os.path.relpath(full, base))
    return zpath


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(ROOT), PKG_NAME),
                    help="输出目录（默认：项目同级的 %s）" % PKG_NAME)
    ap.add_argument("--allow-missing-xt", action="store_true",
                    help="x_t 不齐也继续打包（目标机降级会失败）")
    ap.add_argument("--no-zip", action="store_true", help="只生成文件夹，不压缩")
    args = ap.parse_args()

    _log("== HYT-NX 移植包打包 ==")
    _log("[项目根] %s" % ROOT)
    _health_check(args.allow_missing_xt)

    dst = os.path.abspath(args.out)
    _prepare_dst(dst)
    _log("[输出]   %s" % dst)

    _copy_whitelist(dst)
    _build_convert(dst)
    _write_manifest(dst)

    n_files = 0
    total = 0
    for root, _dirs, files in os.walk(dst):
        for n in files:
            n_files += 1
            total += os.path.getsize(os.path.join(root, n))
    _log("[完成] %d 个文件 / %.1f MB" % (n_files, total / 1024.0 / 1024.0))

    if not args.no_zip:
        z = _zip(dst)
        _log("[压缩] %s  (%.1f MB)" % (z, os.path.getsize(z) / 1024.0 / 1024.0))

    _log("")
    _log("下一步：")
    _log("  1. 把包/压缩包拷到老旧机器，解压到**纯英文路径**（如 C:\\nxpkg\\）")
    _log("  2. 目标机双击「一键降级标准件.bat」完成标准件降级")
    _log("  3. NX 里播放 batch_smoke.py 验收")


if __name__ == "__main__":
    main()
