"""test_camera.py — tests unitaires de core.camera sans matériel réel."""
from __future__ import annotations

import subprocess
import time

from core import camera
from core.camera import CameraManager


class FakeViewfinder:
    def __init__(self):
        self.value = None

    def set_value(self, value):
        self.value = value


class FakeConfig:
    def __init__(self):
        self.viewfinder = FakeViewfinder()

    def get_child_by_name(self, name):
        assert name == "viewfinder"
        return self.viewfinder


class FakeCamera:
    def __init__(self):
        self.config = FakeConfig()
        self.inited = False
        self.exited = False

    def init(self):
        self.inited = True

    def get_config(self):
        return self.config

    def set_config(self, cfg):
        self.config = cfg

    def exit(self):
        self.exited = True


class FakeGp:
    class GPhoto2Error(Exception):
        pass

    Camera = FakeCamera


def _no_subprocess(*args, **kwargs):
    return subprocess.CompletedProcess(args[0], 0)


def test_import_degrade_si_dependance_gphoto2_absente(monkeypatch):
    monkeypatch.setattr(camera, "gp", None)
    mgr = CameraManager()

    assert mgr.init() is False
    assert mgr.is_connected is False


def test_preview_retourne_none_si_dependance_image_absente(monkeypatch):
    monkeypatch.setattr(camera, "cv2", None)
    mgr = CameraManager()

    assert mgr.get_preview_frame() is None


def test_init_connecte_camera_et_liveview(monkeypatch):
    monkeypatch.setattr(camera, "gp", FakeGp)
    monkeypatch.setattr(camera.subprocess, "run", _no_subprocess)
    mgr = CameraManager()

    assert mgr.init() is True
    assert mgr.is_connected is True

    mgr.set_liveview(1)
    assert mgr.raw_camera.config.viewfinder.value == 1


def test_init_echec_reste_deconnecte(monkeypatch):
    class BrokenGp:
        class Camera:
            def init(self):
                raise RuntimeError("no camera")

    monkeypatch.setattr(camera, "gp", BrokenGp)
    monkeypatch.setattr(camera.subprocess, "run", _no_subprocess)
    mgr = CameraManager()

    assert mgr.init() is False
    assert mgr.is_connected is False


def test_get_preview_frame_ne_bloque_pas_sur_camera_lente(monkeypatch):
    class CameraLente(FakeCamera):
        def capture_preview(self):
            time.sleep(0.2)

    class GpLent(FakeGp):
        Camera = CameraLente

    monkeypatch.setattr(camera, "gp", GpLent)
    monkeypatch.setattr(camera, "cv2", object())
    monkeypatch.setattr(camera, "np", object())
    monkeypatch.setattr(camera, "pygame", object())
    monkeypatch.setattr(camera.subprocess, "run", _no_subprocess)
    mgr = CameraManager()
    mgr.init()
    mgr.start_preview()

    debut = time.monotonic()
    assert mgr.get_preview_frame() is None
    assert time.monotonic() - debut < 0.05

    mgr.close()


def test_get_preview_frame_convertit_surface(monkeypatch):
    class PreviewCapture:
        def get_data_and_size(self):
            return b"jpeg"

    class PreviewCamera(FakeCamera):
        def capture_preview(self):
            return PreviewCapture()

    class PreviewGp(FakeGp):
        Camera = PreviewCamera

    class FakeNp:
        uint8 = "uint8"

        @staticmethod
        def frombuffer(data, dtype):
            assert dtype == "uint8"
            return ("array", bytes(data))

        @staticmethod
        def transpose(frame, axes):
            assert axes == (1, 0, 2)
            return ("transpose", frame)

    class FakeCv2:
        IMREAD_COLOR = 1
        COLOR_BGR2RGB = 2

        @staticmethod
        def imdecode(data, mode):
            assert mode == 1
            return ("decoded", data)

        @staticmethod
        def cvtColor(frame, mode):
            assert mode == 2
            return ("rgb", frame)

        @staticmethod
        def flip(frame, flip_code):
            assert flip_code == 1
            return ("flip", frame)

    class FakeSurfarray:
        appels = 0

        @staticmethod
        def make_surface(frame):
            FakeSurfarray.appels += 1
            return ("surface", frame)

    class FakePygame:
        surfarray = FakeSurfarray

    monkeypatch.setattr(camera, "gp", PreviewGp)
    monkeypatch.setattr(camera, "np", FakeNp)
    monkeypatch.setattr(camera, "cv2", FakeCv2)
    monkeypatch.setattr(camera, "pygame", FakePygame)
    monkeypatch.setattr(camera.subprocess, "run", _no_subprocess)
    mgr = CameraManager()
    assert mgr.init() is True
    mgr.start_preview()

    deadline = time.monotonic() + 1.0
    surf = None
    while surf is None and time.monotonic() < deadline:
        surf = mgr.get_preview_frame()
        time.sleep(0.001)

    assert surf[0] == "surface"
    assert mgr.preview_generation > 0

    surface_info, generation_info = mgr.get_preview_frame_info()
    assert surface_info is not None
    assert generation_info <= mgr.preview_generation

    mgr.stop_preview()
    monkeypatch.setattr(mgr, "start_preview", lambda: None)
    surf_cachee = mgr.get_preview_frame()
    nb_conversions = FakeSurfarray.appels

    assert mgr.get_preview_frame() is surf_cachee
    assert FakeSurfarray.appels == nb_conversions
    mgr.close()


def test_capture_hq_succes_cree_fichier_et_relance_liveview(monkeypatch, tmp_path):
    destination = tmp_path / "photo.jpg"
    appels = []

    def fake_run(cmd, **kwargs):
        appels.append(cmd)
        if cmd and cmd[0] == "gphoto2":
            destination.write_bytes(b"jpg")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(camera, "gp", FakeGp)
    monkeypatch.setattr(camera.subprocess, "run", fake_run)
    monkeypatch.setattr(camera.time, "sleep", lambda _: None)
    mgr = CameraManager()
    mgr.init()

    assert mgr.capture_hq(str(destination)) is True
    assert any(cmd and cmd[0] == "gphoto2" for cmd in appels)
    assert mgr.is_connected is True


def test_capture_hq_echec_apres_retries(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "gphoto2":
            raise subprocess.TimeoutExpired(cmd, timeout=15)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(camera, "gp", None)
    monkeypatch.setattr(camera.subprocess, "run", fake_run)
    monkeypatch.setattr(camera.time, "sleep", lambda _: None)
    mgr = CameraManager()

    assert mgr.capture_hq(str(tmp_path / "absente.jpg")) is False


def test_close_ferme_camera(monkeypatch):
    monkeypatch.setattr(camera, "gp", FakeGp)
    monkeypatch.setattr(camera.subprocess, "run", _no_subprocess)
    mgr = CameraManager()
    mgr.init()
    raw = mgr.raw_camera

    mgr.close()

    assert raw.exited is True
    assert mgr.raw_camera is None
