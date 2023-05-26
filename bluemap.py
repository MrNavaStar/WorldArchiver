import os
import shutil
import subprocess
from urllib.request import urlretrieve
from zipfile import ZipFile

from requests import get


class BlueMap:

    def __init__(self, directory: str):
        self.dir = directory
        self.jar = ""
        self.mc_versions = get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json").json()
        self.downloadJar()

    def downloadJar(self):
        latest_release = get("https://api.github.com/repos/BlueMap-Minecraft/BlueMap/releases").json()[0]

        for asset in latest_release["assets"]:
            name = asset["name"]
            if "cli" in name:
                self.jar = name
                if not os.path.exists(f"{self.dir}/{name}"):
                    print(f"Downloading: {name}")
                    urlretrieve(asset['browser_download_url'], f"{self.dir}/{name}")
                break

    def _runJar(self, blocking: bool, *args):
        cmd = ['java', '-jar', self.jar]
        cmd.extend(args)

        current_dir = os.getcwd()
        os.chdir(self.dir)

        if blocking:
            subprocess.call(cmd)
        else:
            subprocess.Popen(cmd)

        os.chdir(current_dir)

    def modifyConfig(self, conf: str, setting: str, value):
        with open(f"{self.dir}/config/{conf}.conf", "r+") as conf_file:
            data = conf_file.readlines()
            out = ""

            for line in data:
                if "#" not in line.lstrip() and setting in line:
                    line = f"{setting}: {value}\n"
                out += f"{line}"

            conf_file.seek(0)
            conf_file.write(out)
            conf_file.truncate()

    def generateFiles(self, accept_eula=False):
        self._runJar(True, "-g")

        # Remove default maps
        shutil.rmtree(f"{self.dir}/config/maps")
        os.mkdir(f"{self.dir}/config/maps")

        if accept_eula:
            self.modifyConfig("core", "accept-download", True)

    def addMap(self, name: str, world_directory: str, mc_version: str):
        map_conf = f'name: "{name}"\n' \
                   f'world: "{world_directory}"\n' \
                   'sorting: 0\n' \
                   'sky-color: "#7dabff"\n' \
                   'ambient-light: 0.1\n' \
                   'world-sky-light: 15\n' \
                   'remove-caves-below-y: 55\n' \
                   'cave-detection-ocean-floor: -5\n' \
                   'cave-detection-uses-block-light: false\n' \
                   'min-inhabited-time: 0\n' \
                   'render-edges: true\n' \
                   'save-hires-layer: true\n' \
                   'storage: "file"\n' \
                   'ignore-missing-light-data: false\n' \
                   'marker-sets: {}'

        if not os.path.exists(f"{self.dir}/config/resourcepacks/minecraft-client-{mc_version}.jar"):
            for version in self.mc_versions["versions"]:
                if version["id"] == mc_version:
                    print(f"Downloading: Client Jar for: {mc_version}")
                    version_meta = get(version["url"]).json()

                    if not os.path.exists(f"{self.dir}/config/resourcepacks"):
                        os.mkdir(f"{self.dir}/config/resourcepacks")

                    urlretrieve(version_meta["downloads"]["client"]["url"], f"{self.dir}/config/resourcepacks/minecraft-client-{mc_version}.jar")
                    break

        open(f'{self.dir}/config/maps/{name}.conf', 'x').write(map_conf)

    def addMods(self, mod_zip: str):
        with ZipFile(mod_zip, "r") as mods:
            mods.extractall(f"{self.dir}/config/resourcepacks")

    def render(self):
        self._runJar(False, "-r")

    def renderAndServe(self):
        self._runJar(False, "-r", "-w")
