# Frogmouth 0.9.3 兼容性验证

验证日期：2026-09-29。工作区：`/home/capri/Sources/frogmouth`。

## 安装与依赖

已将项目元数据迁移到标准 `[project]` 配置，保留版本 `0.9.3`、
Capri XXI 的维护者信息，以及用户指定的全部 classifiers。
`uv sync --locked` 能正常安装应用和开发依赖，不再出现缺少 `requires-python`
的警告。`uv.lock` 纳入版本管理范围，实际依赖包括 HTTPX 0.28.1、Textual 8.2.8。

`.venv` 绑定 `/home/capri/.local/python/3.15/bin/python3.15`，
不再经过可能切换的 `selected` 路径。版本号从已安装项目元数据读取。
旧的 `PKG-INFO` 是上游 0.9.2 发行文件，已移除；新的元数据由构建工具生成。
已核对 wheel 中维护者、Python 要求和 classifiers，后者与项目声明完全一致。

## 测试结果

所有测试均启用 `-X warn_default_encoding -W error`。测试配置还将 pytest
捕获的警告视为错误，没有设置忽略警告规则。测试通过临时 XDG 目录隔离配置、
历史和书签，真实 HTTP 测试仅访问临时本地服务器。

| Python 环境 | JIT 配置 | 结果 |
| --- | --- | --- |
| 本机 3.14.7，debug 构建 | 保持原环境 | 56 项通过 |
| 本机 3.15.0rc2，debug 构建 | `PYTHON_JIT=0` | 56 项通过 |
| uv 提供的标准 3.15.0rc1，非 debug 构建 | 原生默认，JIT 关闭 | 56 项通过 |
| 同一标准 3.15.0rc1 | `PYTHON_JIT=1` | 56 项通过 |

覆盖本地和远程 Markdown、中文内容、HTTP 重定向和相对链接、HTTP 错误、
导航切换与焦点、主题持久化、帮助与关于对话框、书签保存和取消、命令参数大小写、
历史删除后的前进后退，以及配置、历史和书签的读写。

此外，真实终端 PTY 下已完成启动、读取 README 和 Ctrl+Q 退出。
`uv build` 成功生成源码包与 wheel；将 wheel 安装到独立项目虚拟环境后，
使用 `python -I` 排除工作区源码的影响，中文 Markdown 界面冒烟测试通过。
`uv pip check` 未发现依赖冲突。

Python 3.15 的验证对象是上述两个候选发布版本，尚未验证 3.15 最终正式版。
没有执行 GitHub、GitLab、Bitbucket 或 Codeberg 公网服务的端到端测试；
其中 GitHub 和 Codeberg 快捷命令的协议与错误路径通过模拟 HTTP 响应测试。

## 静态检查

以下命令全部通过：Ruff 无诊断，Mypy 检查 32 个源码文件无问题，
Pylint 为 10.00/10，Pyright 为 0 errors、0 warnings。

```sh
uv run ruff check .
uv run mypy
uv run python -X frozen_modules=on -m pylint frogmouth
uv run pyright
git diff --check
```

Mypy 2.3.1 的编译版本在本机两套 debug 解释器中触发 CPython 字典断言退出。
项目使用 uv 的 `no-binary-package` 和 `MYPY_USE_MYPYC=0`，安装其官方纯 Python
版本；该版本已通过检查。这没有改变被检查的代码或降低检查要求。
相关配置依据 [uv 文档](https://docs.astral.sh/uv/reference/settings/#no-binary-package)
和 [Mypy 构建脚本](https://github.com/python/mypy/blob/master/setup.py)。

本机 debug 解释器默认不使用冻结的标准库模块，Astroid 4.0.4 在这种配置下
误报 `collections.abc` 无法导入。Pylint 命令使用 Python 原生的
`-X frozen_modules=on` 解决这项识别问题，没有禁用 `import-error`。
该选项见 [Python 文档](https://docs.python.org/3.15/using/cmdline.html#cmdoption-X)。

## 本机复现命令与 JIT 边界

本机环境继承了 `PYTHON_JIT=1`。定制的 3.15.0rc2 使用 `--with-pydebug`、
`--enable-experimental-jit=yes` 等构建选项，曾在测试过程中以 SIGABRT 退出。
关闭该进程的 JIT 后，最终全部 56 项测试通过。同一套测试在标准 3.15.0rc1
开启 JIT 时也通过，因此目前只能将异常限定到观察到的定制构建与运行配置，
尚未定位到具体 CPython 缺陷，不能据此认定所有 Python 3.15 JIT 都有问题。

使用本机这套 3.15.0rc2 运行应用和回归测试：

```sh
PYTHON_JIT=0 uv run frogmouth README.md
PYTHON_JIT=0 uv run python -X warn_default_encoding -W error -m pytest -q
```

Python 3.14 的本地构建依赖额外共享库，必须保留原有库搜索路径：

```sh
LD_LIBRARY_PATH=/home/capri/.local/python/3.14/lib:$LD_LIBRARY_PATH \
    .venv314/bin/python -X warn_default_encoding -W error -m pytest -q
```

独立标准 Python 3.15 环境的对照命令：

```sh
env -u PYTHON_JIT .venv315standard/bin/python -X warn_default_encoding -W error -m pytest -q
PYTHON_JIT=1 .venv315standard/bin/python -X warn_default_encoding -W error -m pytest -q
```

这些变量只对相应进程生效。没有修改全局 Python、共享库或 JIT 配置，
没有在应用中屏蔽警告或替换标准库实现。

本地原始记录位于忽略目录 `build/validation/`，不随源码提交：

- `python314.log`
- `python315-no-jit.log`
- `python315-standard-default.log`
- `python315-standard-jit.log`
- `python315-jit-crash.log`（早期 46 项测试阶段捕获的定制构建崩溃）
