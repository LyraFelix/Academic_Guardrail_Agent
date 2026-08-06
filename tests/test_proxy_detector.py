"""Unit tests for SystemProxyDetector."""

import os
from unittest.mock import patch
from academic_guardrail.core.proxy_detector import SystemProxyDetector


def test_system_proxy_detector_env():
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:7890"}):
        proxy = SystemProxyDetector.get_active_proxy()
        assert proxy == "http://127.0.0.1:7890"


def test_auto_inject_proxy():
    with patch.object(SystemProxyDetector, "get_active_proxy", return_value="http://127.0.0.1:10809"):
        with patch.dict(os.environ, {}, clear=True):
            injected = SystemProxyDetector.auto_inject_system_proxy()
            assert injected == "http://127.0.0.1:10809"
            assert os.environ.get("HTTP_PROXY") == "http://127.0.0.1:10809"
            assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:10809"
