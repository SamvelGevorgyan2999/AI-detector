#include "../include/forensics.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <vector>

namespace origincheck {
namespace {

constexpr double kPi = 3.14159265358979323846;

inline int clampi(int value, int lo, int hi) {
    return std::max(lo, std::min(hi, value));
}

std::vector<double> to_gray(const std::uint8_t* rgb, int height, int width) {
    std::vector<double> gray(static_cast<std::size_t>(height) * static_cast<std::size_t>(width));
    const std::size_t n = gray.size();
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint8_t r = rgb[i * 3];
        const std::uint8_t g = rgb[i * 3 + 1];
        const std::uint8_t b = rgb[i * 3 + 2];
        gray[i] = 0.299 * r + 0.587 * g + 0.114 * b;
    }
    return gray;
}

double mean_of(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }
    double sum = 0.0;
    for (double v : values) {
        sum += v;
    }
    return sum / static_cast<double>(values.size());
}

double std_of(const std::vector<double>& values, double mean) {
    if (values.size() < 2) {
        return 0.0;
    }
    double acc = 0.0;
    for (double v : values) {
        const double d = v - mean;
        acc += d * d;
    }
    return std::sqrt(acc / static_cast<double>(values.size()));
}

double laplacian_variance(const std::vector<double>& gray, int height, int width) {
    if (height < 3 || width < 3) {
        return 0.0;
    }
    std::vector<double> vals;
    vals.reserve(static_cast<std::size_t>(height - 2) * static_cast<std::size_t>(width - 2));
    for (int y = 1; y < height - 1; ++y) {
        for (int x = 1; x < width - 1; ++x) {
            const double c = gray[y * width + x];
            const double lap =
                gray[(y - 1) * width + x] + gray[(y + 1) * width + x] + gray[y * width + (x - 1)] +
                gray[y * width + (x + 1)] - 4.0 * c;
            vals.push_back(lap);
        }
    }
    const double m = mean_of(vals);
    return std_of(vals, m);
}

double noise_residual_std(const std::vector<double>& gray, int height, int width) {
    if (height < 5 || width < 5) {
        return 0.0;
    }
    std::vector<double> residual;
    residual.reserve(static_cast<std::size_t>(height) * static_cast<std::size_t>(width));
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            double acc = 0.0;
            int count = 0;
            for (int dy = -2; dy <= 2; ++dy) {
                for (int dx = -2; dx <= 2; ++dx) {
                    const int yy = clampi(y + dy, 0, height - 1);
                    const int xx = clampi(x + dx, 0, width - 1);
                    acc += gray[yy * width + xx];
                    ++count;
                }
            }
            residual.push_back(gray[y * width + x] - acc / static_cast<double>(count));
        }
    }
    const double m = mean_of(residual);
    return std_of(residual, m);
}

void fft1d(std::vector<std::complex<double>>& a, bool inverse) {
    const std::size_t n = a.size();
    if (n <= 1) {
        return;
    }

    std::size_t j = 0;
    for (std::size_t i = 1; i < n; ++i) {
        std::size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            std::swap(a[i], a[j]);
        }
    }

    for (std::size_t len = 2; len <= n; len <<= 1) {
        const double ang = 2.0 * kPi / static_cast<double>(len) * (inverse ? 1.0 : -1.0);
        const std::complex<double> wlen(std::cos(ang), std::sin(ang));
        for (std::size_t i = 0; i < n; i += len) {
            std::complex<double> w(1.0, 0.0);
            for (std::size_t k = 0; k < len / 2; ++k) {
                const std::complex<double> u = a[i + k];
                const std::complex<double> v = a[i + k + len / 2] * w;
                a[i + k] = u + v;
                a[i + k + len / 2] = u - v;
                w *= wlen;
            }
        }
    }

    if (inverse) {
        for (auto& x : a) {
            x /= static_cast<double>(n);
        }
    }
}

