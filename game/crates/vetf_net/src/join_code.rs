//! Join codes: a short, typeable code that always holds the address to dial
//! (design/systems/diagrams/net_architecture.png, "the join code always holds the address to dial").
//!
//! Format: the IPv4 address and port (6 bytes) in Crockford base32, grouped as `XXXX-XXXX-XX`.
//! Players can also paste a plain `ip:port` or bare `ip` (default port) anywhere a code is accepted.

use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4};

const ALPHABET: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JoinCode(pub SocketAddrV4);

impl JoinCode {
    pub fn encode(addr: SocketAddrV4) -> String {
        let mut v: u64 = 0;
        for b in addr.ip().octets() {
            v = (v << 8) | b as u64;
        }
        v = (v << 16) | addr.port() as u64;
        // 48 bits -> 10 base32 digits.
        let mut chars = [0u8; 10];
        for i in (0..10).rev() {
            chars[i] = ALPHABET[(v & 31) as usize];
            v >>= 5;
        }
        let s = std::str::from_utf8(&chars).unwrap();
        format!("{}-{}-{}", &s[0..4], &s[4..8], &s[8..10])
    }

    /// Parse a join code, `ip:port`, or a bare IPv4 address (using `default_port`).
    pub fn parse(text: &str, default_port: u16) -> Option<SocketAddr> {
        let t = text.trim();
        if let Ok(addr) = t.parse::<SocketAddr>() {
            return Some(addr);
        }
        if let Ok(ip) = t.parse::<Ipv4Addr>() {
            return Some(SocketAddr::V4(SocketAddrV4::new(ip, default_port)));
        }
        Self::decode(t).map(SocketAddr::V4)
    }

    pub fn decode(code: &str) -> Option<SocketAddrV4> {
        let mut v: u64 = 0;
        let mut n = 0;
        for c in code.chars().filter(|c| !matches!(c, '-' | ' ')) {
            // Crockford: accept lower case and the usual look-alikes.
            let c = match c.to_ascii_uppercase() {
                'O' => '0',
                'I' | 'L' => '1',
                c => c,
            };
            let d = ALPHABET.iter().position(|&a| a == c as u8)? as u64;
            v = (v << 5) | d;
            n += 1;
        }
        if n != 10 {
            return None;
        }
        let port = (v & 0xFFFF) as u16;
        let ip = (v >> 16) as u32;
        Some(SocketAddrV4::new(Ipv4Addr::from(ip), port))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        for (ip, port) in [([192, 168, 1, 23], 47820), ([100, 64, 12, 7], 47820), ([255, 255, 255, 255], 65535)] {
            let addr = SocketAddrV4::new(Ipv4Addr::from(ip), port);
            let code = JoinCode::encode(addr);
            assert_eq!(code.len(), 12, "{code}");
            assert_eq!(JoinCode::decode(&code), Some(addr));
            assert_eq!(JoinCode::decode(&code.to_lowercase()), Some(addr));
        }
    }

    #[test]
    fn parse_accepts_addresses_too() {
        assert_eq!(JoinCode::parse("10.0.0.5:9000", 47820), Some("10.0.0.5:9000".parse().unwrap()));
        assert_eq!(JoinCode::parse(" 10.0.0.5 ", 47820), Some("10.0.0.5:47820".parse().unwrap()));
        assert_eq!(JoinCode::parse("nonsense", 47820), None);
    }
}
