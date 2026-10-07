//! How friends join the running session, for every screen that shows it (the lobby, the scoreboard, the ESC
//! menu, the HUD board). Screens show the invite's STATE, never the full 64-hex invite as the main element:
//!
//! - [`JoinInfo::of`] reads the [`Session`]: an internet invite that is still being prepared, ready (show
//!   [`short_invite`] and a COPY INVITE button) or unavailable (show why, and the LAN `ip:port` fallback),
//!   or a plain address (Direct IP or LAN-only hosting, or a client that joined by address).
//! - The copy helpers ([`JoinInfo::label`], [`JoinInfo::headline`], [`JoinInfo::detail`],
//!   [`JoinInfo::copy_label`]) keep the words the same on every screen.
//! - A COPY button writes [`CopyInvite`]; F6 does the same anywhere. [`JoinInfo::copy_text`] goes on the
//!   clipboard (the full invite). [`InviteCopied::recent`] tells a button to read "COPIED" for a moment.

// The lobby, scoreboard and ESC menu (wave 2) use the rest of this API.
#![allow(dead_code)]

use crate::iroh_transport;
use crate::net::{JoinAccess, Role, Session};
use bevy::prelude::*;
use std::net::SocketAddr;
use vetf_net::JoinCode;

pub struct InvitePlugin;

impl Plugin for InvitePlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<CopyInvite>().init_resource::<InviteCopied>().add_systems(Update, copy_invite);
    }
}

/// How long a COPY button reads "COPIED" after a copy.
pub const COPIED_FOR_S: f32 = 1.5;

/// How friends reach this session.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JoinInfo {
    /// Not in a session: nothing to show.
    None,
    /// Hosting with WHO CAN JOIN = Join code: Iroh is still publishing the invite (a few seconds, at most
    /// about 30). `lan` already works for friends on this network.
    Preparing { lan: Option<SocketAddr> },
    /// The internet invite is ready (`SL1-` + 64 hex). A client that joined by invite sees it too, so it
    /// can pass it on.
    Ready { invite: String, lan: Option<SocketAddr> },
    /// The internet invite failed (no internet, discovery down): friends can still join on the LAN, or by
    /// direct IP with a forwarded port.
    Unavailable { error: String, lan: Option<SocketAddr> },
    /// Direct IP or LAN-only hosting, or a client that joined by address or a legacy LAN code.
    Address { addr: SocketAddr, lan_only: bool },
}

/// What kind of state, for the colour of the headline.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JoinState {
    None,
    Preparing,
    Ready,
    Unavailable,
    Address,
}

impl JoinInfo {
    /// Read the session (`default_port` is `net.ron`'s, for a client's address typed without one).
    pub fn of(session: &Session, default_port: u16) -> Self {
        match session.role {
            Role::Offline => JoinInfo::None,
            Role::Host if session.access == JoinAccess::JoinCode => {
                let lan = session.lan_addr;
                match (&session.join_code, &session.internet_error) {
                    (Some(invite), _) if iroh_transport::parse_invite(invite).is_some() => {
                        JoinInfo::Ready { invite: invite.clone(), lan }
                    }
                    (_, Some(error)) => JoinInfo::Unavailable { error: error.clone(), lan },
                    _ => JoinInfo::Preparing { lan },
                }
            }
            Role::Host => match session.lan_addr {
                Some(addr) => JoinInfo::Address { addr, lan_only: session.access == JoinAccess::LanOnly },
                None => JoinInfo::Unavailable { error: "No network address found.".into(), lan: None },
            },
            Role::Client => {
                let Some(text) = session.join_code.as_deref() else { return JoinInfo::None };
                if let Some(id) = iroh_transport::parse_invite(text) {
                    return JoinInfo::Ready { invite: iroh_transport::invite(id), lan: None };
                }
                match JoinCode::parse(text, default_port) {
                    Some(addr) => JoinInfo::Address { addr, lan_only: false },
                    None => JoinInfo::None,
                }
            }
        }
    }

    pub fn state(&self) -> JoinState {
        match self {
            JoinInfo::None => JoinState::None,
            JoinInfo::Preparing { .. } => JoinState::Preparing,
            JoinInfo::Ready { .. } => JoinState::Ready,
            JoinInfo::Unavailable { .. } => JoinState::Unavailable,
            JoinInfo::Address { .. } => JoinState::Address,
        }
    }

