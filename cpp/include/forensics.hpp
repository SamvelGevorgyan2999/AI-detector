#pragma once

#include <cstdint>
#include <map>
#include <string>
//#include <vector>

namespace origincheck {

struct ForensicFeatures {
    double laplacian_var = 0.0;
    double noise_residual_std = 0.0;
    double fft_high_ratio = 0.0;
    double fft_peakiness = 0.0;
    double saturation_mean = 0.0;
    double saturation_std = 0.0;
    double channel_corr = 0.0;
    double gradient_entropy = 0.0;
    double blockiness = 0.0;
    double edge_density = 0.0;
};

ForensicFeatures extract_features(const std::uint8_t* rgb, int height, int width);

std::map<std::string, double> features_to_map(const ForensicFeatures& features);

}  // namespace origincheck