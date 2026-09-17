@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title HYT-NX 移植包打包（在开发机 NX2312 上运行）

rem ==================================================================
rem  一键生成"老旧机器移植包"。双击本文件即可。
rem
rem  第 1 步  导出  stdparts\*.prt  -^>  <工具目录>\xt\*.x_t     （需要 NX）
rem  第 2 步  回读校验 .x_t 有没有丢东西                        （需要 NX）
rem  第 3 步  生成移植包并压缩成 zip                            （需要 Python 3）
rem
rem  参数 ：
rem    --skip-export        复用现有的 xt\，不重新导出
rem    --skip-verify        跳过回读校验
rem    其他参数             原样转给 make_portable_pkg.py
rem                         例如 --allow-missing-xt --out D:\pkg --no-zip
rem  环境变量 ：
rem    HYT_NOPAUSE=1        跑完不等按键（自动化用）
rem
rem  【为什么这个文件也要存成 GBK + CRLF】
rem  cmd.exe 按本地代码页（中文 Windows = 936/GBK）逐字节读 .bat。
rem  存成 UTF-8 会让解析器丢同步，报满屏 "'EV' 不是内部或外部命令"。
rem  所以本文件用 GBK 存，并在开头 chcp 936。
rem  另外 ：兄弟目录名叫"NX向下兼容工具"（中文），所以这里不写它的名字，
rem  改用通配符 %HERE%..\NX* 去定位，避免在 .bat 里出现中文路径字面量。
rem ==================================================================

set "HERE=%~dp0"

rem ---- 定位兄弟目录（名字是中文，所以用通配符找）
set "TOOL="
for /d %%D in ("%HERE%..\NX*") do if not defined TOOL set "TOOL=%%~fD"
if not defined TOOL (
  echo [错误] 在本文件旁边找不到 NX* 开头的工具目录：
  echo        %HERE%
  if not "%HYT_NOPAUSE%"=="1" pause
  exit /b 1
)
set "XT=%TOOL%\xt"
set "LOG1=%TOOL%\export_log.txt"
set "LOG2=%TOOL%\verify.txt"

rem ---- 把本脚本自己的参数和要转给 py 的参数分开
set "SKIP_EXPORT="
set "SKIP_VERIFY="
set "PASSARGS="
for %%A in (%*) do (
  if /i "%%~A"=="--skip-export" (set "SKIP_EXPORT=1") else if /i "%%~A"=="--skip-verify" (set "SKIP_VERIFY=1") else set "PASSARGS=!PASSARGS! %%A"
)

echo ============================================================
echo  HYT-NX ：生成"老旧机器移植包"
echo ============================================================
echo.
echo  工具目录 ：%TOOL%
echo  项目目录 ：%HERE%..
echo.

rem ---- 找 NX 的 run_journal.exe
rem  注意 ：开发机要的是【最高】版本（要能打开 2312 格式的 stdparts 母版），
rem  这跟目标老机器"选最低版本"的规则正好相反，别改成一样的。
set "RUNNER="
if defined UGII_BASE_DIR if exist "%UGII_BASE_DIR%\NXBIN\run_journal.exe" set "RUNNER=%UGII_BASE_DIR%\NXBIN\run_journal.exe"
if not defined RUNNER for %%D in ("C:\Program Files\Siemens\NX2312" "C:\Program Files\Siemens\NX2306" "C:\Program Files\Siemens\NX2206" "C:\Program Files\Siemens\NX2007" "C:\Program Files\Siemens\NX 12.0" "C:\Program Files\Siemens\NX 11.0" "C:\Program Files\Siemens\NX 10.0" "C:\Program Files\Siemens\NX 8.0") do if not defined RUNNER if exist "%%~D\NXBIN\run_journal.exe" set "RUNNER=%%~D\NXBIN\run_journal.exe"
if defined RUNNER echo  NX 程序 ：%RUNNER%
if not defined RUNNER echo  NX 程序 ：没找到
echo.

set /a NXT=0
if exist "%XT%\*.x_t" for %%F in ("%XT%\*.x_t") do set /a NXT+=1
echo  现有 x_t ：%NXT% 个（应为 14 个）
echo.

rem ---- 第 1 步 ：导出
if defined SKIP_EXPORT goto :cv_verify
if not defined RUNNER goto :cv_no_nx
echo [1/3] 正在用 NX 把 .prt 导出成 .x_t ...（可能要几分钟）
"%RUNNER%" "%TOOL%\export_xt.py"
if exist "%LOG1%" (
  echo       ---- export_log.txt 摘要 ----
  findstr /c:"DONE" "%LOG1%"
  findstr /c:"FAIL" "%LOG1%"
) else (
  echo       [提醒] 没生成 export_log.txt
)
goto :cv_verify

:cv_no_nx
echo [1/3] 跳过导出 ：没找到 NX 的 run_journal.exe
echo       可以手工做 ：打开 NX，菜单 文件 -^> 执行 -^> NX Open ，
echo       然后选中  %TOOL%\export_xt.py
goto :cv_verify

rem ---- 第 2 步 ：校验
:cv_verify
echo.
if defined SKIP_VERIFY goto :cv_pack
if not defined RUNNER goto :cv_pack
echo [2/3] 正在回读校验 .x_t ...
"%RUNNER%" "%TOOL%\verify_import.py"
if exist "%LOG2%" (
  echo       ---- verify.txt 摘要 ----
  findstr /c:"problems" "%LOG2%"
  findstr /c:"ABORT" "%LOG2%"
) else (
  echo       [提醒] 没生成 verify.txt
)

rem ---- 第 3 步 ：打包
:cv_pack
echo.
echo [3/3] 正在生成移植包 ...
if not exist "%HERE%make_portable_pkg.py" (
  echo [错误] 本文件旁边没有 make_portable_pkg.py
  if not "%HYT_NOPAUSE%"=="1" pause
  exit /b 1
)
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  echo [错误] PATH 里没有 Python 3
  echo        前两步已经做完了，可以手工收尾 ：
  echo            python "%HERE%make_portable_pkg.py"
  if not "%HYT_NOPAUSE%"=="1" pause
  exit /b 1
)

rem 让 Python 也按 GBK 输出，跟本脚本的编码保持一致
rem （否则重定向到文件时，bat 是 GBK、Python 是 UTF-8，混在一起没法看）
set "PYTHONIOENCODING=gbk"
%PY% "%HERE%make_portable_pkg.py" !PASSARGS!
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [错误] 打包失败，退出码 %RC%
  if not "%HYT_NOPAUSE%"=="1" pause
  exit /b %RC%
)

echo ============================================================
echo  完成。请把  HYT-NX-portable.zip  拷到老旧机器，
echo  解压到【全英文】路径（例如 C:\nxpkg\），
echo  然后双击包里面的"一键降级标准件.bat"。
echo ============================================================
if not "%HYT_NOPAUSE%"=="1" pause
exit /b 0
