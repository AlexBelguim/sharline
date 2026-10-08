//! Hosting and joining: lightyear server / client entities and the connection lifecycle.
//!
//! Internet invites use an Iroh datagram bridge around the existing netcode/UDP transport.
//! The host's player uses an in-process link; direct IP and legacy LAN codes still use UDP.

use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data, level_by_name};
use crate::iroh_transport::{self, Bridge, Event as InternetEvent};
use crate::user_config::{RecentServer, RecentServers};
use bevy::prelude::*;
use lightyear::netcode::client_plugin::NetcodeConfig as ClientNetcodeConfig;
use lightyear::netcode::server_plugin::NetcodeConfig as ServerNetcodeConfig;
use lightyear::prelude::client::NetcodeClient;
use lightyear::prelude::server::{NetcodeServer, ServerUdpIo, Start, Stop};
use lightyear::prelude::*;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket};
use std::sync::Arc;
use std::time::Duration;
use vetf_net::{Hello, JoinCode, MatchState, PlayerId, PlayerInfo, ReliableChannel};
use vetf_sim::GameData;

pub struct NetPlugin;

impl Plugin for NetPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Session>()
            .init_resource::<HostSettings>()
            .init_resource::<Closing>()
            .insert_resource(crate::user_config::load_or_default::<RecentServers>(RecentServers::FILE))
            .init_resource::<RecentPending>()
            .add_message::<NetRequest>()
            .add_systems(Update, (poll_internet, handle_requests, finish_closing).chain())
            .add_systems(Startup, auto_start)
            .add_systems(OnEnter(AppState::InGame), arm_recent)
            .add_systems(Update, record_recent.run_if(in_state(AppState::InGame)))
            .add_observer(on_client_connected)
            .add_observer(on_client_disconnected);
    }
}

/// Join-code hosting enables Iroh discovery and relay fallback. Direct-IP and LAN modes
/// keep the UDP path and do not contact Iroh services. LAN discovery is not built yet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum JoinAccess {
    #[default]
    JoinCode,
    LanOnly,
    DirectIp,
}

/// The HOST GAME panel's settings, kept across menu visits and used by [`NetRequest::Host`] (and so by the
/// gun range and `--host` too).
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct HostSettings {
    /// Empty: "<PLAYER NAME>'S GAME" (see [`HostSettings::lobby_name_for`]). Not replicated yet.
    pub lobby_name: String,
    pub access: JoinAccess,
    /// Players including the host: even, 2 up to [`max_players_cap`] (free-for-all: up to its own cap,
    /// [`max_players_cap_for`]).
    pub max_players: u32,
    /// Team deathmatch or free-for-all (HOST GAME's MODE, `--mode`). The gun range is always the range.
    pub mode: vetf_net::MatchMode,
    /// The UDP port to host on: `--port`, else `net.ron`.
    pub port: u16,
    /// Not in the protocol yet (the panel shows the field disabled).
    pub password: Option<String>,
}

impl HostSettings {
    pub const LOBBY_NAME_MAX: usize = 24;

    pub fn new(data: &GameData, cli_port: Option<u16>) -> Self {
        Self {
            lobby_name: String::new(),
            access: JoinAccess::JoinCode,
            max_players: max_players_cap(data),
            mode: vetf_net::MatchMode::Tdm,
            port: cli_port.unwrap_or(data.net.port),
            password: None,
        }
    }

    /// The lobby's name: the typed one, else "<PLAYER>'S GAME".
    pub fn lobby_name_for(&self, player: &str) -> String {
        let typed = self.lobby_name.trim();
        if typed.is_empty() { default_lobby_name(player) } else { typed.chars().take(Self::LOBBY_NAME_MAX).collect() }
    }
}

impl FromWorld for HostSettings {
    fn from_world(world: &mut World) -> Self {
        let port = world.get_resource::<Cli>().and_then(|c| c.port);
        let mode = world.get_resource::<Cli>().and_then(|c| c.mode);
        let mut host = match world.get_resource::<Data>() {
            Some(data) => Self::new(data, port),
            None => Self::new(&GameData::embedded(), port),
        };
        if let Some(mode) = mode {
            host.mode = mode;
        }
        host
    }
}

pub fn default_lobby_name(player: &str) -> String {
    format!("{}'S GAME", player.trim().to_uppercase())
}