std::pair<double, double> fft_metrics(const std::vector<double>& gray, int height, int width) {
    constexpr int n = 256;
    std::vector<std::complex<double>> grid(static_cast<std::size_t>(n) * n);

    for (int y = 0; y < n; ++y) {
        const int src_y = static_cast<int>(std::floor((y + 0.5) * height / n));
        const int yy = clampi(src_y, 0, height - 1);
        for (int x = 0; x < n; ++x) {
            const int src_x = static_cast<int>(std::floor((x + 0.5) * width / n));
            const int xx = clampi(src_x, 0, width - 1);
            grid[y * n + x] = gray[yy * width + xx];
        }
    }

    std::vector<std::complex<double>> row(n);
    for (int y = 0; y < n; ++y) {
        for (int x = 0; x < n; ++x) {
            row[x] = grid[y * n + x];
        }
        fft1d(row, false);
        for (int x = 0; x < n; ++x) {
            grid[y * n + x] = row[x];
        }
    }
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            row[y] = grid[y * n + x];
        }
        fft1d(row, false);
        for (int y = 0; y < n; ++y) {
            grid[y * n + x] = row[y];
        }
    }

    double total = 0.0;
    double high = 0.0;
    double peak = 0.0;
    std::vector<double> mags;
    mags.reserve(static_cast<std::size_t>(n) * n);

    for (int y = 0; y < n; ++y) {
        const int fy = std::min(y, n - y);
        for (int x = 0; x < n; ++x) {
            const int fx = std::min(x, n - x);
            if (fx == 0 && fy == 0) {
                continue;
            }
            const double mag = std::abs(grid[y * n + x]);
            mags.push_back(mag);
            total += mag;
            if (fx > n / 4 || fy > n / 4) {
                high += mag;
            }
            peak = std::max(peak, mag);
        }
    }

    const double mean_mag = mean_of(mags);
    const double peakiness = (mean_mag > 1e-9) ? (peak / mean_mag) : 0.0;
    const double ratio = (total > 1e-9) ? (high / total) : 0.0;
    return {ratio, peakiness};
}

std::pair<double, double> saturation_stats(const std::uint8_t* rgb, int height, int width) {
    const int n = height * width;
    std::vector<double> sats;
    sats.reserve(n);
    for (int i = 0; i < n; ++i) {
        const double r = rgb[i * 3] / 255.0;
        const double g = rgb[i * 3 + 1] / 255.0;
        const double b = rgb[i * 3 + 2] / 255.0;
        const double mx = std::max(r, std::max(g, b));
        const double mn = std::min(r, std::min(g, b));
        const double sat = (mx > 1e-9) ? ((mx - mn) / mx) : 0.0;
        sats.push_back(sat);
    }
    const double m = mean_of(sats);
    return {m, std_of(sats, m)};
}

double channel_correlation(const std::uint8_t* rgb, int height, int width) {
    const int n = height * width;
    if (n < 2) {
        return 0.0;
    }
    double mean_r = 0.0;
    double mean_g = 0.0;
    double mean_b = 0.0;
    for (int i = 0; i < n; ++i) {
        mean_r += rgb[i * 3];
        mean_g += rgb[i * 3 + 1];
        mean_b += rgb[i * 3 + 2];
    }
    mean_r /= n;
    mean_g /= n;
    mean_b /= n;

    auto corr = [&](int c0, int c1, double m0, double m1) {
        double num = 0.0;
        double d0 = 0.0;
        double d1 = 0.0;
        for (int i = 0; i < n; ++i) {
            const double a = rgb[i * 3 + c0] - m0;
            const double b = rgb[i * 3 + c1] - m1;
            num += a * b;
            d0 += a * a;
            d1 += b * b;
        }
        const double den = std::sqrt(d0 * d1);
        return (den > 1e-9) ? (num / den) : 0.0;
    };

    const double rg = corr(0, 1, mean_r, mean_g);
    const double gb = corr(1, 2, mean_g, mean_b);
    const double br = corr(2, 0, mean_b, mean_r);
    return (rg + gb + br) / 3.0;
}

