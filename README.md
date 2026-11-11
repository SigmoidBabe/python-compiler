# Python project compiler

Package a Python project directory into a `.pyz`, convert it into a C header
using `xxd`, and compile a Linux executable that embeds the archive. Choose the
Python environment when running the executable.

The launcher uses Linux `memfd_create` and executes Python with a
`/proc/self/fd/...` archive path. It creates no runtime temporary archive on disk.
The memory-backed descriptor stays open so Python can import modules throughout
the application's lifetime. Linux can swap memory-backed pages; this is not a
guarantee that application bytes can never reach swap storage.

## Requirements and installation

- Build host: Linux, Python 3.9+, `xxd`, and a C compiler such as GCC or Clang.
- Runtime: Linux with `memfd_create` and mounted `/proc`, and a compatible Python
  environment with the application's dependencies installed.
- Python must support zlib to read the compressed archive.

Install from this repository:

```bash
python -m pip install .
```

Or run the builder directly from this checkout using `python -m python_compiler`.

## Build and run

For a directory with a root `__main__.py`:

```text
my_project/
    __main__.py
    mypackage/
        __init__.py
        cli.py
```

```bash
python-compiler ./my_project --output-dir ./dist/myapp --name myapp
./dist/myapp/myapp /path/to/venv -- --config 'a file.json'
```

The first binary argument is a virtual environment directory (the launcher uses
`ENV/bin/python`) or a Python executable path:

```bash
./dist/myapp/myapp /usr/bin/python3 -- --help
```

The optional `--` after the environment is consumed by the launcher; subsequent
arguments are passed unchanged to the application. Without it, all arguments
after the environment are application arguments. Executable names are treated
as paths, not searched through `PATH`. Relative paths work from the current
working directory. The launcher replaces itself with Python, preserving its
exit status and normal signal handling. It does not invoke a shell or `sudo`.

If the directory lacks `__main__.py`, supply an entry point:

```bash
python-compiler ./my_project -n myapp -m mypackage.cli:main
```

The function is called without arguments; it can read `sys.argv` as usual. Its
return value is passed to `sys.exit`. An explicit entry point replaces any root
`__main__.py` in the archive. For a `src` layout, pass the import root:

```bash
python-compiler ./my_project/src -n myapp -m mypackage.cli:main
```

Each build produces these files (existing files with these names are replaced):

```text
dist/myapp/
    myapp.pyz
    embedded_pyz.h
    launcher.c
    myapp
```

By default, output goes to `SOURCE/dist/NAME`. Build artifacts are written to disk;
the RAM-backed behavior applies when running the resulting executable.
`cpp_example.c` shows the same launcher, including the generated
`embedded_pyz.h`. You can also compile that example manually with the generated
header's directory on the include path:

```bash
cc -std=c11 -O2 -I ./dist/myapp cpp_example.c -o ./dist/myapp/example
```

Compiler selection and additional flags:

```bash
python-compiler ./my_project --cc clang --cflag=-g
```

## Python API

```python
from python_compiler import build

result = build(
    "./my_project",
    "./dist/myapp",
    name="myapp",
    entry_point="mypackage.cli:main",
)
print(result.executable)
```

## Packaging limits

This bundles source and project files, not Python itself or installed dependencies.
The executable is compiled for the build compiler's target platform and architecture.
Use a compatible runtime Python version for your application's syntax and dependencies.

The source must be an import root. The builder does not install the project or
interpret `pyproject.toml` entry points. It skips version control directories,
common virtual environments and caches, `build`, `dist`, `node_modules`,
`*.egg-info` directories, and `.pyc`/`.pyo` files. The selected output directory
is also excluded. Symlink directories are skipped and symlink files are rejected.
Other files are bundled, so keep credentials and unrelated files out of the
source directory. Existing output files are overwritten only after source and
tool validation, but a failed build can leave partial artifacts.

Native extension modules (`.so`) cannot be imported directly from a zip archive;
install those dependencies in the runtime environment. Code that opens resources
using filesystem paths derived from `__file__` needs adjustment for zip loading;
use zip-compatible resource APIs such as `importlib.resources` for package data.
The runtime script path is `/proc/self/fd/NUMBER`, and the launcher's current
working directory is preserved. Application code and dependencies can still
write files themselves. Embedding is packaging, not source encryption.
