"""Automatic Windows System Proxy Detector & Injector.

Detection order:
  1. Existing environment variables (HTTP_PROXY / HTTPS_PROXY / ALL_PROXY)
  2. urllib.request.getproxies()  (reads IE/WinInet system proxy)
  3. Windows Registry direct read (HKCU Internet Settings)
  4. Active port probing: tries common VPN/proxy local ports
     (Clash=7890, V2RayN=10809, Shadowsocks/generic=1080, Clash SOCKS=7891)
"""

import os
import sys
import socket
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import winreg
except ImportError:
    winreg = None

# Common local proxy ports used by popular Windows VPN/proxy tools
COMMON_PROXY_PORTS = [
    7890,   # Clash for Windows (HTTP)
    10809,  # V2RayN (HTTP)
    1080,   # Shadowsocks / generic SOCKS (also used as HTTP by some tools)
    8080,   # Fiddler / generic HTTP proxy
    7891,   # Clash for Windows (SOCKS5 — httpx needs socksio for this)
    10808,  # V2RayN (SOCKS)
]


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Quick TCP connect check — no data exchanged, just SYN/ACK."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class SystemProxyDetector:
    """Detects active Windows system proxy settings from Registry or system environment."""

    @staticmethod
    def get_windows_registry_proxy() -> Optional[str]:
        """Reads ProxyEnable and ProxyServer directly from Windows Registry."""
        if sys.platform != "win32" or not winreg:
            return None

        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if proxy_enable == 1:
                    proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                    if proxy_server:
                        # Format can be "127.0.0.1:7890" or "http=127.0.0.1:7890;https=127.0.0.1:7890"
                        if "=" in proxy_server:
                            for part in proxy_server.split(";"):
                                if part.startswith("http=") or part.startswith("https="):
                                    addr = part.split("=", 1)[1]
                                    return f"http://{addr}" if not addr.startswith("http") else addr
                        else:
                            return f"http://{proxy_server}" if not proxy_server.startswith("http") else proxy_server
        except Exception:
            pass
        return None

    @staticmethod
    def probe_local_proxy_ports() -> Optional[str]:
        """Fallback: scan common VPN tool ports on 127.0.0.1.
        Returns the first open HTTP proxy URL found, or None.
        Note: skips SOCKS-only ports (7891, 10808) to avoid httpx compatibility issues
        unless socksio is installed.
        """
        http_ports = [7890, 10809, 1080, 8080]
        socks_ports = [7891, 10808]

        for port in http_ports:
            if _is_port_open("127.0.0.1", port):
                return f"http://127.0.0.1:{port}"

        # Try SOCKS5 only if socksio is available
        try:
            import socksio  # noqa: F401
            for port in socks_ports:
                if _is_port_open("127.0.0.1", port):
                    return f"socks5://127.0.0.1:{port}"
        except ImportError:
            pass

        return None

    @classmethod
    def get_active_proxy(cls) -> Optional[str]:
        """Returns active proxy URL from env vars, urllib, Registry, or port scan."""
        # 1. Existing Environment Variables
        env_proxy = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("ALL_PROXY")
        )
        if env_proxy:
            return env_proxy

        # 2. urllib System Proxies (reads WinInet/IE settings)
        proxies = urllib.request.getproxies()
        if "https" in proxies and proxies["https"]:
            p = proxies["https"]
            return p if p.startswith("http") else f"http://{p}"
        if "http" in proxies and proxies["http"]:
            p = proxies["http"]
            return p if p.startswith("http") else f"http://{p}"

        # 3. Windows Registry Direct Detection
        reg_proxy = cls.get_windows_registry_proxy()
        if reg_proxy:
            return reg_proxy

        # 4. Port Probing Fallback (handles cases where registry isn't updated in time)
        return cls.probe_local_proxy_ports()

    @classmethod
    def auto_inject_system_proxy(cls) -> Optional[str]:
        """Detects system proxy and injects into os.environ so httpx trust_env picks it up.
        Prints a one-line status so users know whether proxy was found.
        """
        proxy = cls.get_active_proxy()
        if proxy:
            if not os.environ.get("HTTP_PROXY"):
                os.environ["HTTP_PROXY"] = proxy
            if not os.environ.get("HTTPS_PROXY"):
                os.environ["HTTPS_PROXY"] = proxy
            if not os.environ.get("ALL_PROXY"):
                os.environ["ALL_PROXY"] = proxy
            logger.debug("[proxy] System proxy detected: %s — injected into environment.", proxy)
        else:
            logger.debug("[proxy] No active proxy detected; international API calls may time out without a proxy.")
        return proxy
