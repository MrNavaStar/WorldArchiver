# World Archiver

<img src="https://github.com/MrNavaStar/WorldArchiver/blob/master/screenshot.png">

An easy and simple way to share your past minecraft worlds with your friends!

## Run with Docker

The repository now includes a Docker setup that runs the app with **Python 3** and **Java 25**.

### Prerequisites
- Docker
- Docker Compose (v2)

### Build the image

```bash
docker build -t worldarchiver .
```

### Run with `docker run`

Create a local directory called `worlds` and put your archived Minecraft world folders there.

```bash
docker run --rm \
  -p 80:80 \
  -e PORT=80 \
  -v "$(pwd)/worlds:/worlds" \
  worldarchiver
```

Then open: <http://localhost>

### OIDC authentication for uploads

Uploading worlds is now restricted to authenticated users. Configure OIDC and session settings to enable sign-in:

- `SESSION_SECRET`: secret key used to sign session cookies.
- `OIDC_CLIENT_ID`: OIDC client ID.
- `OIDC_CLIENT_SECRET`: OIDC client secret.
- `OIDC_DISCOVERY_URL`: provider discovery URL, for example `https://accounts.google.com/.well-known/openid-configuration`.
- `OIDC_SCOPES` (optional): defaults to `openid profile email`.

If OIDC is configured, the home page shows a **Sign in** link and only logged-in users will see the **Upload World** button. Direct `POST /upload` requests from unauthenticated users return `403 Authentication required`.


### Expected `/worlds` folder structure

Each world entry should be a folder under `./worlds` containing at least `info.json` and a zipped world file.

```text
worlds/
  MyServerOne/
    info.json
    MyServerOne.zip
    images/
      preview1.png
      preview2.png
    mods.zip            # optional

  MyServerTwo/
    info.json
    MyServerTwo.zip
```

Notes:
- `info.json` is required for each server folder.
- `images/` is optional but recommended for thumbnails.
- `mods.zip` is optional and will be added to BlueMap resourcepacks if present.

### Run with Docker Compose

The included `docker-compose.yml` expects your world archive data at `./worlds` (mounted to `/worlds` in the container).

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up --build -d
```

Stop the stack:

```bash
docker compose down
```