    /// The small label over the headline (upper case): "INTERNET INVITE", "DIRECT IP", "LAN ADDRESS".
    pub fn label(&self) -> &'static str {
        match self {
            JoinInfo::None => "",
            JoinInfo::Preparing { .. } | JoinInfo::Ready { .. } => "INTERNET INVITE",
            JoinInfo::Unavailable { .. } => "INTERNET INVITE UNAVAILABLE",
            JoinInfo::Address { lan_only: true, .. } => "LAN ADDRESS",
            JoinInfo::Address { lan_only: false, .. } => "DIRECT IP",
        }
    }

    /// The main element: the short invite ("SL1-3A38…DC49"), "PREPARING…", the LAN fallback, or ip:port.
    pub fn headline(&self) -> String {
        match self {
            JoinInfo::None => String::new(),
            JoinInfo::Preparing { .. } => "PREPARING…".into(),
            JoinInfo::Ready { invite, .. } => short_invite(invite),
            JoinInfo::Unavailable { lan: Some(lan), .. } => format!("LAN {lan}"),
            JoinInfo::Unavailable { lan: None, .. } => "—".into(),
            JoinInfo::Address { addr, .. } => addr.to_string(),
        }
    }

    /// One line under the headline (sentence case), or None.
    pub fn detail(&self) -> Option<String> {
        match self {
            JoinInfo::None => None,
            JoinInfo::Preparing { .. } => Some("Ready in a few seconds (up to 30). Then COPY INVITE or F6.".into()),
            JoinInfo::Ready { .. } => Some("Friends paste it in JOIN GAME. Valid while this session runs.".into()),
            JoinInfo::Unavailable { error, lan: Some(_) } => {
                Some(format!("{} Friends on your network can join with the LAN address.", sentence(error)))
            }
            JoinInfo::Unavailable { error, lan: None } => Some(sentence(error)),
            JoinInfo::Address { lan_only: true, .. } => Some("Friends on your network join with this address.".into()),
            JoinInfo::Address { addr, lan_only: false } => Some(format!(
                "Over the internet friends need your public IP with UDP {} forwarded, or a shared VPN.",
                addr.port()
            )),
        }
    }

    /// What COPY (and F6) puts on the clipboard: the full invite or the address. None while preparing.
    pub fn copy_text(&self) -> Option<String> {
        match self {
            JoinInfo::Ready { invite, .. } => Some(invite.clone()),
            JoinInfo::Unavailable { lan: Some(lan), .. } => Some(lan.to_string()),
            JoinInfo::Address { addr, .. } => Some(addr.to_string()),
            _ => None,
        }
    }

    /// The COPY button's label: "COPY INVITE" for an invite, "COPY ADDRESS" for an address.
    pub fn copy_label(&self) -> &'static str {
        match self {
            JoinInfo::Ready { .. } | JoinInfo::Preparing { .. } => "COPY INVITE",
            _ => "COPY ADDRESS",
        }
    }
}

/// An error message ends with a full stop.
fn sentence(s: &str) -> String {
    let t = s.trim();
    if t.ends_with(['.', '!', '?']) { t.to_string() } else { format!("{t}.") }
}

/// The display form of a long invite: "SL1-" and the first and last four characters of the key,
/// "SL1-3A38…DC49". Anything that is not an invite is returned as it is.
pub fn short_invite(text: &str) -> String {
    let t = text.trim();
    match iroh_transport::parse_invite(t) {
        Some(_) => {
            let key = &t[4..];
            format!("SL1-{}…{}", key[..4].to_uppercase(), key[key.len() - 4..].to_uppercase())
        }
        None => t.to_string(),
    }
}

/// Copy the session's invite or address to the clipboard (a COPY button; F6 sends it too).
#[derive(Message, Debug, Clone, Copy, Default)]
pub struct CopyInvite;

/// When the last copy worked (seconds since start-up), for a "COPIED" label.
#[derive(Resource, Debug, Default, Clone, Copy)]
pub struct InviteCopied {
    pub at: Option<f32>,
}

impl InviteCopied {
    /// A copy worked less than [`COPIED_FOR_S`] ago.
    pub fn recent(&self, now: f32) -> bool {
        self.at.is_some_and(|t| now - t < COPIED_FOR_S)
    }
}

