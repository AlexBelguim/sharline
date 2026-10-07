//! The main menu's copy: everything it derives from data and state as text (player card, agent tag,
//! version lines, recent games), as plain functions so they can be tested.

use crate::loadout::LoadoutSummary;
use std::net::Ipv4Addr;
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;
use vetf_sim::data::{AmmoKind, AttachmentCategory};
use vetf_sim::{Zone, ZoneTable};

/// Magazine slots on the MAGS line.
pub const MAG_SLOTS: usize = vetf_sim::weapon::MAX_MAGS;

/// "Working title · prototype 0.1" (major.minor of the crate version).
pub fn tagline() -> String {
    let v = env!("CARGO_PKG_VERSION");
    let short: Vec<&str> = v.split('.').take(2).collect();
    format!("Working title · prototype {}", short.join("."))
}

/// Version line 1: "v0.1.0-proto · Bevy 0.19 · lightyear 0.30" (the micro role upper-cases it).
pub fn version_line() -> String {
    format!("v{}-proto · Bevy 0.19 · lightyear 0.30", env!("CARGO_PKG_VERSION"))
}

/// Version line 2: the network facts instead of the mockup's region / relay ("UDP 47820 · " and
/// "LAN 192.168.1.23"). The second part is a warning when there is no route ("NO NETWORK").
pub fn network_line(port: u16, ip: Option<Ipv4Addr>) -> (String, String, bool) {
    let head = format!("UDP {port} · ");
    match ip {
        Some(ip) if !ip.is_loopback() && !ip.is_unspecified() => (head, format!("LAN {ip}"), false),
        _ => (head, "NO NETWORK".into(), true),
    }
}

/// A short attachment name for the player card ("holo", "std stock", "30 mag", "angled grip").
pub fn attachment_short(id: &str, data: &GameData) -> String {
    let spec = data.attachment(id);
    let cap = spec.and_then(|s| s.capacity);
    match spec.map(|s| s.cat) {
        Some(AttachmentCategory::Optic) => match id.trim_start_matches("optic_") {
            "reddot" => "red dot".into(),
            "3x" => "3x scope".into(),
            "sniper" => "sniper scope".into(),
            other => other.replace('_', " "),
        },
        Some(AttachmentCategory::Stock) => {
            let kind = id.rsplit('_').next().unwrap_or(id);
            let kind = if kind == "standard" { "std" } else { kind };
            format!("{kind} stock")
        }
        Some(AttachmentCategory::Mag) => match cap {
            Some(n) if id.contains("drum") => format!("{n} drum"),
            Some(n) => format!("{n} mag"),
            None => id.replace('_', " "),
        },
        Some(AttachmentCategory::Under) if id.starts_with("grip_") => {
            format!("{} grip", id.trim_start_matches("grip_"))
        }
        Some(AttachmentCategory::Under) if id.starts_with("ugl") => "UGL".into(),
        Some(AttachmentCategory::Shield) => "gun shield".into(),
        _ => id.replace('_', " "),
    }
}

