import json
import os
import random
from zipfile import ZipFile

import uvicorn
from fastapi import FastAPI
from nbt import nbt
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from bluemap import BlueMap

metadata = []
app = FastAPI()
templates = Jinja2Templates(directory="web/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    new_meta = metadata
    for i in range(len(metadata)):
        server = metadata[i]
        new_meta[i]["image"] = random.choice(server["images"])

    return templates.TemplateResponse("index.html", {"request": request, "metadata": new_meta})


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    if "tiles" in request.url.path and ".json" in request.url.path and "gz" not in request.url.path:
        return FileResponse(headers={"Content-Encoding": "gzip", "Content-Type": "application/json"}, path=f"/home/ethan/Documents/Minecraft/server-archive/bluemap/web{request.url.path.replace('/map', '', 1)}.gz")

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


if __name__ == '__main__':
    server_dir = "/home/ethan/Documents/Minecraft/server-archive"

    metadata = getMetaData(server_dir)
    bmap = initBlueMap(server_dir)

    app.mount("/static", StaticFiles(directory="web"), name="static")
    app.mount("/content", StaticFiles(directory=server_dir), name="content")
    app.mount("/map", StaticFiles(directory=f"{server_dir}/bluemap/web", html=True), name="map")

    bmap.render()
    uvicorn.run(app, host="0.0.0.0", port=2002)
