use std::env;
use std::io::{self, BufRead, BufWriter, Read, Write};

/// `bhudrishti_native` — zero-dependency Rust kernel used by the BHU-DRISHTI
/// pipelines for per-cell ground profiling of LiDAR point clouds.
///
/// Contract (text): read space/tab-separated "x y z" points on stdin, print
/// "x y z ground_z" per line — same shape as the numpy reference & the C++
/// ctypes kernel, so callers can swap implementations freely.
///
/// Contract (binary, --binary): stdin is raw little-endian f64 triples (x y z);
/// stdout is one raw f64 ground-z per input point. No text parsing, so the
/// bulk path avoids all formatting overhead.

const USAGE: &str = "usage: bhudrishti_native ground-profile [--binary] --cell <f> --pct <f> | --version";

fn parse_points() -> Vec<(f64, f64, f64)> {
    let stdin = io::stdin();
    let mut out = Vec::with_capacity(200_000);
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let mut it = line.split_whitespace();
        let (x, y, z) = match (it.next(), it.next(), it.next()) {
            (Some(a), Some(b), Some(c)) => {
                match (a.parse::<f64>(), b.parse::<f64>(), c.parse::<f64>()) {
                    (Ok(x), Ok(y), Ok(z)) => (x, y, z),
                    _ => continue,
                }
            }
            _ => continue,
        };
        out.push((x, y, z));
    }
    out
}

fn parse_points_binary() -> (Vec<f64>, usize) {
    let mut bytes = Vec::new();
    io::stdin().lock().read_to_end(&mut bytes).unwrap();
    let aligned = (bytes.len() / 24) * 24;
    let triples = bytes.len() / 24;
    let mut flat: Vec<f64> = Vec::with_capacity(aligned / 8);
    for chunk in bytes[..aligned].chunks_exact(8) {
        flat.push(f64::from_le_bytes(chunk.try_into().unwrap()));
    }
    // x, y, z are packed contiguously as [x0 y0 z0 x1 y1 z1 ...]
    (flat, triples)
}

/// Per-cell percentile (mirrors the numpy reference algorithm).
fn ground_profile(points: &[(f64, f64, f64)], cell: f64, pct: f64) -> Vec<f64> {
    let n = points.len();
    if n == 0 {
        return Vec::new();
    }
    let mut min_x = f64::INFINITY;
    let mut min_y = f64::INFINITY;
    for &(x, y, _) in points.iter() {
        if x < min_x {
            min_x = x;
        }
        if y < min_y {
            min_y = y;
        }
    }
    // Bin origin = floored global minimum (must match numpy reference + C++ kernel).
    min_x = min_x.floor();
    min_y = min_y.floor();
    // Group indices by cell key (same key scheme as numpy path).
    let mut bins: Vec<Vec<usize>> = Vec::new();
    let mut keys = vec![0usize; n];
    let mut key_of = Vec::new(); // cell-index -> bin id
    for (i, &(x, y, _)) in points.iter().enumerate() {
        let gx = ((x - min_x) / cell).floor() as i64;
        let gy = ((y - min_y) / cell).floor() as i64;
        let key = (gx.wrapping_mul(1_000_000_000i64)).wrapping_add(gy);
        // linear-probe the sparse key map
        let mut found = None;
        for (idx, &k) in key_of.iter().enumerate() {
            if k == key {
                found = Some(idx);
                break;
            }
        }
        let bid = match found {
            Some(id) => id,
            None => {
                key_of.push(key);
                bins.push(Vec::new());
                bins.len() - 1
            }
        };
        keys[i] = bid;
        bins[bid].push(i);
    }
    let mut zs = Vec::with_capacity(n);
    for &(_, _, z) in points.iter() {
        zs.push(z);
    }
    let mut out = vec![0.0f64; n];
    for (_bid, members) in bins.iter().enumerate() {
        let mut vals: Vec<f64> = members.iter().map(|&i| zs[i]).collect();
        vals.sort_by(|a, b| a.partial_cmp(b).unwrap());
        // numpy-linear percentile: idx=(pct/100)*(n-1), interpolate between
        // floor/ceil ranks — identical semantics to the C++ kernel.
        let idx = (pct / 100.0) * (vals.len() - 1) as f64;
        let lo = idx.floor() as usize;
        let mut hi = idx.ceil() as usize;
        if hi < lo {
            hi = lo;
        }
        let frac = idx - lo as f64;
        let v = vals[lo] + frac * (vals[hi.min(vals.len() - 1)] - vals[lo]);
        for &i in members.iter() {
            out[i] = v;
        }
    }
    out
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() >= 2 && args[1] == "--version" {
        println!("bhudrishti_native 0.1.0");
        return;
    }
    if args.len() < 2 || args[1] != "ground-profile" {
        eprintln!("{}", USAGE);
        std::process::exit(1);
    }
    let mut cell = 2.0f64;
    let mut pct = 5.0f64;
    let mut binary = false;
    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--cell" => {
                i += 1;
                cell = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(2.0);
            }
            "--pct" => {
                i += 1;
                pct = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(5.0);
            }
            "--binary" => binary = true,
            _ => {}
        }
        i += 1;
    }

    if binary {
        let (flat, triples) = parse_points_binary();
        let mut points = Vec::with_capacity(triples);
        for k in 0..triples {
            let base = k * 3;
            points.push((flat[base], flat[base + 1], flat[base + 2]));
        }
        let profile = ground_profile(&points, cell.clamp(0.1, 100.0), pct.clamp(0.0, 100.0));
        let mut w = BufWriter::new(io::stdout().lock());
        for v in profile.iter() {
            let bytes = v.to_le_bytes();
            let _ = w.write_all(&bytes);
        }
        let _ = w.flush();
        return;
    }

    let points = parse_points();
    let profile = ground_profile(&points, cell.clamp(0.1, 100.0), pct.clamp(0.0, 100.0));
    let stdout = io::stdout();
    let mut w = BufWriter::new(stdout.lock());
    for (k, &(x, y, z)) in points.iter().enumerate() {
        if k < profile.len() {
            let _ = writeln!(w, "{:.6} {:.6} {:.6} {:.6}", x, y, z, profile[k]);
        }
    }
    let _ = w.flush();
}