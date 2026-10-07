//! Deterministic randomness. Spread and recoil jitter must come out the same on the predicting client and
//! on the host, so every random draw is a pure function of a seed (player id, shot number, ...).

/// SplitMix64: tiny, fast, good enough for gameplay jitter.
#[derive(Debug, Clone, Copy)]
pub struct SplitMix(u64);

impl SplitMix {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    /// Seed from several values (order matters).
    pub fn from_parts(parts: &[u64]) -> Self {
        let mut s = 0x9E37_79B9_7F4A_7C15_u64;
        for &p in parts {
            s = Self(s ^ p).next_u64();
        }
        Self(s)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform in [0, 1).
    pub fn next_f32(&mut self) -> f32 {
        (self.next_u64() >> 40) as f32 / (1u64 << 24) as f32
    }

    /// Uniform in [-1, 1).
    pub fn next_signed(&mut self) -> f32 {
        self.next_f32() * 2.0 - 1.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_same_sequence() {
        let mut a = SplitMix::from_parts(&[7, 42]);
        let mut b = SplitMix::from_parts(&[7, 42]);
        let mut c = SplitMix::from_parts(&[42, 7]);
        let xa: Vec<_> = (0..8).map(|_| a.next_u64()).collect();
        let xb: Vec<_> = (0..8).map(|_| b.next_u64()).collect();
        let xc: Vec<_> = (0..8).map(|_| c.next_u64()).collect();
        assert_eq!(xa, xb);
        assert_ne!(xa, xc);
    }

    #[test]
    fn floats_in_range() {
        let mut r = SplitMix::new(1);
        let mut sum = 0.0;
        for _ in 0..10_000 {
            let f = r.next_f32();
            assert!((0.0..1.0).contains(&f));
            sum += f;
        }
        assert!((sum / 10_000.0 - 0.5).abs() < 0.02);
    }
}
