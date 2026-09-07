# Build the optional C++ extension:
#   python setup.py build_ext --inplace
#
# The GUI runs without this module; Python forensics is used instead.

import importlib
import importlib.util

from setuptools import Extension, setup  # type: ignore[import-not-found]

_pybind11_spec = importlib.util.find_spec("pybind11")
if _pybind11_spec is None:
    raise RuntimeError(
        "pybind11 is required to build the native forensics extension. "
        "Install it with: python -m pip install pybind11"
    )

try:
    _pybind11_setup_helpers = importlib.import_module("pybind11.setup_helpers")
    Pybind11Extension = _pybind11_setup_helpers.Pybind11Extension
    build_ext = _pybind11_setup_helpers.build_ext
except ModuleNotFoundError:
    Pybind11Extension = Extension
    from setuptools.command.build_ext import build_ext  # type: ignore[import-not-found]


def _make_extension():
    if Pybind11Extension is Extension:
        return Pybind11Extension(
            "origincheck._forensics",
            ["cpp/src/forensics.cpp", "cpp/src/bindings.cpp"],
            include_dirs=["cpp/include"],
            extra_compile_args=["-std=c++17"],
        )
    return Pybind11Extension(
        "origincheck._forensics",
        ["cpp/src/forensics.cpp", "cpp/src/bindings.cpp"],
        include_dirs=["cpp/include"],
        extra_compile_args=["-std=c++17"],
    )


ext_modules = [_make_extension()]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