std::pair<double, double> gradient_stats(const std::vector<double>& gray, int height, int width) {
    if (height < 2 || width < 2) {
        return {0.0, 0.0};
    }
    constexpr int bins = 64;
    std::vector<int> hist(bins, 0);
    int edges = 0;
    int total = 0;
    for (int y = 0; y < height - 1; ++y) {
        for (int x = 0; x < width - 1; ++x) {
            const double dx = gray[y * width + (x + 1)] - gray[y * width + x];
            const double dy = gray[(y + 1) * width + x] - gray[y * width + x];
            const double mag = std::sqrt(dx * dx + dy * dy);
            int bin = static_cast<int>(mag / 8.0);
            bin = clampi(bin, 0, bins - 1);
            hist[bin] += 1;
            ++total;
            if (mag > 18.0) {
                ++edges;
            }
        }
    }
    double entropy = 0.0;
    if (total > 0) {
        for (int c : hist) {
            if (c <= 0) {
                continue;
            }
            const double p = static_cast<double>(c) / static_cast<double>(total);
            entropy -= p * std::log2(p);
        }
    }
    const double density = (total > 0) ? (static_cast<double>(edges) / static_cast<double>(total)) : 0.0;
    return {entropy, density};
}

double jpeg_blockiness(const std::vector<double>& gray, int height, int width) {
    if (height < 16 || width < 16) {
        return 0.0;
    }
    double boundary = 0.0;
    int boundary_n = 0;
    double interior = 0.0;
    int interior_n = 0;

    for (int y = 0; y < height; ++y) {
        for (int x = 1; x < width; ++x) {
            const double diff = std::abs(gray[y * width + x] - gray[y * width + (x - 1)]);
            if (x % 8 == 0) {
                boundary += diff;
                ++boundary_n;
            } else {
                interior += diff;
                ++interior_n;
            }
        }
    }
    for (int x = 0; x < width; ++x) {
        for (int y = 1; y < height; ++y) {
            const double diff = std::abs(gray[y * width + x] - gray[(y - 1) * width + x]);
            if (y % 8 == 0) {
                boundary += diff;
                ++boundary_n;
            } else {
                interior += diff;
                ++interior_n;
            }
        }
    }

    const double b = (boundary_n > 0) ? (boundary / boundary_n) : 0.0;
    const double i = (interior_n > 0) ? (interior / interior_n) : 1.0;
    return b / (i + 1e-6);
}

}  // namespace

ForensicFeatures extract_features(const std::uint8_t* rgb, int height, int width) {
    ForensicFeatures out;
    if (rgb == nullptr || height <= 0 || width <= 0) {
        return out;
    }

    const auto gray = to_gray(rgb, height, width);
    out.laplacian_var = laplacian_variance(gray, height, width);
    out.noise_residual_std = noise_residual_std(gray, height, width);

    const auto fft = fft_metrics(gray, height, width);
    out.fft_high_ratio = fft.first;
    out.fft_peakiness = fft.second;

    const auto sat = saturation_stats(rgb, height, width);
    out.saturation_mean = sat.first;
    out.saturation_std = sat.second;
    out.channel_corr = channel_correlation(rgb, height, width);

    const auto grad = gradient_stats(gray, height, width);
    out.gradient_entropy = grad.first;
    out.edge_density = grad.second;
    out.blockiness = jpeg_blockiness(gray, height, width);
    return out;
}

std::map<std::string, double> features_to_map(const ForensicFeatures& features) {
    return {
        {"laplacian_var", features.laplacian_var},
        {"noise_residual_std", features.noise_residual_std},
        {"fft_high_ratio", features.fft_high_ratio},
        {"fft_peakiness", features.fft_peakiness},
        {"saturation_mean", features.saturation_mean},
        {"saturation_std", features.saturation_std},
        {"channel_corr", features.channel_corr},
        {"gradient_entropy", features.gradient_entropy},
        {"blockiness", features.blockiness},
        {"edge_density", features.edge_density},
    };
}

}  // namespace origincheck


