# SHARD/LINE website

A small, self-contained static info page served by Nginx with Docker Compose.
All artwork, fonts and scripts are local. No Node build, database, analytics,
external fonts or hosting account is required. Concept artwork is labeled as such.

## Run on TrueNAS

Use a TrueNAS installation with Docker Compose available. Copy **this entire
`website` directory**, including `public`, `nginx.conf` and the empty `downloads`
directory, to a dataset, for example `/mnt/tank/apps/shardline-web`.
Replace `tank` with your actual pool name. From the TrueNAS shell:

```sh
cd /mnt/tank/apps/shardline-web
cp .env.example .env
docker compose config
docker compose up -d
```

Open `http://YOUR-TRUENAS-IP:8080`. Change `WEB_PORT` in `.env` if that port is
already taken, then run `docker compose up -d` again. The first start downloads
the official Nginx image. Subsequent website requests need no third-party services.
This Compose project is intended to be run from this directory in the shell;
pasting the YAML alone into an app editor does not copy the required files.

The website is an HTTP server. For an existing HTTPS reverse proxy, point it at
the TrueNAS IP and chosen `WEB_PORT`. This container serves the info page and
installer only; multiplayer sessions are hosted by the game on players' PCs.

## Publish the installer

No installer was found in the repository when this page was created. This
website does **not** build or package the game into an installer.

Put the real Windows installer at:

```text
downloads/SHARDLINE-Setup.exe
```

The button checks that the file is available and nonempty, then shows a download
link and size. Without it, the page displays “Installer coming soon”. The page
rechecks every minute. The check verifies availability, not installer validity.
Only this exact filename is served from the downloads directory.

To use a separate dataset, set an absolute path in `.env`:

```dotenv
WEB_PORT=8080
DOWNLOADS_DIR=/mnt/tank/shardline-downloads
```

Create that directory first, put `SHARDLINE-Setup.exe` inside, and run
`docker compose up -d`. Dataset permissions/ACLs must allow the container's Nginx
worker to read the installer and traverse its directory. All container mounts
are read-only. Keep `.env` local; installers are ignored by Git.

Upload new versions to a temporary filename in the **same downloads directory**,
then rename into place after the upload finishes so visitors cannot fetch a
partially uploaded installer:

```sh
mv downloads/SHARDLINE-Setup.exe.upload downloads/SHARDLINE-Setup.exe
```

No container rebuild or restart is required for content or installer updates.

## Operate and check

```sh
docker compose ps
docker compose logs --tail=50 website
curl -f http://127.0.0.1:8080/healthz
curl -I http://127.0.0.1:8080/downloads/SHARDLINE-Setup.exe
docker compose exec website nginx -t
```

The installer returns 404 until it is published; afterward expect 200,
`Content-Disposition: attachment` and its actual `Content-Length`. Nginx supports
byte-range requests for resumed downloads. Test a full download before sharing.

Update the server image with `docker compose pull && docker compose up -d`.
Stop with `docker compose down`; downloaded files stay on the dataset.

## Edit

- `public/index.html`: copy and page sections.
- `public/style.css`: responsive layout and colors.
- `public/download.js`: download availability and filename.
- `public/assets`: project concept art, Barlow fonts and their license.
- `nginx.conf`: HTTP routes and installer response headers.

If renaming the installer, update `nginx.conf`, `public/download.js`, and the
download filename / no-JavaScript fallback in `public/index.html` together.

Compose syntax reference: https://docs.docker.com/reference/compose-file/services/
Official server image: https://hub.docker.com/_/nginx/
