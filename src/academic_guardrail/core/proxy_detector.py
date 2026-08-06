"""Automatic Windows System Proxy Detector & Injector."""

import os
import sys
import urllib.request
from typing import Optional, Dict

try:
    import winreg
except ImportError:
    winreg = None


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
                                    addr = part.split("=")[1]
                                    return f"http://{addr}" if not addr.startswith("http") else addr
                        else:
                            return f"http://{proxy_server}" if not proxy_server.startswith("http") else proxy_server
        except Exception:
            pass
        return None

    @classmethod
    def get_active_proxy(cls) -> Optional[str]:
        """Returns active proxy URL from env vars or Windows Registry."""
        # 1. Existing Environment Variables
        env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
        if env_proxy:
            return env_proxy

        # 2. urllib System Proxies
        proxies = urllib.request.getproxies()
        if "https" in proxies:
            return proxies["https"] if proxies["https"].startswith("http") else f"http://{proxies['https']}"
        if "http" in proxies:
            return proxies["http"] if proxies["http"].startswith("http") else f"http://{proxies['http']}"

        # 3. Windows Registry Direct Detection
        return cls.get_windows_registry_proxy()

    @classmethod
    def auto_inject_system_proxy(cls) -> Optional[str]:
        """Automatically injects detected system proxy into os.environ if missing."""
        proxy = cls.get_active_proxy()
        if proxy:
            if not os.environ.get("HTTP_PROXY"):
                os.environ["HTTP_PROXY"] = proxy
            if not os.environ.get("HTTPS_PROXY"):
                os.environ["HTTPS_PROXY"] = proxy
            if not os.environ.get("ALL_PROXY"):
                os.environ["ALL_PROXY"] = proxy
        return proxy
