#define PY_SSIZE_T_CLEAN

#include "../include/forensics.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <stdexcept>

namespace py = pybind11;

PYBIND11_MODULE(_forensics, m) {

    m.doc() = "OriginCheck C++ image forensics engine";

    m.def(
        "extract_features",
        [](const py::array_t<
            std::uint8_t,
            py::array::c_style | py::array::forcecast
        >& image) {

            const auto shape = image.shape();

            if (image.ndim() != 3 || shape[2] != 3) {
                throw std::invalid_argument(
                    "expected an RGB array with shape (H, W, 3)"
                );
            }

            const int height =
                static_cast<int>(shape[0]);

            const int width =
                static_cast<int>(shape[1]);

            const auto* data = image.data();

            const auto features =
                origincheck::extract_features(
                    data,
                    height,
                    width
                );

            return origincheck::features_to_map(features);
        },
        py::arg("image"),
        "Extract forensic features from a contiguous uint8 RGB image."
    );
}