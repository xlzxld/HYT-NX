# make verify —— AGENTS.md §2 验证门禁的机械执法层（闭环验证的唯一入口）
# 用法：按目标项目 AGENTS.md §2 登记的命令填充以下变量，然后执行 `make verify`
# §2 登记"无"的项：对应变量填 skip（留空 = 未配置，报错退出，防误配静默放行）
# 增量检查（存量问题大仓推荐）：make verify CHANGED="$(git diff --name-only)"
#   —— fmt-check 与 lint 均只对 CHANGED 列出的文件执行；lint 只取其中的 .py
#   （ruff 显式收到非 .py 文件会按 invalid-syntax 报错, 并不会自动跳过）
FMT_CHECK_CMD ?= skip
LINT_CMD ?= python -m ruff check
TEST_CMD ?= python nx_extrude_runner.py --selftest
BUILD_CMD ?= skip
CHANGED ?=

# CHANGED 通常来自 $(git diff --name-only)，是**多行**文本。recipe 里不加引号
# 直接展开时，多行的最后一行会跟续行末尾的 `else skip; fi` 拼成
# `...py; else skip; fi`，/bin/sh 报 Syntax error、make 退 2 → fmt-check 恒定
# 失败、gate CI 恒红（2026-09-17 用 dash 逐字节复现坐实；main 两次 CI 同样红）。
# 故统一把换行归一化成空格：CHANGED_LINE 才是可安全展开进 shell 的单行形态。
# ⚠ define 的值 = 中间各行 + 换行，且 make 会去掉**最后一个**换行 —— 下面必须
#   留**两个**空行，_NL 才是一个换行符；只留一个空行得到空串，subst 静默失效
#   （2026-09-17 踩过：CI 仍报同样的错，仅行号从 Makefile:18 变成 :28）。
define _NL


endef
CHANGED_LINE = $(subst $(_NL), ,$(CHANGED))

.PHONY: verify fmt-check lint test build
verify: fmt-check lint test build

fmt-check:
	@if [ -z "$(FMT_CHECK_CMD)" ]; then echo "FMT_CHECK_CMD 未配置（见 enforcement/README.md）"; exit 1; fi
	@if [ "$(FMT_CHECK_CMD)" = "skip" ]; then echo "skip: fmt-check（§2 登记“无”）"; \
	elif [ -n "$(CHANGED_LINE)" ]; then $(FMT_CHECK_CMD) $(CHANGED_LINE); \
	else $(FMT_CHECK_CMD); fi

lint:
	@if [ -z "$(LINT_CMD)" ]; then echo "LINT_CMD 未配置（见 enforcement/README.md）"; exit 1; fi
	@if [ "$(LINT_CMD)" = "skip" ]; then echo "skip: lint（§2 登记“无”）"; \
	elif [ -n "$(CHANGED_LINE)" ]; then \
	  CHANGED_PY=$$(printf "%s\n" $(CHANGED_LINE) | grep "\.py$$" | tr "\n" " "); \
	  if [ -n "$$CHANGED_PY" ]; then $(LINT_CMD) $$CHANGED_PY; \
	  else echo "skip: lint（本次改动无 .py 文件）"; fi; \
	else $(LINT_CMD); fi

test:
	@if [ -z "$(TEST_CMD)" ]; then echo "TEST_CMD 未配置（见 enforcement/README.md）"; exit 1; fi
	@if [ "$(TEST_CMD)" = "skip" ]; then echo "skip: test（§2 登记“无”）"; else $(TEST_CMD); fi

build:
	@if [ "$(BUILD_CMD)" = "skip" ]; then echo "skip: no build configured"; else $(BUILD_CMD); fi
