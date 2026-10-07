//! Body zones. Health, halo coverage and hitboxes all use the same four zones.

use serde::{Deserialize, Serialize};
use std::ops::{Index, IndexMut};

#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Zone {
    Head,
    Torso,
    Arms,
    Legs,
}

impl Zone {
    pub const ALL: [Zone; 4] = [Zone::Head, Zone::Torso, Zone::Arms, Zone::Legs];

    pub fn index(self) -> usize {
        self as usize
    }

    /// Losing all HP in a vital zone kills; other zones break instead.
    pub fn is_vital(self) -> bool {
        matches!(self, Zone::Head | Zone::Torso)
    }

    pub fn label(self) -> &'static str {
        match self {
            Zone::Head => "HEAD",
            Zone::Torso => "TORSO",
            Zone::Arms => "ARMS",
            Zone::Legs => "LEGS",
        }
    }
}

/// One value per zone. Serialises as `{head, torso, arms, legs}` like the design data.
#[derive(Copy, Clone, Debug, PartialEq, Default, Serialize, Deserialize)]
pub struct ZoneTable<T> {
    pub head: T,
    pub torso: T,
    pub arms: T,
    pub legs: T,
}

impl<T> ZoneTable<T> {
    pub fn splat(v: T) -> Self
    where
        T: Clone,
    {
        Self { head: v.clone(), torso: v.clone(), arms: v.clone(), legs: v }
    }

    pub fn map<U>(&self, mut f: impl FnMut(Zone, &T) -> U) -> ZoneTable<U> {
        ZoneTable {
            head: f(Zone::Head, &self.head),
            torso: f(Zone::Torso, &self.torso),
            arms: f(Zone::Arms, &self.arms),
            legs: f(Zone::Legs, &self.legs),
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = (Zone, &T)> {
        Zone::ALL.into_iter().map(move |z| (z, &self[z]))
    }
}

impl<T> Index<Zone> for ZoneTable<T> {
    type Output = T;
    fn index(&self, zone: Zone) -> &T {
        match zone {
            Zone::Head => &self.head,
            Zone::Torso => &self.torso,
            Zone::Arms => &self.arms,
            Zone::Legs => &self.legs,
        }
    }
}

impl<T> IndexMut<Zone> for ZoneTable<T> {
    fn index_mut(&mut self, zone: Zone) -> &mut T {
        match zone {
            Zone::Head => &mut self.head,
            Zone::Torso => &mut self.torso,
            Zone::Arms => &mut self.arms,
            Zone::Legs => &mut self.legs,
        }
    }
}

/// A set of zones as a bitmask (compact on the wire).
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub struct ZoneSet(pub u8);

impl ZoneSet {
    pub const EMPTY: ZoneSet = ZoneSet(0);

    pub fn from_zones(zones: &[Zone]) -> Self {
        let mut s = Self::EMPTY;
        for &z in zones {
            s.insert(z);
        }
        s
    }

    pub fn contains(self, zone: Zone) -> bool {
        self.0 & (1 << zone.index()) != 0
    }

    pub fn insert(&mut self, zone: Zone) {
        self.0 |= 1 << zone.index();
    }

    pub fn len(self) -> u32 {
        self.0.count_ones()
    }

    pub fn is_empty(self) -> bool {
        self.0 == 0
    }

    pub fn iter(self) -> impl Iterator<Item = Zone> {
        Zone::ALL.into_iter().filter(move |&z| self.contains(z))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zone_set_roundtrip() {
        let s = ZoneSet::from_zones(&[Zone::Head, Zone::Legs]);
        assert!(s.contains(Zone::Head) && s.contains(Zone::Legs));
        assert!(!s.contains(Zone::Torso) && !s.contains(Zone::Arms));
        assert_eq!(s.len(), 2);
        assert_eq!(s.iter().collect::<Vec<_>>(), vec![Zone::Head, Zone::Legs]);
    }

    #[test]
    fn zone_table_index() {
        let mut t = ZoneTable::splat(1.0_f32);
        t[Zone::Arms] = 3.0;
        assert_eq!(t.arms, 3.0);
        assert_eq!(t.map(|z, v| if z == Zone::Arms { *v } else { 0.0 }).arms, 3.0);
    }
}
