import json
import os
import random
import re
import shutil
from zipfile import ZipFile

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from nbt import nbt
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from bluemap import BlueMap

metadata = []
server_dir = "/worlds"
port = int(os.getenv("PORT", "80"))
bmap = None

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    new_meta = metadata
    for i in range(len(metadata)):
        server = metadata[i]
        new_meta[i]["image"] = random.choice(server["images"])

    return templates.TemplateResponse(request, "index.html", {"metadata": new_meta})


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    if "tiles" in request.url.path and ".json" in request.url.path and "gz" not in request.url.path:
        return FileResponse(
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
            path=f"{server_dir}/bluemap/web{request.url.path.replace('/map', '', 1)}.gz"
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

                level_data = nbt.NBTFile(f"{dir}/{folder}/{sub.replace('.zip', '')}/level.dat", "rb")
                data["version"] = level_data["Data"]["Version"]["Name"]
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


@app.post("/upload")
async def upload_world(
    name: str = Form(...),
    date_range: str = Form(...),
    description: str = Form(""),
    world_zip: UploadFile = File(...),
    mods_zip: UploadFile | None = File(None),
    images: list[UploadFile] | None = File(None)
):
    global metadata
    global bmap

    folder_name = create_world_folder(name)
    world_path = f"{server_dir}/{folder_name}"
    images_path = f"{world_path}/images"
    os.makedirs(images_path, exist_ok=True)

    info = {
        "name": name.strip(),
        "date_range": date_range.strip(),
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
