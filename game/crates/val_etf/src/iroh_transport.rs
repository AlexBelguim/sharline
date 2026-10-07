//! Iroh carries Lightyear/netcode packets as unreliable QUIC datagrams.
//! Each remote peer gets its own loopback socket, preserving netcode client identities.
use iroh::{
    Endpoint, EndpointId,
    endpoint::{Connection, presets},
};
use std::{
    net::SocketAddr,
    sync::{Arc, Mutex, mpsc},
    time::Duration,
};
use tokio::{
    net::UdpSocket,
    sync::{Semaphore, oneshot},
    task::JoinSet,
    time::timeout,
};

const ALPN: &[u8] = b"shardline/netcode/1";
const PREFIX: &str = "SL1-";
const MAX_PACKET: usize = 2048;
// Fits QUIC's minimum path MTU including encryption and the fragment header.
const CHUNK: usize = 900;
const HEADER: usize = 8;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

pub fn parse_invite(text: &str) -> Option<EndpointId> {
    let text = text.trim();
    if text.len() != PREFIX.len() + 64 || !text.get(..PREFIX.len())?.eq_ignore_ascii_case(PREFIX) {
        return None;
    }
    let key = &text[PREFIX.len()..];
    if !key.bytes().all(|b| b.is_ascii_hexdigit()) {
        return None;
    }
    key.to_ascii_lowercase().parse().ok()
}

pub fn invite(id: EndpointId) -> String {
    format!("{PREFIX}{id}").to_uppercase()
}

pub enum Event {
    Ready(String),
    Failed(String),
}

/// Drop cancels startup and all forwarding tasks, including on leave/rehost or app exit.
pub struct Bridge {
    stop: Option<oneshot::Sender<()>>,
    events: Mutex<mpsc::Receiver<Event>>,
}

impl Drop for Bridge {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
    }
}

impl Bridge {
    pub fn poll(&self) -> Option<Event> {
        self.events.lock().ok()?.try_recv().ok()
    }

    pub fn host(port: u16, max_peers: usize) -> std::io::Result<Self> {
        Self::start(move |endpoint, events| Box::pin(host(endpoint, port, max_peers, events)))
    }

    pub fn join(id: EndpointId) -> std::io::Result<(Self, SocketAddr)> {
        let socket = std::net::UdpSocket::bind("127.0.0.1:0")?;
        socket.set_nonblocking(true)?;
        let addr = socket.local_addr()?;
        let bridge = Self::start(move |endpoint, _events| Box::pin(join(endpoint, id, socket)))?;
        Ok((bridge, addr))
    }

