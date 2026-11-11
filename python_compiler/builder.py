"""Build-time archive, xxd header, and C launcher generation (standard library only)."""

import keyword
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union


EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox",
    "build", "dist", "node_modules",
}


@dataclass(frozen=True)
class BuildResult:
    archive: Path
    header: Path
    launcher: Path
    executable: Path


def _entry_source(entry_point: str) -> str:
    parts = entry_point.split(":")
    if len(parts) != 2:
        raise ValueError("Entry point must have the form package.module:function")
    module, function = parts
    if not all(
        part.isidentifier() and not keyword.iskeyword(part)
        for name in (module, function) for part in name.split(".")
    ):
        raise ValueError("Entry point must contain valid Python module and function names")
    return (
        "import importlib\n"
        "import sys\n"
        f"_entry = importlib.import_module({module!r})\n"
        f"for _part in {function.split('.')!r}:\n"
        "    _entry = getattr(_entry, _part)\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(_entry())\n"
    )


def build(
    source: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    *,
    name: Optional[str] = None,
    entry_point: Optional[str] = None,
    cc: Optional[str] = None,
    cflags: Sequence[str] = (),
) -> BuildResult:
    """Create a .pyz, xxd-generated .h, .c, and executable in output_dir.

    The source directory must be an import root, with __main__.py unless an
    entry_point is supplied. Existing build artifacts in output_dir are replaced.
    """
    if sys.platform != "linux":
        raise ValueError("Building the RAM-backed launcher requires Linux")
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f"Project directory does not exist: {source}")
    name = source.name if name is None else name
    if not name or name in {".", ".."} or any(c in name for c in "/\\\0"):
        raise ValueError("Name must be a single nonempty filename")
    if name in {"launcher.c", "embedded_pyz.h"}:
        raise ValueError("Name conflicts with a generated source artifact")
    if not entry_point and not (source / "__main__.py").is_file():
        raise ValueError("Project needs __main__.py or --entry-point package.module:function")
    main_source = _entry_source(entry_point) if entry_point else None
    output = Path(output_dir).resolve() if output_dir is not None else source / "dist" / name
    if output == source or output in source.parents:
        raise ValueError("Output directory must not be the source directory or its ancestor")
    compiler = shlex.split(cc if cc is not None else os.environ.get("CC", "cc"))
    if not compiler or not shutil.which(compiler[0]):
        raise ValueError("C compiler not found; install one or provide --cc")
    xxd = shutil.which("xxd")
    if xxd is None:
        raise ValueError("xxd not found; install xxd before building")

    # Collect before creating artifacts; never recurse into the output directory.
    def walk_error(error: OSError) -> None:
        raise error

    files = []
    for root, dirs, filenames in os.walk(source, followlinks=False, onerror=walk_error):
        root = Path(root)
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.endswith(".egg-info")
            and (root / d).resolve() != output and not (root / d).is_symlink()
        )
        for filename in sorted(filenames):
            path = root / filename
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Symlinked files are unsupported: {path}")
            if main_source is not None and path == source / "__main__.py":
                continue
            files.append(path)

    output.mkdir(parents=True, exist_ok=True)
    result = BuildResult(
        output / f"{name}.pyz", output / "embedded_pyz.h",
        output / "launcher.c", output / name,
    )
    with zipfile.ZipFile(result.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Explicit directory entries let zipimport discover namespace packages.
        directories = {
            parent.as_posix() + "/"
            for path in files
            for parent in path.relative_to(source).parents
            if parent != Path(".")
        }
        for directory in sorted(directories):
            archive.writestr(directory, b"")
        for path in files:
            archive.write(path, path.relative_to(source).as_posix())
        if main_source is not None:
            archive.writestr("__main__.py", main_source)
    with result.header.open("wb") as header:
        subprocess.run(
            [xxd, "-i", "-n", "embedded_pyz", str(result.archive)],
            stdout=header, check=True,
        )
    shutil.copyfile(Path(__file__).with_name("launcher.c"), result.launcher)
    subprocess.run(
        [*compiler, "-std=c11", "-O2", "-Wall", "-Wextra", *cflags,
         str(result.launcher), "-o", str(result.executable)],
        check=True,
    )
    return result
