"""test_arduino.py — tests unitaires du contrôleur Arduino.

Mocke `pyserial` avec une FakeSerial qui enregistre les octets écrits et
alimente les lectures depuis une queue. Permet de couvrir la logique sans
hardware. `pygame` est aussi mocké pour tester l'injection de KEYDOWN.

Usage : pytest test_arduino.py -v
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from core import arduino
from core.arduino import (
    LED_OFF, LED_ON, LED_PULSE, LED_PULSE_FAST,
    POS_DROITE, POS_GAUCHE, POS_MILIEU,
    ArduinoController,
)


# --- Fakes ---


class FakeSerial:
    """Faux port série : enregistre les écritures, simule les lectures depuis une queue."""

    def __init__(self, port, baudrate, timeout=0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.written: list[bytes] = []
        self._read_queue: list[bytes] = []
        self.closed = False
        self.reset_called = False

    def write(self, data):
        self.written.append(bytes(data))
        return len(data)

    def read(self, n):
        if self._read_queue:
            return self._read_queue.pop(0)
        return b""

    def reset_input_buffer(self):
        self.reset_called = True

    def close(self):
        self.closed = True

    def feed(self, data: bytes):
        """Inject data to be read by the next read() call."""
        self._read_queue.append(data)


class FakeSerialModule:
    """Simule le module `serial` (pyserial)."""

    def __init__(self):
        self.last_instance: FakeSerial | None = None

    def Serial(self, port, baudrate, timeout=0.1):
        inst = FakeSerial(port, baudrate, timeout)
        self.last_instance = inst
        return inst


class FakePygameEvent:
    """Simule pygame.event pour capturer les posts."""

    KEYDOWN = 768  # valeur arbitraire stable

    def __init__(self):
        self.posted: list = []

    def Event(self, type_, attrs):
        return SimpleNamespace(type=type_, **attrs)

    def post(self, evt):
        self.posted.append(evt)


# --- Fixtures ---


@pytest.fixture
def fake_serial(monkeypatch):
    mod = FakeSerialModule()
    monkeypatch.setattr(arduino, "serial", mod)
    # Réduit le sleep post-connexion pour que les tests ne traînent pas.
    return mod


@pytest.fixture
def fake_pygame(monkeypatch):
    fake = SimpleNamespace(
        KEYDOWN=FakePygameEvent.KEYDOWN,
        event=FakePygameEvent(),
    )
    monkeypatch.setattr(arduino, "pygame", fake)
    return fake


@pytest.fixture
def ctrl(fake_serial, fake_pygame):
    """Controller déjà démarré, avec FakeSerial branchée."""
    c = ArduinoController(
        port="/dev/fake",
        baudrate=115200,
        key_left=ord("g"),
        key_mid=ord("m"),
        key_right=ord("d"),
        connect_timeout_s=0.0,
    )
    c.start()
    yield c
    c.close()


# --- Init / lifecycle ---


class TestStart:
    def test_sans_pyserial_inerte(self, monkeypatch):
        monkeypatch.setattr(arduino, "serial", None)
        c = ArduinoController(port="/dev/x", connect_timeout_s=0.0)
        c.start()
        assert c.available is False

    def test_sans_port_inerte(self, fake_serial):
        c = ArduinoController(port=None, connect_timeout_s=0.0)
        c.start()
        assert c.available is False

    def test_ouverture_echouee_fallback(self, monkeypatch):
        class FailingModule:
            def Serial(self, *a, **kw):
                raise OSError("port busy")
        monkeypatch.setattr(arduino, "serial", FailingModule())
        c = ArduinoController(port="/dev/x", connect_timeout_s=0.0)
        c.start()
        assert c.available is False

    def test_start_reussi_marque_available(self, fake_serial, fake_pygame):
        c = ArduinoController(port="/dev/fake", connect_timeout_s=0.0)
        c.start()
        assert c.available is True
        assert fake_serial.last_instance is not None
        assert fake_serial.last_instance.reset_called is True
        c.close()

    def test_close_idempotent(self, ctrl):
        ctrl.close()
        ctrl.close()  # ne doit pas crasher
        assert ctrl.available is False


# --- LEDs ---


def _last_written_ascii(serial_inst: FakeSerial) -> list[str]:
    return [b.decode("ascii").strip() for b in serial_inst.written]


class TestLed:
    def test_set_led_envoie_commande(self, ctrl, fake_serial):
        fake_serial.last_instance.written.clear()
        ctrl.set_led(POS_GAUCHE, LED_ON)
        assert "LED:L:ON" in _last_written_ascii(fake_serial.last_instance)

    def test_set_led_debounce_transitions(self, ctrl, fake_serial):
        ctrl.set_led(POS_MILIEU, LED_PULSE)
        fake_serial.last_instance.written.clear()
        ctrl.set_led(POS_MILIEU, LED_PULSE)  # même état → skip
        assert fake_serial.last_instance.written == []

    def test_set_led_emet_sur_changement(self, ctrl, fake_serial):
        ctrl.set_led(POS_DROITE, LED_ON)
        fake_serial.last_instance.written.clear()
        ctrl.set_led(POS_DROITE, LED_PULSE_FAST)
        assert "LED:R:FAST" in _last_written_ascii(fake_serial.last_instance)

    def test_all_leds_off(self, ctrl, fake_serial):
        fake_serial.last_instance.written.clear()
        ctrl.all_leds_off()
        assert "LED:ALL:OFF" in _last_written_ascii(fake_serial.last_instance)


# --- Tick (machine d'état) ---


class TestTick:
    def test_accueil_sans_mode(self, ctrl):
        ctrl.tick("ACCUEIL", mode_actuel=None)
        assert ctrl._last_led_state == {POS_GAUCHE: LED_PULSE, POS_MILIEU: LED_OFF, POS_DROITE: LED_PULSE}

    def test_accueil_avec_mode(self, ctrl):
        ctrl.tick("ACCUEIL", mode_actuel="10x15")
        assert ctrl._last_led_state[POS_MILIEU] == LED_PULSE
        assert ctrl._last_led_state[POS_GAUCHE] == LED_ON
        assert ctrl._last_led_state[POS_DROITE] == LED_ON

    def test_decompte_toutes_off(self, ctrl):
        ctrl.tick("ACCUEIL", mode_actuel=None)
        ctrl.tick("DECOMPTE", mode_actuel="10x15")
        assert all(v == LED_OFF for v in ctrl._last_led_state.values())

    def test_validation(self, ctrl):
        ctrl.tick("VALIDATION", mode_actuel="strips")
        assert ctrl._last_led_state[POS_MILIEU] == LED_PULSE

    def test_fin_abandon_armed_seul_rouge_clignote(self, ctrl):
        ctrl.tick("FIN", mode_actuel="10x15", abandon_armed=True)
        assert ctrl._last_led_state[POS_DROITE] == LED_PULSE_FAST
        assert ctrl._last_led_state[POS_GAUCHE] == LED_OFF
        assert ctrl._last_led_state[POS_MILIEU] == LED_OFF

    def test_meme_signature_pas_de_reemission(self, ctrl, fake_serial):
        ctrl.tick("VALIDATION", mode_actuel="10x15")
        fake_serial.last_instance.written.clear()
        ctrl.tick("VALIDATION", mode_actuel="10x15")
        assert fake_serial.last_instance.written == []


# --- Lecture / injection pygame ---


class TestReadLoop:
    def test_ligne_L_injecte_touche_gauche(self, ctrl, fake_serial, fake_pygame):
        fake_serial.last_instance.feed(b"L\n")
        # Laisse le thread consommer
        for _ in range(50):
            if fake_pygame.event.posted:
                break
            time.sleep(0.01)
        assert any(evt.key == ord("g") for evt in fake_pygame.event.posted)

    def test_ligne_READY_ne_crashe_pas(self, ctrl, fake_serial):
        fake_serial.last_instance.feed(b"READY\n")
        time.sleep(0.05)  # laisse le thread tourner
        assert ctrl.available is True

    def test_ligne_LOG_ne_crashe_pas(self, ctrl, fake_serial):
        fake_serial.last_instance.feed(b"LOG:debug message\n")
        time.sleep(0.05)
        assert ctrl.available is True

    def test_handle_line_sans_pygame_no_crash(self, fake_serial, monkeypatch):
        """Si pygame absent, l'injection est no-op silencieuse."""
        monkeypatch.setattr(arduino, "pygame", None)
        c = ArduinoController(port="/dev/fake", key_left=1, connect_timeout_s=0.0)
        c.start()
        c._handle_line("L")  # ne doit pas crasher
        c.close()