/// The most players a hosted game takes (host included): the mode's limit and the netcode's remote slots
/// plus the host, rounded down to an even number (teams of equal size).
pub fn max_players_cap(data: &GameData) -> u32 {
    max_players_cap_for(data, vetf_net::MatchMode::Tdm)
}

/// The most players a game of `mode` takes (host included): the mode's limit and the netcode's remote slots
/// plus the host; even in team deathmatch.
pub fn max_players_cap_for(data: &GameData, mode: vetf_net::MatchMode) -> u32 {
    crate::server::mode_max_players(data, mode, data.net.max_remote_clients + 1)
}

/// Netcode client slots for a game of `max_players`: the host plays through a local link, not a netcode
/// connection, so it does not take a slot.
pub fn netcode_max_clients(max_players: u32) -> usize {
    max_players.saturating_sub(1).max(1) as usize
}

/// The lowest port HOST GAME accepts (below are system ports).
pub const MIN_HOST_PORT: u16 = 1024;

/// A port typed in HOST GAME: digits only, 1024-65535.
pub fn parse_host_port(text: &str) -> Option<u16> {
    let t = text.trim();
    if t.is_empty() || t.len() > 5 || !t.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    t.parse::<u16>().ok().filter(|p| *p >= MIN_HOST_PORT)
}

/// Can we host on UDP `port`? (Bind and release it; the server binds it right after.)
pub fn check_port_free(port: u16) -> Result<(), String> {
    UdpSocket::bind(SocketAddr::new(Ipv4Addr::UNSPECIFIED.into(), port))
        .map(drop)
        .map_err(|e| format!("Cannot host on UDP {port}: {}. Pick another port.", port_error_text(&e)))
}

fn port_error_text(e: &std::io::Error) -> String {
    match e.kind() {
        std::io::ErrorKind::AddrInUse => "the port is in use (is another game hosting?)".into(),
        std::io::ErrorKind::PermissionDenied => "permission denied".into(),
        _ => e.to_string(),
    }
}

/// A private or local address (LAN, VPN mesh such as Tailscale's 100.64/10, or this machine).
pub fn is_lan_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            v4.is_private() || v4.is_loopback() || v4.is_link_local() || (o[0] == 100 && (o[1] & 0xC0) == 64)
        }
        IpAddr::V6(v6) => v6.is_loopback(),
    }
}

