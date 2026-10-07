//! Hosting and joining: lightyear server / client entities and the connection lifecycle.
//!
//! Host = listen server: a netcode + UDP server entity plus a local "HostClient" linked to it in the same
//! app (no socket for the host's own player). Join = a netcode + UDP client entity dialling the address
//! from a join code.

use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data, level_by_name};
use bevy::prelude::*;
use lightyear::netcode::client_plugin::NetcodeConfig as ClientNetcodeConfig;
use lightyear::netcode::server_plugin::NetcodeConfig as ServerNetcodeConfig;
use lightyear::prelude::client::NetcodeClient;
use lightyear::prelude::server::{NetcodeServer, ServerUdpIo, Start, Stop};
use lightyear::prelude::*;
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4, UdpSocket};
use std::sync::Arc;
use std::time::Duration;
use vetf_net::{Hello, JoinCode, LoadoutChoice, ReliableChannel};

pub struct NetPlugin;

impl Plugin for NetPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Session>()
            .add_message::<NetRequest>()
            .add_systems(Update, handle_requests)
            .add_systems(Startup, auto_start)
            .add_observer(on_client_connected)
            .add_observer(on_client_disconnected);
    }
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
    pub server: Option<Entity>,
    pub client: Option<Entity>,
    /// Shown in the lobby / scoreboard so friends can join.
    pub join_code: Option<String>,
    pub lan_addr: Option<SocketAddr>,
    /// Last connection problem, shown on the main menu.
    pub status: Option<String>,
    pub local_name: String,
}

/// Requests from the menu (or the command line).
#[derive(Message, Debug, Clone)]
pub enum NetRequest {
    Host { map: String },
    Join { address: String },
    Leave { reason: Option<String> },
}

fn auto_start(cli: Res<Cli>, mut requests: MessageWriter<NetRequest>, mut session: ResMut<Session>) {
    session.local_name = cli.name.clone();
    if let Some(map) = &cli.host {
        requests.write(NetRequest::Host { map: if map.is_empty() { "showhome".into() } else { map.clone() } });
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
    cli: Res<Cli>,
) {
    for req in requests.read() {
        match req {
            NetRequest::Host { map } => {
                if session.role != Role::Offline {
                    continue;
                }
                let port = cli.port.unwrap_or(data.net.port);
                let level = level_by_name(map);
                info!("hosting {} on UDP {port}", level.name);
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
                            max_clients: data.net.max_remote_clients as usize + 1,
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
                session.join_code = lan.and_then(|a| match a {
                    SocketAddr::V4(v4) => Some(JoinCode::encode(v4)),
                    _ => None,
                });
                session.status = None;
                if let Some(code) = &session.join_code {
                    info!("join code {code} ({})", lan.unwrap());
                }
                crate::server::spawn_match(&mut commands, &data, map);
                next.set(AppState::Connecting);
            }
            NetRequest::Join { address } => {
                if session.role != Role::Offline {
                    continue;
                }
                let Some(server_addr) = JoinCode::parse(address, data.net.port) else {
                    session.status = Some(format!("\"{address}\" is not a join code or address"));
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
                let config = ClientNetcodeConfig { client_timeout_secs: 5, token_expire_secs: -1, ..default() };
                let netcode = match NetcodeClient::new(auth, config) {
                    Ok(n) => n,
                    Err(e) => {
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
                session.status = Some(format!("connecting to {server_addr}..."));
                next.set(AppState::Connecting);
            }
            NetRequest::Leave { reason } => {
                if let Some(server) = session.server.take() {
                    commands.trigger(Stop { entity: server });
                    commands.entity(server).try_despawn();
                }
                if let Some(client) = session.client.take() {
                    if session.role == Role::Client {
                        commands.trigger(Disconnect { entity: client });
                    }
                    commands.entity(client).try_despawn();
                }
                commands.remove_resource::<CurrentLevel>();
                session.role = Role::Offline;
                session.join_code = None;
                session.status = reason.clone();
                next.set(AppState::MainMenu);
            }
        }
    }
}

/// A connected client (remote or the host's own) introduces itself.
fn on_client_connected(
    trigger: On<Add, Connected>,
    mut senders: Query<&mut MessageSender<Hello>, With<Client>>,
    session: Res<Session>,
    data: Res<Data>,
) {
    let Ok(mut sender) = senders.get_mut(trigger.entity) else { return };
    let l = &data.rules.default_loadout;
    sender.send::<ReliableChannel>(Hello {
        name: session.local_name.clone(),
        loadout: LoadoutChoice {
            weapon: l.primary.clone(),
            ammo: l.ammo,
            attachments: l.attachments.clone(),
            armor: l.armor.clone(),
        },
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
    requests.write(NetRequest::Leave { reason: Some(format!("disconnected ({:?})", d.reason)) });
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
