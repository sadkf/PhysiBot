"""NapCatQQ Manager — Deeply robust lifecycle with refined directory detection."""

import json
import logging
import platform
import subprocess
import threading
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class NapCatManager:
    """Manages downloading, configuring, and running NapCatQQ with refined rooting."""

    def __init__(
        self, data_dir: Path, owner_qq: str, reverse_ws_url: str = "ws://127.0.0.1:3001/"
    ) -> None:
        self._data_dir = data_dir
        self._napcat_base = data_dir / "napcat"
        self._owner_qq = owner_qq
        self._reverse_ws_url = reverse_ws_url
        self._process: subprocess.Popen[Any] | None = None
        self._running = False

    async def start(self) -> bool:
        """Ensure NapCatQQ is installed, configured, and running."""
        if platform.system() != "Windows":
            logger.error("NapCatManager strictly supports Windows for now.")
            return False

        await self._ensure_installed()
        real_root = self._get_real_root()
        self._ensure_configured(real_root)
        return await self._launch_daemon(real_root)

    async def stop(self) -> None:
        """Gracefully kill the NapCatQQ process."""
        self._running = False
        if self._process:
            logger.info("Stopping NapCatQQ...")
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                pass
            finally:
                if self._process and self._process.poll() is None:
                    self._process.kill()
            self._process = None

    def _get_real_root(self) -> Path:
        """Find the true NapCat root by locating index.js (strictly outside node_modules)."""
        # We need an index.js that also has a node.exe nearby - that's the real app root.
        all_indices = list(self._napcat_base.rglob("index.js"))

        # Filter out node_modules
        valid_indices = [idx for idx in all_indices if "node_modules" not in str(idx)]

        if not valid_indices:
            # Fallback to the base if nothing found
            return self._napcat_base

        # Select the one that has node.exe or napcat.bat in the same dir
        for idx in valid_indices:
            root = idx.parent
            if (root / "node.exe").exists() or (root / "napcat.bat").exists():
                return root

        # If no binary found nearby, just pick the shallowest one (most likely the top-level)
        return min(valid_indices, key=lambda x: len(x.parts)).parent

    async def _ensure_installed(self) -> None:
        """Download and extract NapCatQQ if not present."""
        if list(self._napcat_base.rglob("index.js")):
            return

        logger.info("📦 NapCatQQ not found. Downloading...")
        self._napcat_base.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
            # 彻底弃用 github api 查询，避免在国内被墙导致超时
            # 直接写死版本号配合 ghfast.top 稳定下载
            mirror_url = "https://ghfast.top/https://github.com/NapNeko/NapCatQQ/releases/download/v4.17.55/NapCat.Shell.Windows.OneKey.zip"
            zip_path = self._data_dir / "napcat_download.zip"

            logger.info("Downloading NapCatQQ from %s", mirror_url)
            with open(zip_path, "wb") as f:
                async with client.stream("GET", mirror_url) as stream:
                    async for chunk in stream.aiter_bytes():
                        f.write(chunk)

            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(self._napcat_base)
            finally:
                zip_path.unlink(missing_ok=True)
            logger.info("✅ NapCatQQ installed.")

    def _ensure_configured(self, root: Path) -> None:
        """Write NapCat config to both the legacy and the napcat-plugin config dirs."""
        parsed_ws = urlparse(self._reverse_ws_url)
        reverse_ws_url = self._reverse_ws_url
        if not parsed_ws.scheme or not parsed_ws.netloc:
            reverse_ws_url = "ws://127.0.0.1:3001/"

        # Normalise: replace "localhost" → "127.0.0.1" so NapCat doesn't resolve to ::1
        reverse_ws_url = reverse_ws_url.replace("localhost", "127.0.0.1")

        # NapCatQQ (standalone) reads its onebot11 config from  <root>/napcat/config/
        # The outer <root>/config/ is used only for the global QQ/NapCat identity config.
        napcat_config_dir = root / "napcat" / "config"
        napcat_config_dir.mkdir(parents=True, exist_ok=True)

        # 1. Global NapCat identity config (written to both locations for safety)
        global_config = {
            "version": 1,
            "qq": self._owner_qq,
            "p": "onebot11",
            "webui": {"enable": True, "port": 6100, "token": "physibot"},
        }
        outer_config_dir = root / "config"
        outer_config_dir.mkdir(parents=True, exist_ok=True)
        for cfg_dir in [outer_config_dir, napcat_config_dir]:
            for f in ["napcat.json", f"napcat_{self._owner_qq}.json"]:
                with open(cfg_dir / f, "w", encoding="utf-8") as file:
                    json.dump(global_config, file, indent=4)

        # 2. OneBot11 network config — newer NapCat uses "network" wrapper schema
        ob_config = {
            "network": {
                "httpServers": [
                    {
                        "name": "PhysiBot-HTTP",
                        "enable": True,
                        "host": "0.0.0.0",
                        "port": 3000,
                        "enableCors": True,
                        "enableWebsocket": False,
                        "messagePostFormat": "array",
                        "token": "",
                    }
                ],
                "websocketServers": [],
                "websocketClients": [
                    {
                        "name": "PhysiBot-Reverse",
                        "enable": True,
                        "url": reverse_ws_url,
                        "reconnectInterval": 3000,
                        "token": "",
                    }
                ],
                "httpClients": [],
            },
            "reportSelfMessage": True,
            "log": {"level": "info"},
        }

        for f in ["onebot11.json", f"onebot11_{self._owner_qq}.json"]:
            with open(napcat_config_dir / f, "w", encoding="utf-8") as file:
                json.dump(ob_config, file, indent=4)

        logger.info(
            "NapCat configured: ws_url=%s, config_dir=%s", reverse_ws_url, napcat_config_dir
        )

    async def _launch_daemon(self, root: Path) -> bool:
        """Spawn NapCat from the detected true root."""
        import shutil

        exe = root / "node.exe"
        if not exe.exists():
            exe = root.parent / "node.exe"  # Fallback if node.exe is one level up

        exe_str = str(exe)
        if not exe.exists():
            system_node = shutil.which("node")
            if system_node:
                exe_str = system_node
                logger.info("Using system node: %s", system_node)
            else:
                logger.error("No node.exe found at %s or in PATH", root)
                return False

        cmd = [exe_str, "./index.js", "-q", self._owner_qq]
        logger.info("Booting NapCat from root: %s", root)

        self._process = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self._running = True

        def _read_output() -> None:
            if not self._process or not self._process.stdout:
                return
            verbose = False
            for line in iter(self._process.stdout.readline, ""):
                if not self._running:
                    break
                stripped = line.strip()
                if stripped and verbose:
                    safe = stripped.encode("ascii", errors="ignore").decode()
                    if safe:
                        print(safe, flush=True)

        threading.Thread(target=_read_output, daemon=True).start()
        return True