/// What to store for a typed join text: a canonical join code, or "ip:port" (`by_ip`). None if it does
/// not parse.
pub fn canonical_join_text(text: &str, default_port: u16) -> Option<(String, bool)> {
    if let Some(id) = iroh_transport::parse_invite(text) {
        return Some((iroh_transport::invite(id), false));
    }
    if let Some(addr) = JoinCode::decode(text.trim()) {
        return Some((JoinCode::encode(addr), false));
    }
    JoinCode::parse(text, default_port).map(|a| (a.to_string(), true))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Role {
    #[default]
    Offline,
    Host,
    Client,
}

/// The current network session.
#[derive(Resource, Default)]
pub struct Session {
    pub role: Role,
    internet: Option<Bridge>,
    pub server: Option<Entity>,
    pub client: Option<Entity>,
    /// Shown in the lobby / scoreboard so friends can join.
    pub join_code: Option<String>,
    /// Internet setup failures do not interrupt offline practice or existing LAN players.
    pub internet_error: Option<String>,
    pub lan_addr: Option<SocketAddr>,
    /// Last connection problem, shown on the main menu.
    pub status: Option<String>,
    /// `status` is a hosting failure (the menu shows it in HOST GAME rather than JOIN GAME).
    pub host_error: bool,
    pub local_name: String,
    /// While hosting: the lobby's name and who may join (from [`HostSettings`]), for the lobby, scoreboard
    /// and ESC menu. Not replicated yet.
    pub lobby_name: Option<String>,
    pub access: JoinAccess,
}

/// Requests from the menu (or the command line).
#[derive(Message, Debug, Clone)]
pub enum NetRequest {
    /// `lobby`: a team deathmatch opens in the lobby (false: straight into the match, `--live`).
    Host {
        map: String,
        lobby: bool,
    },
    Join {
        address: String,
    },
    Leave {
        reason: Option<String>,
    },
}

fn auto_start(cli: Res<Cli>, mut requests: MessageWriter<NetRequest>) {
    if let Some(map) = &cli.host {
        let map = if map.is_empty() { "showhome".into() } else { map.clone() };
        requests.write(NetRequest::Host { map, lobby: !cli.live });
    } else if let Some(address) = &cli.join {
        requests.write(NetRequest::Join { address: address.clone() });
    }
}

fn handle_requests(
    mut requests: MessageReader<NetRequest>,
    mut commands: Commands,
    mut session: ResMut<Session>,
    mut next: ResMut<NextState<AppState>>,
    data: Res<Data>,
    host: Res<HostSettings>,
    replicated: Query<Entity, Or<(With<Replicate>, With<lightyear::prelude::client::Remote>)>>,
    mut closing: ResMut<Closing>,
) {
    for req in requests.read() {
        match req {
            NetRequest::Host { map, lobby } => {
                if session.role != Role::Offline {
                    continue;
                }
                let port = host.port;
                if let Err(e) = check_port_free(port) {
                    warn!("{e}");
                    session.status = Some(e);
                    session.host_error = true;
                    continue;
                }
                let mode = if map.eq_ignore_ascii_case("range") { vetf_net::MatchMode::Range } else { host.mode };
                let max_players = host.max_players.clamp(2, max_players_cap_for(&data, mode));
                session.internet_error = None;
                if host.access == JoinAccess::JoinCode {
                    match Bridge::host(port, netcode_max_clients(max_players)) {
                        Ok(bridge) => session.internet = Some(bridge),
                        Err(e) => {
                            session.status = Some(format!("Cannot start internet hosting: {e}"));
                            session.host_error = true;
                            continue;
                        }
                    }
                }
                let level = level_by_name(map);
                info!("hosting {} on UDP {port} for up to {max_players} players", level.name);
                commands.insert_resource(CurrentLevel(Arc::new(level)));
                commands.insert_resource(ReplicationMetadata::new(Duration::from_secs_f64(
                    1.0 / data.net.snapshot_hz.max(1) as f64,
                )));
                let server = commands
                    .spawn((
                        Name::new("Server"),
                        NetcodeServer::new(ServerNetcodeConfig {
                            protocol_id: vetf_net::protocol_id(),
                            private_key: vetf_net::PRIVATE_KEY,
                            max_clients: netcode_max_clients(max_players),
                            // Friends dial our LAN / public / VPN address, not 0.0.0.0.
                            server_addr_check: false,
                            ..default()
                        }),
                        LocalAddr(SocketAddr::new(Ipv4Addr::UNSPECIFIED.into(), port)),
                        ServerUdpIo::default(),
                    ))
                    .id();
                let client = commands.spawn((Client, Name::new("HostClient"), LinkOf { server })).id();
                commands.trigger(Start { entity: server });
                commands.trigger(Connect { entity: client });
                let lan = local_ipv4().map(|ip| SocketAddr::V4(SocketAddrV4::new(ip, port)));
                session.role = Role::Host;
                session.server = Some(server);
                session.client = Some(client);
                session.lan_addr = lan;
                // An invite host gets its SL1 invite from the Iroh worker in a few seconds; Direct IP and
                // LAN-only hosts are joined at ip:port (see `invite::JoinInfo`).
                session.join_code = if host.access == JoinAccess::JoinCode { None } else { lan.map(|a| a.to_string()) };
                session.status = None;
                session.host_error = false;
                session.lobby_name = Some(host.lobby_name_for(&session.local_name));
                session.access = host.access;
                if let Some(addr) = &session.join_code {
                    info!("friends join at {addr}");
                }
                let lobby_name = session.lobby_name.clone().unwrap_or_default();
                crate::server::spawn_match(&mut commands, &data, map, mode, lobby_name, max_players, *lobby);
                next.set(AppState::Connecting);
            }
            NetRequest::Join { address } => {
                if session.role != Role::Offline {
                    continue;
                }
                session.host_error = false;
                let internet_id = iroh_transport::parse_invite(address);
                let server_addr = if let Some(id) = internet_id {
                    match Bridge::join(id) {
                        Ok((bridge, addr)) => {
                            session.internet = Some(bridge);
                            Some(addr)
                        }
                        Err(e) => {
                            session.status = Some(format!("Cannot start internet join: {e}"));
                            continue;
                        }
                    }
                } else {
                    JoinCode::parse(address, data.net.port)
                };
                let Some(server_addr) = server_addr else {
                    session.status = Some(format!("\"{}\" is not an invite or address.", address.trim()));
                    continue;
                };
                let client_id = random_client_id();
                info!("joining {server_addr} as client {client_id:x}");
                let auth = Authentication::Manual {
                    server_addr,
                    client_id,
                    private_key: vetf_net::PRIVATE_KEY,
                    protocol_id: vetf_net::protocol_id(),
                };
                let config = ClientNetcodeConfig {
                    client_timeout_secs: if internet_id.is_some() { 45 } else { 5 },
                    token_expire_secs: -1,
                    ..default()
                };
                let netcode = match NetcodeClient::new(auth, config) {
                    Ok(n) => n,
                    Err(e) => {
                        session.internet = None;
                        session.status = Some(format!("cannot create a connection: {e:?}"));
                        continue;
                    }
                };
                commands.insert_resource(PredictionManager::default());
                let client = commands
                    .spawn((
                        Name::new("Client"),
                        Client,
                        ReplicationReceiver,
                        Link::default(),
                        LocalAddr(SocketAddr::new(Ipv4Addr::UNSPECIFIED.into(), 0)),
                        PeerAddr(server_addr),
                        netcode,
                        UdpIo::default(),
                    ))
                    .id();
                commands.trigger(Connect { entity: client });
                session.role = Role::Client;
                session.client = Some(client);
                session.join_code = Some(address.clone());
                session.status = Some(if internet_id.is_some() {
                    "Connecting to internet host...".into()
                } else {
                    format!("connecting to {server_addr}...")
                });
                next.set(AppState::Connecting);
            }
            NetRequest::Leave { reason } => {
                let bridge = session.internet.take();
                session.internet_error = None;
                if let Some(server) = session.server.take() {
                    commands.trigger(Stop { entity: server });
                    commands.entity(server).try_despawn();
                }
                if let Some(client) = session.client.take() {
                    if session.role == Role::Client {
                        commands.trigger(Disconnect { entity: client });
                        // Keep the link (and Iroh bridge) a moment so the disconnect packets reach the host.
                        // Otherwise it only notices at the timeout, with our player left standing there.
                        if let Some(old) = closing.client.replace(client) {
                            commands.entity(old).try_despawn();
                        }
                        closing.bridge = bridge;
                        closing.left_s = 0.5;
                    } else {
                        commands.entity(client).try_despawn();
                    }
                }
                // Players and the match state of the game we left (ours if we hosted, the host's copies if we
                // joined). A stale player would keep `Controlled`, and the next game's camera would follow it.
                for e in &replicated {
                    commands.entity(e).try_despawn();
                }
                commands.remove_resource::<CurrentLevel>();
                session.role = Role::Offline;
                session.join_code = None;
                session.lobby_name = None;
                session.status = reason.clone();
                session.host_error = false;
                next.set(AppState::MainMenu);
            }
        }
    }
}

/// A connection we just left, kept until its disconnect packets are out.
#[derive(Resource, Default)]
struct Closing {
    client: Option<Entity>,
    bridge: Option<Bridge>,
    left_s: f32,
}

fn finish_closing(mut closing: ResMut<Closing>, time: Res<Time>, mut commands: Commands) {
    if closing.client.is_none() {
        return;
    }
    closing.left_s -= time.delta_secs();
    if closing.left_s <= 0.0 {
        if let Some(client) = closing.client.take() {
            commands.entity(client).try_despawn();
        }
        closing.bridge = None;
    }
}

/// A connected client (remote or the host's own) introduces itself.
fn on_client_connected(
    trigger: On<Add, Connected>,
    mut senders: Query<&mut MessageSender<Hello>, With<Client>>,
    session: Res<Session>,
    data: Res<Data>,
    active: Option<Res<crate::loadout::ActiveLoadout>>,
    cli: Res<Cli>,
) {
    let Ok(mut sender) = senders.get_mut(trigger.entity) else { return };
    let loadout = active.map(|a| a.0.clone()).unwrap_or_else(|| crate::config::loadout_choice(&cli, &data));
    info!("asking for loadout {loadout:?}");
    sender.send::<ReliableChannel>(Hello {
        name: session.local_name.clone(),
        loadout,
        data_fingerprint: data.fingerprint,
    });
    info!("connected; sent hello");
}

/// Our connection to a host dropped (or never came up): back to the menu.
fn on_client_disconnected(
    trigger: On<Add, Disconnected>,
    clients: Query<&Disconnected, With<Client>>,
    session: Res<Session>,
    mut requests: MessageWriter<NetRequest>,
) {
    if session.role != Role::Client || session.client != Some(trigger.entity) {
        return;
    }
    let Ok(d) = clients.get(trigger.entity) else { return };
    // `Disconnected` is also inserted once at spawn (reason Unknown) before connecting.
    if matches!(d.reason, DisconnectedReason::Unknown | DisconnectedReason::UserRequested(_)) {
        return;
    }
    warn!("disconnected: {:?}", d.reason);
    requests.write(NetRequest::Leave { reason: Some(disconnect_text(&d.reason)) });
}

/// Why we are back on the menu, as JOIN GAME shows it.
pub fn disconnect_text(reason: &DisconnectedReason) -> String {
    match reason {
        DisconnectedReason::TransportError(e) if e.contains("TimedOut") => {
            "No answer from the host (timed out). Check the code, and that the host's UDP port is reachable.".into()
        }
        DisconnectedReason::ByPeer(Some(r)) => format!("The host closed the connection: {r}."),
        DisconnectedReason::ByPeer(None) => "The host closed the connection.".into(),
        DisconnectedReason::LinkFailed(r) => format!("Connection lost ({r})."),
        DisconnectedReason::TransportError(e) => format!("Connection error ({e})."),
        other => format!("Disconnected ({other})."),
    }
}

/// Set when a client reaches the match; [`record_recent`] then adds the game to `recent.ron`.
#[derive(Resource, Debug, Default)]
struct RecentPending {
    armed: bool,
    waited_s: f32,
}

fn arm_recent(session: Res<Session>, mut pending: ResMut<RecentPending>) {
    *pending = RecentPending { armed: session.role == Role::Client, waited_s: 0.0 };
}

/// After joining a game, remember it in RECENT (once the match state is in; the host's name may take a
/// moment longer to replicate).
fn record_recent(
    mut pending: ResMut<RecentPending>,
    session: Res<Session>,
    data: Res<Data>,
    matches: Query<&MatchState>,
    players: Query<(&PlayerId, &PlayerInfo)>,
    mut recent: ResMut<RecentServers>,
    time: Res<Time>,
) {
    if !pending.armed {
        return;
    }
    pending.waited_s += time.delta_secs();
    let Some(m) = matches.iter().next() else { return };
    let host = players.iter().find(|(id, _)| id.0 == 0).map(|(_, info)| info.name.clone());
    if host.is_none() && pending.waited_s < 3.0 {
        return;
    }
    pending.armed = false;
    let Some((address, by_ip)) = session.join_code.as_deref().and_then(|t| canonical_join_text(t, data.net.port))
    else {
        return;
    };
    let last_joined =
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or_default();
    recent.record(RecentServer {
        name: default_lobby_name(host.as_deref().unwrap_or("HOST")),
        map: m.map.clone(),
        address,
        by_ip,
        last_joined,
    });
    if let Err(e) = crate::user_config::save(RecentServers::FILE, &*recent) {
        warn!("cannot save recent games: {e}");
    }
}

/// The machine's LAN address (no packets are sent: connecting a UDP socket only picks a route).
pub fn local_ipv4() -> Option<Ipv4Addr> {
    let sock = UdpSocket::bind("0.0.0.0:0").ok()?;
    sock.connect("8.8.8.8:80").ok()?;
    match sock.local_addr().ok()? {
        SocketAddr::V4(a) if !a.ip().is_unspecified() => Some(*a.ip()),
        _ => Some(Ipv4Addr::LOCALHOST),
    }
}

fn random_client_id() -> u64 {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    // Never 0: that is the host's id.
    vetf_sim::rng::SplitMix::from_parts(&[nanos as u64, std::process::id() as u64]).next_u64().max(1)
}

/// Network work stays off the render thread; only lifecycle events cross into Bevy.
fn poll_internet(mut session: ResMut<Session>, mut requests: MessageWriter<NetRequest>) {
    while let Some(event) = session.internet.as_ref().and_then(Bridge::poll) {
        match event {
            InternetEvent::Ready(invite) => {
                info!("Internet invite: {invite}");
                session.join_code = Some(invite);
            }
            InternetEvent::Failed(error) => {
                warn!("{error}");
                if session.role == Role::Host {
                    session.internet_error = Some(error);
                    session.internet = None;
                } else {
                    requests.write(NetRequest::Leave { reason: Some(error) });
                }
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_settings_follow_the_data() {
        let d = GameData::embedded();
        let cap = max_players_cap(&d);
        assert_eq!(cap % 2, 0, "teams of equal size");
        assert!(cap <= d.rules.tdm.max_players && cap <= d.net.max_remote_clients + 1);
        let h = HostSettings::new(&d, None);
        assert_eq!((h.port, h.max_players), (d.net.port, cap));
        assert_eq!(h.mode, vetf_net::MatchMode::Tdm, "team deathmatch unless HOST GAME or --mode says otherwise");
        // Free-for-all seats its own number (8), and need not be even.
        let ffa = max_players_cap_for(&d, vetf_net::MatchMode::Ffa);
        assert_eq!(ffa, d.rules.ffa.max_players.min(d.net.max_remote_clients + 1));
        assert!(ffa <= cap);
        assert_eq!(HostSettings::new(&d, Some(50000)).port, 50000, "--port overrides net.ron");
        // The host plays over a local link: a 10-player game takes 9 netcode slots.
        assert_eq!(netcode_max_clients(10), 9);
        assert_eq!(netcode_max_clients(2), 1);
    }

    #[test]
    fn lobby_names_default_to_the_players_game() {
        let mut h = HostSettings::new(&GameData::embedded(), None);
        assert_eq!(h.lobby_name_for("ash"), "ASH'S GAME");
        h.lobby_name = "  Range night ".into();
        assert_eq!(h.lobby_name_for("ash"), "Range night");
        h.lobby_name = "x".repeat(40);
        assert_eq!(h.lobby_name_for("ash").len(), HostSettings::LOBBY_NAME_MAX);
    }

    #[test]
    fn host_ports_are_digits_from_1024() {
        assert_eq!(parse_host_port("47820"), Some(47820));
        assert_eq!(parse_host_port(" 1024 "), Some(1024));
        assert_eq!(parse_host_port("1023"), None);
        assert_eq!(parse_host_port("65536"), None);
        assert_eq!(parse_host_port("4782a"), None);
        assert_eq!(parse_host_port(""), None);
        assert_eq!(parse_host_port("000047820"), None, "at most five digits");
    }

    #[test]
    fn a_busy_port_is_reported_before_hosting() {
        let taken = UdpSocket::bind("0.0.0.0:0").unwrap();
        let port = taken.local_addr().unwrap().port();
        let err = check_port_free(port).unwrap_err();
        assert!(err.contains(&port.to_string()), "{err}");
        drop(taken);
        assert!(check_port_free(port).is_ok());
    }

    #[test]
    fn lan_addresses_and_join_texts() {
        for ip in ["192.168.1.40", "10.0.0.2", "172.20.1.1", "100.64.12.7", "127.0.0.1"] {
            assert!(is_lan_ip(ip.parse().unwrap()), "{ip}");
        }
        for ip in ["8.8.8.8", "100.128.0.1", "172.32.0.1"] {
            assert!(!is_lan_ip(ip.parse().unwrap()), "{ip}");
        }
        let addr = SocketAddrV4::new(Ipv4Addr::new(192, 168, 1, 40), 47820);
        let code = JoinCode::encode(addr);
        assert_eq!(canonical_join_text(&code.to_lowercase().replace('-', ""), 47820), Some((code, false)));
        assert_eq!(canonical_join_text("192.168.1.40", 47820), Some(("192.168.1.40:47820".into(), true)));
        assert_eq!(canonical_join_text("nope", 47820), None);
        let invite = iroh_transport::invite(iroh::SecretKey::from_bytes(&[8; 32]).public());
        assert_eq!(canonical_join_text(&invite.to_lowercase(), 47820), Some((invite, false)));
    }

    #[test]
    fn disconnect_reasons_read_as_sentences() {
        let t = disconnect_text(&DisconnectedReason::TransportError("ConnectionRequestTimedOut".into()));
        assert!(t.starts_with("No answer from the host"), "{t}");
        assert_eq!(disconnect_text(&DisconnectedReason::ByPeer(None)), "The host closed the connection.");
        assert!(disconnect_text(&DisconnectedReason::TransportError("x".into())).contains("(x)"));
    }
}