fn copy_invite(
    keys: Res<ButtonInput<KeyCode>>,
    mut requests: MessageReader<CopyInvite>,
    session: Res<Session>,
    data: Option<Res<crate::config::Data>>,
    clipboard: Option<ResMut<bevy::clipboard::Clipboard>>,
    time: Res<Time>,
    mut copied: ResMut<InviteCopied>,
) {
    let asked = requests.read().count() > 0 || keys.just_pressed(KeyCode::F6);
    if !asked {
        return;
    }
    let port = data.map_or(47820, |d| d.net.port);
    let Some(text) = JoinInfo::of(&session, port).copy_text() else { return };
    let Some(mut clipboard) = clipboard else { return };
    match clipboard.set_text(text) {
        Ok(()) => copied.at = Some(time.elapsed_secs()),
        Err(e) => warn!("Cannot copy the invite: {e}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn invite() -> String {
        iroh_transport::invite(iroh::SecretKey::from_bytes(&[8; 32]).public())
    }

    fn host(access: JoinAccess) -> Session {
        let mut s = Session::default();
        s.role = Role::Host;
        s.access = access;
        s.lan_addr = Some("192.168.1.23:47820".parse().unwrap());
        s
    }

    #[test]
    fn long_invites_are_shortened_for_display() {
        let inv = invite();
        let short = short_invite(&inv);
        assert!(short.starts_with("SL1-") && short.contains('…'), "{short}");
        assert_eq!(short.chars().count(), 4 + 4 + 1 + 4);
        assert_eq!(&short[4..8], &inv[4..8]);
        assert!(short.ends_with(&inv[inv.len() - 4..]));
        assert_eq!(short_invite(&inv.to_lowercase()), short, "case does not matter");
        assert_eq!(short_invite("192.168.1.23:47820"), "192.168.1.23:47820", "not an invite: as it is");
    }

    #[test]
    fn an_invite_host_goes_preparing_ready_or_unavailable() {
        let mut s = host(JoinAccess::JoinCode);
        let lan = s.lan_addr;
        assert_eq!(JoinInfo::of(&s, 47820), JoinInfo::Preparing { lan });
        assert_eq!(JoinInfo::of(&s, 47820).copy_text(), None, "nothing to copy yet");
        assert_eq!(JoinInfo::of(&s, 47820).headline(), "PREPARING…");

        s.join_code = Some(invite());
        let ready = JoinInfo::of(&s, 47820);
        assert_eq!(ready.state(), JoinState::Ready);
        assert_eq!(ready.copy_text(), Some(invite()), "COPY puts the full invite on the clipboard");
        assert_eq!(ready.headline(), short_invite(&invite()), "the screen shows the short form");
        assert_eq!(ready.copy_label(), "COPY INVITE");

        s.join_code = None;
        s.internet_error = Some("Iroh relay unreachable".into());
        let down = JoinInfo::of(&s, 47820);
        assert_eq!(down.state(), JoinState::Unavailable);
        assert_eq!(down.headline(), "LAN 192.168.1.23:47820", "the LAN fallback");
        assert_eq!(down.copy_text().as_deref(), Some("192.168.1.23:47820"));
        assert!(down.detail().unwrap().starts_with("Iroh relay unreachable. "));
    }

    #[test]
    fn direct_and_lan_hosting_show_ip_and_port() {
        let direct = JoinInfo::of(&host(JoinAccess::DirectIp), 47820);
        assert_eq!(direct.headline(), "192.168.1.23:47820");
        assert_eq!((direct.label(), direct.copy_label()), ("DIRECT IP", "COPY ADDRESS"));
        assert!(direct.detail().unwrap().contains("UDP 47820"));
        let lan = JoinInfo::of(&host(JoinAccess::LanOnly), 47820);
        assert_eq!(lan.label(), "LAN ADDRESS");
        assert_eq!(lan.copy_text().as_deref(), Some("192.168.1.23:47820"));
    }

    #[test]
    fn clients_see_how_they_joined() {
        assert_eq!(JoinInfo::of(&Session::default(), 47820), JoinInfo::None);
        let mut s = Session::default();
        s.role = Role::Client;
        s.join_code = Some(invite().to_lowercase());
        assert_eq!(JoinInfo::of(&s, 47820), JoinInfo::Ready { invite: invite(), lan: None });
        s.join_code = Some("10.0.0.2".into());
        assert_eq!(
            JoinInfo::of(&s, 47820),
            JoinInfo::Address { addr: "10.0.0.2:47820".parse().unwrap(), lan_only: false }
        );
    }

    #[test]
    fn copied_reads_for_a_moment() {
        let c = InviteCopied { at: Some(10.0) };
        assert!(c.recent(10.5));
        assert!(!c.recent(10.0 + COPIED_FOR_S));
        assert!(!InviteCopied::default().recent(0.0));
    }
}