/// Covered arcs as letters and tiers: "H2 T2", "T3 A3" ("" with no halo).
pub fn arcs_short(tiers: &ZoneTable<u8>) -> String {
    Zone::ALL
        .iter()
        .filter(|z| tiers[**z] > 0)
        .map(|z| format!("{}{}", zone_letter(*z), tiers[*z]))
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn zone_letter(z: Zone) -> char {
    match z {
        Zone::Head => 'H',
        Zone::Torso => 'T',
        Zone::Arms => 'A',
        Zone::Legs => 'L',
    }
}

/// The halo's tier label: "T2" when every covered arc has one tier, "T1–T4" when mixed, None with no halo.
/// The second value is the highest tier (the label's colour).
pub fn tier_label(tiers: &ZoneTable<u8>) -> Option<(String, u8)> {
    let lit: Vec<u8> = tiers.iter().map(|(_, t)| *t).filter(|t| *t > 0).collect();
    let (lo, hi) = (*lit.iter().min()?, *lit.iter().max()?);
    let label = if lo == hi { format!("T{hi}") } else { format!("T{lo}–T{hi}") };
    Some((label, hi))
}

/// The player card's loadout line: "Default loadout · AR-7 Mako (holo, std stock, 30 mag) · Mender Scout H2 T2".
pub fn loadout_line(choice: &LoadoutChoice, s: &LoadoutSummary, data: &GameData) -> String {
    let d = &data.rules.default_loadout;
    let is_default = choice.weapon == d.primary
        && choice.mags == d.mags
        && choice.attachments == d.attachments
        && choice.halo == crate::config::halo_from_armor(&d.armor, data);
    let name = if is_default { "Default loadout" } else { "Custom loadout" };
    let attachments: Vec<String> = choice.attachments.iter().map(|a| attachment_short(a, data)).collect();
    let weapon = if attachments.is_empty() {
        s.weapon_name.clone()
    } else {
        format!("{} ({})", s.weapon_name, attachments.join(", "))
    };
    let arcs = arcs_short(&s.tiers);
    // The halo is custom now (a core and a tier per arc): name the core, then the arcs.
    let halo = match s.core {
        Some(core) if !arcs.is_empty() => format!("{} {arcs}", title_case(core.label())),
        _ => "No halo".to_string(),
    };
    format!("{name} · {weapon} · {halo}")
}

/// "MENDER" -> "Mender".
fn title_case(s: &str) -> String {
    let mut c = s.chars();
    c.next().map_or(String::new(), |f| f.to_uppercase().chain(c.flat_map(|ch| ch.to_lowercase())).collect())
}

/// The MAGS line: six slots in order, each the short ammo label and type, or None for an unused slot.
pub fn mag_slots(s: &LoadoutSummary) -> [Option<(String, AmmoKind)>; MAG_SLOTS] {
    let mut slots: [Option<(String, AmmoKind)>; MAG_SLOTS] = Default::default();
    for (slot, label, kind) in &s.mags {
        if let Some(cell) = slot.checked_sub(1).and_then(|i| slots.get_mut(i)) {
            *cell = Some((label.clone(), *kind));
        }
    }
    slots
}

/// The GEAR readout's numbers and whether they are over budget: ("4 / 13", false).
pub fn gear_text(cost: u32, budget: u32) -> (String, bool) {
    (format!("{cost} / {budget}"), cost > budget)
}

/// The agent tag's halo part: the tier label with the core ("T2 MENDER") and its colour tier, or None
/// with no halo.
pub fn agent_halo(s: &LoadoutSummary) -> Option<(String, u8)> {
    let core = s.core?;
    let (label, hi) = tier_label(&s.tiers)?;
    Some((format!("{label} {}", core.label()), hi))
}

/// The agent tag's micro line after the halo chip: "· LIGHT · AR-7 MAKO", or "NO HALO · AR-7 MAKO".
pub fn agent_micro(s: &LoadoutSummary) -> String {
    match agent_halo(s) {
        Some(_) => format!("· {} · {}", s.weight.label(), s.weapon_name.to_uppercase()),
        None => format!("NO HALO · {}", s.weapon_name.to_uppercase()),
    }
}

/// MAX PLAYERS help: "2–10 · 5 v 5 max on Showhome".
pub fn max_players_help(cap: u32, tdm_max: u32) -> String {
    let half = tdm_max / 2;
    format!("2–{cap} · {half} v {half} max on Showhome")
}

/// A map's mode and name for RECENT: "TDM · Showhome", "Gun range".
pub fn mode_map_label(map: &str) -> String {
    match map.to_ascii_lowercase().as_str() {
        "range" => "Gun range".into(),
        "showhome" => "TDM · Showhome".into(),
        other => {
            let mut c = other.chars();
            let name: String = c.next().map(|f| f.to_uppercase().chain(c).collect()).unwrap_or_default();
            format!("TDM · {name}")
        }
    }
}

/// A RECENT row's subline: "TDM · Showhome · code 6000-105E-PC", "Gun range · 192.168.1.40:47820", or
/// "TDM · last seen 2 days ago" after a day.
pub fn recent_subline(map: &str, address: &str, by_ip: bool, last_joined: u64, now: u64) -> String {
    let label = mode_map_label(map);
    let days = now.saturating_sub(last_joined) / 86_400;
    if days >= 1 {
        let mode = label.split(" · ").next().unwrap_or(&label).to_string();
        let ago = if days == 1 { "1 day ago".to_string() } else { format!("{days} days ago") };
        return format!("{mode} · last seen {ago}");
    }
    if crate::iroh_transport::parse_invite(address).is_some() {
        format!("{label} · internet invite (session only)")
    } else if by_ip {
        format!("{label} · {address}")
    } else {
        format!("{label} · code {address}")
    }
}

/// CREATE LOBBY's help while it starts the match directly (phase 1, before the lobby screen).
pub fn create_help(score_limit: u32) -> String {
    format!("Starts Team Deathmatch on Showhome · first to {score_limit}.")
}

pub const HOST_INTRO: &str =
    "You play and host at the same time (listen server). If you leave, the match ends for everyone.";
pub const PORT_HELP: &str = "UDP. Only needed for Direct IP (port-forward).";
pub const PORT_ERROR: &str = "Port must be 1024–65535.";
pub const PASSWORD_PLACEHOLDER: &str = "optional · not available yet";
pub const CODE_LABEL: &str = "Code from your host";
pub const CODE_PLACEHOLDER: &str = "Paste host invite";
pub const CODE_HELP: &str = "Paste the host's SL1 invite. Connects over the internet without port forwarding.";
pub const IP_LABEL: &str = "Host address";
/// The spec's "192.168.1.20 or 192.168.1.20:47820" does not fit beside PASTE at 30 px; the help explains :port.
pub const IP_PLACEHOLDER: &str = "192.168.1.20:47820";
pub const LAN_NOT_BUILT: &str =
    "LAN discovery isn't built yet. Ask the host for their join code (TAB or ESC in their match shows it).";
pub const RECENT_EMPTY: &str = "Games you join show up here.";
pub const EMPTY_JOIN: &str = "Type a join code or address first.";

/// DIRECT IP help (the default port comes from net.ron).
pub fn ip_help(port: u16) -> String {
    format!(
        "IPv4 address, with :port if the host changed it (default {port}). Over the internet the host must forward \
         UDP {port}, or you both join a VPN mesh (Tailscale, ZeroTier, Radmin) and use their VPN address."
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::loadout::summary;
    use vetf_sim::data::AmmoChoice;

    fn default_choice(d: &GameData) -> LoadoutChoice {
        let l = &d.rules.default_loadout;
        LoadoutChoice {
            weapon: l.primary.clone(),
            mags: l.mags.clone(),
            attachments: l.attachments.clone(),
            halo: crate::config::halo_from_armor(&l.armor, d),
            agent: crate::config::DEFAULT_AGENT.into(),
        }
    }

    #[test]
    fn the_player_card_describes_the_default_loadout() {
        let d = GameData::embedded();
        let c = default_choice(&d);
        let s = summary(&c, &d);
        assert_eq!(loadout_line(&c, &s, &d), "Default loadout · AR-7 Mako (holo, std stock, 30 mag) · Mender H2 T2");
        let slots = mag_slots(&s);
        assert_eq!(slots.iter().filter(|m| m.is_some()).count(), c.mags.len());
        assert_eq!(slots[0], Some(("STD".into(), AmmoKind::Standard)));
        assert_eq!(slots[5], None, "unused slots show a dash");
        // The default Mender Scout (H2 T2) is LIGHT, whatever the mockup's sample copy says.
        assert_eq!(agent_halo(&s), Some(("T2 MENDER".into(), 2)));
        assert_eq!(agent_micro(&s), "· LIGHT · AR-7 MAKO");
    }

    #[test]
    fn other_loadouts_and_no_halo() {
        let d = GameData::embedded();
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        let c = LoadoutChoice {
            halo: crate::config::halo_from_armor("arm_none", &d),
            mags: vec![ap2, AmmoChoice::STANDARD],
            ..default_choice(&d)
        };
        let s = summary(&c, &d);
        assert!(loadout_line(&c, &s, &d).starts_with("Custom loadout · "));
        assert!(loadout_line(&c, &s, &d).ends_with(" · No halo"));
        assert_eq!(agent_halo(&s), None);
        assert_eq!(agent_micro(&s), "NO HALO · AR-7 MAKO");
        assert_eq!(mag_slots(&s)[0], Some(("AP II".into(), AmmoKind::ArmorPiercing)));
    }

    #[test]
    fn tier_labels_name_uniform_and_mixed_halos() {
        let t = |h, t, a, l| ZoneTable { head: h, torso: t, arms: a, legs: l };
        assert_eq!(tier_label(&t(2, 2, 0, 0)), Some(("T2".into(), 2)));
        assert_eq!(tier_label(&t(2, 4, 2, 1)), Some(("T1–T4".into(), 4)));
        assert_eq!(tier_label(&t(0, 0, 0, 0)), None);
        assert_eq!(arcs_short(&t(0, 3, 3, 0)), "T3 A3");
    }

    #[test]
    fn attachments_have_short_names() {
        let d = GameData::embedded();
        for (id, short) in [
            ("optic_holo", "holo"),
            ("optic_reddot", "red dot"),
            ("mako_stock_standard", "std stock"),
            ("mako_stock_light", "light stock"),
            ("mag_30", "30 mag"),
            ("mag_drum60", "60 drum"),
            ("grip_angled", "angled grip"),
            ("ugl_launcher", "UGL"),
            ("laser", "laser"),
            ("shield_front", "gun shield"),
        ] {
            assert_eq!(attachment_short(id, &d), short, "{id}");
        }
    }

    #[test]
    fn gear_version_and_network_lines() {
        assert_eq!(gear_text(4, 13), ("4 / 13".into(), false));
        assert_eq!(gear_text(14, 13), ("14 / 13".into(), true));
        assert!(version_line().starts_with(&format!("v{}-proto", env!("CARGO_PKG_VERSION"))));
        assert!(tagline().ends_with("prototype 0.1"));
        let (head, tail, warn) = network_line(47820, Some(Ipv4Addr::new(192, 168, 1, 23)));
        assert_eq!((head.as_str(), tail.as_str(), warn), ("UDP 47820 · ", "LAN 192.168.1.23", false));
        assert!(network_line(47820, Some(Ipv4Addr::LOCALHOST)).2, "no route is a warning");
        assert_eq!(network_line(47820, None).1, "NO NETWORK");
    }

    #[test]
    fn host_and_recent_copy_from_data() {
        let d = GameData::embedded();
        assert_eq!(max_players_help(10, d.rules.tdm.max_players), "2–10 · 5 v 5 max on Showhome");
        assert_eq!(create_help(50), "Starts Team Deathmatch on Showhome · first to 50.");
        let now = 1_700_000_000;
        assert_eq!(recent_subline("showhome", "6000-105E-PC", false, now, now), "TDM · Showhome · code 6000-105E-PC");
        assert_eq!(
            recent_subline("range", "192.168.1.40:47820", true, now - 60, now),
            "Gun range · 192.168.1.40:47820"
        );
        assert_eq!(recent_subline("showhome", "x", false, now - 2 * 86_400 - 5, now), "TDM · last seen 2 days ago");
        assert_eq!(recent_subline("range", "x", true, now - 86_400, now), "Gun range · last seen 1 day ago");
        assert!(ip_help(47820).contains("UDP 47820"));
    }
}
