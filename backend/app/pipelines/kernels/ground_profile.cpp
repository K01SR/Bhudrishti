// Bhu-Drishti 3D — native C++ spatial kernel (ground profile, per-cell percentile).
// Compiled at first use via ctypes (g++/gcc shipped in the backend image). This is
// the REAL multi-language execution backend behind the "high-performance pipelines":
//   grid_ground_profile performs per-cell (histogram bin) ground-elevation estimation
//   directly on raw LiDAR XYZ returns, replacing a pure-numpy scanline.
#include <cstdint>
#include <cmath>
#include <algorithm>
#include <vector>
#include <unordered_map>

typedef struct {
    double x, y, z;
} Point3;

extern "C" {

// ground_profile: fills `out[0..n-1]` with each point's grid-cell P{pct} ground estimate.
// pts layout: n consecutive x,y,z triples.
void ground_profile(const double* pts, int64_t n, double cell, double pct, double* out) {
    if (n <= 0 || cell <= 0.0) return;
    double minx = pts[0], miny = pts[1];
    for (int64_t i = 1; i < n; ++i) {
        minx = std::min(minx, pts[3*i]);
        miny = std::min(miny, pts[3*i+1]);
    }
    // Bin origin = floored global minimum (must match the numpy reference).
    minx = std::floor(minx);
    miny = std::floor(miny);
    std::unordered_map<int64_t, std::vector<double>> cells;
    cells.reserve((size_t)(n / 4 + 1));
    for (int64_t i = 0; i < n; ++i) {
        int64_t xi = (int64_t)std::floor((pts[3*i] - minx) / cell);
        int64_t yi = (int64_t)std::floor((pts[3*i+1] - miny) / cell);
        int64_t key = (xi << 32) | (uint64_t)(uint32_t)yi;
        cells[key].push_back(pts[3*i+2]);
    }
    std::unordered_map<int64_t, double> result;
    result.reserve(cells.size());
    for (auto& kv : cells) {
        std::vector<double>& v = kv.second;
        std::sort(v.begin(), v.end());
        double idx = (pct / 100.0) * (double)(v.size() - 1);
        int64_t lo = (int64_t)std::floor(idx);
        int64_t hi = (int64_t)std::ceil(idx);
        double frac = idx - (double)lo;
        if (hi < lo) hi = lo;
        double val = v[lo] + frac * (v[(size_t)hi] - v[lo]);
        result[kv.first] = val;
    }
    for (int64_t i = 0; i < n; ++i) {
        int64_t xi = (int64_t)std::floor((pts[3*i] - minx) / cell);
        int64_t yi = (int64_t)std::floor((pts[3*i+1] - miny) / cell);
        int64_t key = (xi << 32) | (uint64_t)(uint32_t)yi;
        out[i] = result[key];
    }
}

} // extern "C"