    fn start<F>(run: F) -> std::io::Result<Self>
    where
        F: FnOnce(
                Endpoint,
                mpsc::Sender<Event>,
            ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<()>> + Send>>
            + Send
            + 'static,
    {
        let (tx, rx) = mpsc::channel();
        let (stop, mut stopped) = oneshot::channel();
        std::thread::Builder::new().name("iroh-network".into()).spawn(move || {
            let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build();
            match runtime {
                Ok(rt) => rt.block_on(async {
                    let result: Result<()> = async {
                        let endpoint = tokio::select! {
                            _ = &mut stopped => return Ok(()),
                            endpoint = endpoint() => endpoint?,
                        };
                        let result = tokio::select! {
                            _ = &mut stopped => Ok(()),
                            result = run(endpoint.clone(), tx.clone()) => result,
                        };
                        // Retain an endpoint outside the cancelled future so leave/failure sends
                        // QUIC close frames and frees remote slots instead of waiting for idle expiry.
                        endpoint.close().await;
                        result
                    }
                    .await;
                    if let Err(e) = result {
                        let _ = tx.send(Event::Failed(format!("Internet connection: {e}")));
                    }
                }),
                Err(e) => {
                    let _ = tx.send(Event::Failed(format!("Cannot start networking: {e}")));
                }
            }
        })?;
        Ok(Self { stop: Some(stop), events: Mutex::new(rx) })
    }
}

async fn endpoint() -> Result<Endpoint> {
    let mut builder = Endpoint::builder(presets::N0).alpns(vec![ALPN.to_vec()]);
    if let Ok(url) = std::env::var("VETF_IROH_RELAY_URL") {
        builder = builder.relay_mode(iroh::RelayMode::Custom(iroh::RelayMap::try_from_iter([url.as_str()])?));
    }
    // A diagnostic mode for exercising fallback even on networks that allow direct connections.
    if std::env::var("VETF_IROH_RELAY_ONLY").as_deref() == Ok("1") {
        builder = builder.clear_ip_transports();
    }
    Ok(builder.bind().await?)
}

async fn host(endpoint: Endpoint, port: u16, max_peers: usize, events: mpsc::Sender<Event>) -> Result<()> {
    timeout(Duration::from_secs(30), endpoint.online()).await?;
    let _ = events.send(Event::Ready(invite(endpoint.id())));
    let slots = Arc::new(Semaphore::new(max_peers));
    let mut peers = JoinSet::new();
    loop {
        tokio::select! {
            incoming = endpoint.accept() => {
                let Some(incoming) = incoming else { return Err("Host endpoint closed".into()); };
                let Ok(slot) = slots.clone().try_acquire_owned() else { incoming.refuse(); continue; };
                peers.spawn(async move {
                    let _slot = slot;
                    let connection = timeout(Duration::from_secs(10), incoming).await??;
                    let socket = UdpSocket::bind("127.0.0.1:0").await?;
                    socket.connect(("127.0.0.1", port)).await?;
                    let result = forward(&connection, &socket).await;
                    connection.close(0u32.into(), b"session ended");
                    result
                });
            },
            _ = peers.join_next(), if !peers.is_empty() => {}
        }
    }
}

async fn join(endpoint: Endpoint, id: EndpointId, socket: std::net::UdpSocket) -> Result<()> {
    let connection = timeout(Duration::from_secs(30), endpoint.connect(id, ALPN)).await??;
    let socket = UdpSocket::from_std(socket)?;
    // Only local programs can reach this socket. Pin it to the game's first sender.
    let mut buf = [0u8; MAX_PACKET + 1];
    let (n, sender) = timeout(Duration::from_secs(10), socket.recv_from(&mut buf)).await??;
    socket.connect(sender).await?;
    let mut sequence = 0;
    send_packet(&connection, &buf[..n], &mut sequence)?;
    let result = forward(&connection, &socket).await;
    connection.close(0u32.into(), b"session ended");
    result
}

fn send_packet(connection: &Connection, packet: &[u8], sequence: &mut u32) -> Result<()> {
    if packet.is_empty() || packet.len() > MAX_PACKET {
        return Ok(());
    }
    let id = *sequence;
    *sequence = sequence.wrapping_add(1);
    let count = packet.len().div_ceil(CHUNK) as u8;
    for (index, part) in packet.chunks(CHUNK).enumerate() {
        let mut frame = Vec::with_capacity(HEADER + part.len());
        frame.extend_from_slice(&id.to_le_bytes());
        frame.push(index as u8);
        frame.push(count);
        frame.extend_from_slice(&(packet.len() as u16).to_le_bytes());
        frame.extend_from_slice(part);
        connection.send_datagram(frame.into())?;
    }
    Ok(())
}

async fn forward(connection: &Connection, socket: &UdpSocket) -> Result<()> {
    let mut buf = [0u8; MAX_PACKET + 1];
    let mut sequence = 1;
    let mut fragments = Reassembly::default();
    loop {
        tokio::select! {
            received = socket.recv(&mut buf) => {
                match received {
                    Ok(n) => send_packet(connection, &buf[..n], &mut sequence)?,
                    // Windows reports an ICMP "port unreachable" from an earlier send as a reset on the
                    // next UDP recv. It is not fatal for a datagram socket, so keep the session alive.
                    Err(e) if e.kind() == std::io::ErrorKind::ConnectionReset => {}
                    Err(e) => return Err(e.into()),
                }
            },
            received = connection.read_datagram() => {
                if let Some(packet) = fragments.push(&received?) { socket.send(&packet).await?; }
            }
        }
    }
}

struct PartialPacket {
    id: u32,
    len: usize,
    mask: u8,
    data: Vec<u8>,
}
#[derive(Default)]
struct Reassembly {
    slots: [Option<PartialPacket>; 32],
}

impl Reassembly {
    fn push(&mut self, frame: &[u8]) -> Option<Vec<u8>> {
        if frame.len() < HEADER {
            return None;
        }
        let id = u32::from_le_bytes(frame[..4].try_into().ok()?);
        let index = frame[4] as usize;
        let count = frame[5] as usize;
        let len = u16::from_le_bytes(frame[6..8].try_into().ok()?) as usize;
        if len == 0 || len > MAX_PACKET || count != len.div_ceil(CHUNK) || index >= count {
            return None;
        }
        let offset = index * CHUNK;
        if frame.len() - HEADER != (len - offset).min(CHUNK) {
            return None;
        }
        let slot = &mut self.slots[id as usize % 32];
        if slot.as_ref().is_none_or(|p| p.id != id || p.len != len) {
            *slot = Some(PartialPacket { id, len, mask: 0, data: vec![0; len] });
        }
        let p = slot.as_mut()?;
        p.data[offset..offset + frame.len() - HEADER].copy_from_slice(&frame[HEADER..]);
        p.mask |= 1 << index;
        if p.mask == (1 << count) - 1 {
            return slot.take().map(|p| p.data);
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invites_are_versioned_case_insensitive_and_strict() {
        let id = iroh::SecretKey::from_bytes(&[7; 32]).public();
        let text = invite(id);
        assert_eq!(parse_invite(&text), Some(id));
        assert_eq!(parse_invite(&format!(" {} ", text.to_lowercase())), Some(id));
        assert_eq!(parse_invite("SL2-deadbeef"), None);
        assert_eq!(parse_invite("127.0.0.1:47820"), None);
        assert_eq!(parse_invite(&"é".repeat(34)), None);
    }
    fn frame(id: u32, index: usize, packet: &[u8]) -> Vec<u8> {
        let mut f = id.to_le_bytes().to_vec();
        f.extend([index as u8, packet.len().div_ceil(CHUNK) as u8]);
        f.extend((packet.len() as u16).to_le_bytes());
        f.extend(&packet[index * CHUNK..packet.len().min((index + 1) * CHUNK)]);
        f
    }
    #[test]
    fn reassembles_maximum_packets_out_of_order_and_rejects_malformed() {
        let packet: Vec<_> = (0..MAX_PACKET).map(|n| n as u8).collect();
        let mut r = Reassembly::default();
        assert!(r.push(&frame(4, 2, &packet)).is_none());
        assert!(r.push(&frame(4, 0, &packet)).is_none());
        assert!(r.push(&frame(4, 0, &packet)).is_none());
        assert_eq!(r.push(&frame(4, 1, &packet)), Some(packet.clone()));
        assert!(r.push(&[0; 8]).is_none());
        let mut invalid = frame(5, 0, &packet);
        invalid[4] = 255;
        assert!(r.push(&invalid).is_none());
        assert!(r.push(&frame(6, 0, &packet)).is_none());
        assert_eq!(r.push(&frame(7, 0, b"next")), Some(b"next".to_vec()));
    }

    /// Exercises real QUIC, packet fragmentation and both loopback directions without public services.
    #[tokio::test]
    async fn local_quic_bridge_roundtrip() -> Result<()> {
        timeout(Duration::from_secs(15), async {
            let host = Endpoint::builder(presets::Minimal).alpns(vec![ALPN.to_vec()]).bind().await?;
            let client = Endpoint::builder(presets::Minimal).bind().await?;
            let host_addr = host.addr();
            let accept = async { host.accept().await.ok_or("no incoming connection")?.await.map_err(Into::into) };
            let (server_connection, client_connection): (Result<Connection>, _) =
                tokio::join!(accept, client.connect(host_addr, ALPN));
            let server_connection = server_connection?;
            let client_connection = client_connection?;
            let game_host = UdpSocket::bind("127.0.0.1:0").await?;
            let game_client = UdpSocket::bind("127.0.0.1:0").await?;
            let host_proxy = UdpSocket::bind("127.0.0.1:0").await?;
            let client_proxy = UdpSocket::bind("127.0.0.1:0").await?;
            host_proxy.connect(game_host.local_addr()?).await?;
            client_proxy.connect(game_client.local_addr()?).await?;
            game_client.connect(client_proxy.local_addr()?).await?;
            let host_task = tokio::spawn(async move { forward(&server_connection, &host_proxy).await });
            let client_task = tokio::spawn(async move { forward(&client_connection, &client_proxy).await });
            let packet = vec![42; MAX_PACKET];
            game_client.send(&packet).await?;
            let mut buf = [0; MAX_PACKET + 1];
            let (n, peer) = game_host.recv_from(&mut buf).await?;
            assert_eq!(&buf[..n], &packet);
            game_host.send_to(&buf[..n], peer).await?;
            let n = game_client.recv(&mut buf).await?;
            assert_eq!(&buf[..n], &packet);
            host_task.abort();
            client_task.abort();
            client.close().await;
            host.close().await;
            Ok::<_, Box<dyn std::error::Error + Send + Sync>>(())
        })
        .await?
    }

    /// Opt-in: validates real public discovery, invite dialing, and the session worker lifecycle.
    /// Set VETF_IROH_RELAY_ONLY=1 to exercise the public relay with all direct IP paths disabled.
    #[test]
    #[ignore = "requires public Iroh services; run explicitly for internet smoke testing"]
    fn public_invite_roundtrip_and_shutdown() -> Result<()> {
        let game_host = std::net::UdpSocket::bind("127.0.0.1:0")?;
        game_host.set_read_timeout(Some(Duration::from_secs(40)))?;
        let host = Bridge::host(game_host.local_addr()?.port(), 2)?;
        let deadline = std::time::Instant::now() + Duration::from_secs(40);
        let id = loop {
            match host.poll() {
                Some(Event::Ready(text)) => break parse_invite(&text).ok_or("invalid host invite")?,
                Some(Event::Failed(e)) => return Err(e.into()),
                None if std::time::Instant::now() < deadline => std::thread::sleep(Duration::from_millis(20)),
                None => return Err("host never became ready".into()),
            }
        };
        let (client, addr) = Bridge::join(id)?;
        let game_client = std::net::UdpSocket::bind("127.0.0.1:0")?;
        game_client.set_read_timeout(Some(Duration::from_secs(40)))?;
        let packet = vec![19; MAX_PACKET];
        game_client.send_to(&packet, addr)?;
        let mut buf = [0; MAX_PACKET + 1];
        let (n, peer) = game_host.recv_from(&mut buf)?;
        assert_eq!(&buf[..n], &packet);
        game_host.send_to(&buf[..n], peer)?;
        let (n, _) = game_client.recv_from(&mut buf)?;
        assert_eq!(&buf[..n], &packet);
        drop(client);
        // The proxy socket must be released after leaving, with no orphan worker.
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        loop {
            match std::net::UdpSocket::bind(addr) {
                Ok(socket) => {
                    drop(socket);
                    break;
                }
                Err(_) if std::time::Instant::now() < deadline => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => return Err(e.into()),
            }
        }
        drop(host);
        Ok(())
    }
}
