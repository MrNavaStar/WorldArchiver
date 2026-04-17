import json
import os
import random
import re
import shutil
from datetime import datetime
from zipfile import ZipFile

import uvicorn
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import PlainTextResponse
from nbt import nbt
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from bluemap import BlueMap

metadata = []
server_dir = "/worlds"
port = int(os.getenv("PORT", "80"))
bmap = None
session_secret = os.getenv("SESSION_SECRET")
oidc_enabled = bool(
    session_secret
    and os.getenv("OIDC_CLIENT_ID")
    and os.getenv("OIDC_CLIENT_SECRET")
    and os.getenv("OIDC_DISCOVERY_URL")
)

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")
if session_secret:
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

oauth = OAuth()
if oidc_enabled:
    oauth.register(
        name="oidc",
        client_id=os.getenv("OIDC_CLIENT_ID"),
        client_secret=os.getenv("OIDC_CLIENT_SECRET"),
        server_metadata_url=os.getenv("OIDC_DISCOVERY_URL"),
        client_kwargs={"scope": os.getenv("OIDC_SCOPES", "openid profile email")}
    )


def get_user(request: Request) -> dict | None:
    return request.session.get("user", None)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    new_meta = metadata
    for i in range(len(metadata)):
        server = metadata[i]
        if len(server["images"]) != 0:
            new_meta[i]["image"] = random.choice(server["images"])

    user = get_user(request) if session_secret else None
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "metadata": new_meta,
            "auth_enabled": oidc_enabled,
            "is_authenticated": user is not None,
            "user": user
        }
    )


@app.get("/login")
async def login(request: Request):
    if not oidc_enabled:
        return PlainTextResponse("OIDC login is not configured.", status_code=503)

    redirect_uri = request.url_for("auth_callback")
    return await oauth.oidc.authorize_redirect(request, str(redirect_uri))


@app.get("/auth/callback")
async def auth_callback(request: Request):
    if not oidc_enabled:
        return PlainTextResponse("OIDC login is not configured.", status_code=503)

    token = await oauth.oidc.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.oidc.userinfo(token=token)
    request.session["user"] = dict(user_info)
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    if session_secret:
        request.session.pop("user", None)
    return RedirectResponse("/", status_code=303)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    if request.url.path.startswith("/map/") and request.url.path.endswith(".json") and ".gz" not in request.url.path:
        gz_path = f"{server_dir}/bluemap/web{request.url.path.replace('/map', '', 1)}.gz"
        if os.path.exists(gz_path):
            return FileResponse(
                headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
                path=gz_path
            )

    response = await call_next(request)
    return response


def getMetaData(dir: str):
    metaData = []

    for folder in os.listdir(dir):
        if folder == "bluemap":
            continue

        subs = os.listdir(f"{dir}/{folder}")

        if "info.json" in subs:
            with open(f"{dir}/{folder}/info.json") as json_file:
                data = json.loads(json_file.read())
                data["map_name"] = data["name"].replace(" ", "_")
        else:
            continue

        if "images" in subs:
            data["images"] = [f"{folder}/images/{image}" for image in os.listdir(f"{dir}/{folder}/images")]

        for sub in subs:
            if sub == "mods.zip":
                data["mods"] = f"{folder}/{sub}"
                continue

            if ".zip" in sub:
                if sub.replace(".zip", "") not in subs:
                    with ZipFile(f"{dir}/{folder}/{sub}", "r") as world:
                        print(f"Extracting: {world.filename}")
                        world.extractall(f"{dir}/{folder}/{sub.replace('.zip', '')}")

                try:
                    level_data = nbt.NBTFile(f"{dir}/{folder}/{sub.replace('.zip', '')}/level.dat", "rb")
                    data["version"] = level_data["Data"]["Version"]["Name"]
                except Exception:
                    data["version"] = "unknown"
                finally:
                    data["world"] = f"{folder}/{sub}"
                    
        metaData.append(data)
    return metaData


def initBlueMap(dir: str) -> BlueMap:
    if not os.path.exists(f"{dir}/bluemap"):
        os.mkdir(f"{dir}/bluemap")

    bmap = BlueMap(f"{dir}/bluemap")
    bmap.generateFiles(True)
    bmap.modifyConfig("webserver", "enabled", False)

    for server in metadata:
        if "world" in server:
            bmap.addMap(server["name"], f"{dir}/{server['world'].replace('.zip', '')}", f"{server['version']}")

        if "mods" in server:
            bmap.addMods(f"{dir}/{server['mods']}")

    return bmap


def slugify_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return cleaned or "world"


def create_world_folder(name: str) -> str:
    slug = slugify_name(name)
    candidate = slug
    suffix = 1

    while os.path.exists(f"{server_dir}/{candidate}"):
        suffix += 1
        candidate = f"{slug}-{suffix}"

    os.makedirs(f"{server_dir}/{candidate}", exist_ok=False)
    return candidate


def save_upload_file(path: str, uploaded_file: UploadFile):
    with open(path, "wb") as destination:
        shutil.copyfileobj(uploaded_file.file, destination)


def format_date_range(start_date: str, end_date: str, fallback: str) -> str:
    if fallback.strip():
        return fallback.strip()

    if not start_date and not end_date:
        return ""

    def to_display(value: str) -> str:
        if not value:
            return ""
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")

    start_display = to_display(start_date)
    end_display = to_display(end_date)

    if start_display and end_display:
        return f"{start_display} - {end_display}"

    return start_display or end_display


@app.post("/upload")
async def upload_world(
    request: Request,
    name: str = Form(...),
    date_start: str = Form(""),
    date_end: str = Form(""),
    date_range: str = Form(""),
    description: str = Form(""),
    world_zip: UploadFile = File(...),
    mods_zip: UploadFile | None = File(None),
    images: list[UploadFile] | None = File(None)
):
    global metadata
    global bmap
    user = get_user(request) if session_secret else None
    if user is None:
        return PlainTextResponse("Authentication required.", status_code=403)

    folder_name = create_world_folder(name)
    world_path = f"{server_dir}/{folder_name}"
    images_path = f"{world_path}/images"
    os.makedirs(images_path, exist_ok=True)

    info = {
        "name": name.strip(),
        "date_range": format_date_range(date_start.strip(), date_end.strip(), date_range),
        "description": description.strip()
    }
    with open(f"{world_path}/info.json", "w") as info_file:
        json.dump(info, info_file, indent=2)

    world_zip_name = "world.zip"
    save_upload_file(f"{world_path}/{world_zip_name}", world_zip)
    await world_zip.close()

    if mods_zip is not None and mods_zip.filename:
        save_upload_file(f"{world_path}/mods.zip", mods_zip)
        await mods_zip.close()

    if images:
        for image in images:
            if not image.filename:
                continue

            safe_image_name = os.path.basename(image.filename)
            save_upload_file(f"{images_path}/{safe_image_name}", image)
            await image.close()

    metadata = getMetaData(server_dir)

    if bmap is not None:
        bmap = initBlueMap(server_dir)
        bmap.render()

    return RedirectResponse("/", status_code=303)


if __name__ == '__main__':
    metadata = getMetaData(server_dir)
    bmap = initBlueMap(server_dir)

    app.mount("/static", StaticFiles(directory="web"), name="static")
    app.mount("/content", StaticFiles(directory=server_dir), name="content")
    app.mount("/map", StaticFiles(directory=f"{server_dir}/bluemap/web", html=True), name="map")

    bmap.render()
    uvicorn.run(app, host="0.0.0.0", port=port)
