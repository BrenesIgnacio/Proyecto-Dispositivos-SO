#!/usr/bin/env python3
"""Desktop driver for the Arduino launcher panel."""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Union

try:  # pragma: no cover - lazily enforced elsewhere
    import serial
    from serial import Serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None  # type: ignore[assignment]
    Serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]

ProgramEntry = Union[str, Sequence[str], Dict[str, Union[str, Sequence[str]]]]


class TransportBase:
    """Abstract transport for sending/receiving text lines."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send_line(self, line: str) -> None:
        raise NotImplementedError

    def read_line(self) -> Optional[str]:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - optional cleanup
        pass


class SerialTransport(TransportBase):
    def __init__(self, port: str, baud: int) -> None:
        super().__init__()
        if serial is None or Serial is None:
            raise SystemExit(
                "pyserial is required for hardware mode. Install it with 'pip install -r Driver/requirements.txt'."
            )
        self.port_name = port
        self.baud = baud
        self.serial: Optional[Serial] = None
        self._connect_with_retry()

    def _connect_with_retry(self) -> None:
        backoff = 1.5
        while self.serial is None:
            try:
                logging.info("Opening serial port %s @ %d bps", self.port_name, self.baud)
                self.serial = serial.Serial(self.port_name, self.baud, timeout=0.2)
                time.sleep(2.0)  # allow Arduino reset
                self.send_line("HELLO|PC")
                logging.info("Serial link ready.")
            except serial.SerialException as err:
                logging.warning("Failed to open %s (%s). Retrying in %.1fs", self.port_name, err, backoff)
                time.sleep(backoff)

    def _require_serial(self) -> Serial:
        if self.serial is None or not self.serial.is_open:
            self.serial = None
            self._connect_with_retry()
        return self.serial  # type: ignore[return-value]

    def send_line(self, line: str) -> None:
        payload = (line.strip() + "\n").encode("utf-8")
        with self._lock:
            try:
                self._require_serial().write(payload)
            except serial.SerialException:
                logging.warning("Serial write failed; reconnecting...")
                self.serial = None
                self._connect_with_retry()
                self._require_serial().write(payload)

    def read_line(self) -> Optional[str]:
        ser = self._require_serial()
        try:
            data = ser.readline()
        except serial.SerialException:
            logging.warning("Serial read failed; reconnecting...")
            self.serial = None
            return ""
        if not data:
            return ""
        line = data.decode("utf-8", errors="ignore").strip()
        return line

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()


class SimulationTransport(TransportBase):
    """Keyboard-driven mock transport for development without hardware."""

    def send_line(self, line: str) -> None:
        with self._lock:
            logging.info("SIM ➜ %s", line)

    def read_line(self) -> Optional[str]:
        try:
            return input("SIM BTN> ").strip()
        except EOFError:
            return None


class ButtonDriver:
    def __init__(self, programs: Dict[str, List[str]], transport: TransportBase,
                 success_flash_ms: int = 1200, error_flash_ms: int = 2000) -> None:
        self.programs = programs
        self.transport = transport
        self.success_flash_ms = success_flash_ms
        self.error_flash_ms = error_flash_ms

    def handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split('|')
        topic = parts[0].upper()
        if topic == "BTN" and len(parts) >= 3:
            button_id = parts[1]
            event = parts[2].upper()
            logging.debug("Button event %s -> %s", button_id, event)
            if event == "DOWN":
                self.launch_program(button_id)
        elif topic == "READY":
            logging.info("Arduino reports READY (%s)", '|'.join(parts[1:]))
        else:
            logging.debug("Ignoring message: %s", line)

    def launch_program(self, button_id: str) -> None:
        if button_id not in self.programs:
            logging.warning("No program mapped to button %s", button_id)
            self.flash_led(button_id, success=False)
            return
        command = self.programs[button_id]
        logging.info("Launching %s via button %s", command, button_id)
        try:
            subprocess.Popen(command)
            self.flash_led(button_id, success=True)
        except FileNotFoundError:
            logging.exception("Program for button %s not found.", button_id)
            self.flash_led(button_id, success=False)
        except Exception:
            logging.exception("Failed to launch program for button %s", button_id)
            self.flash_led(button_id, success=False)

    def send_led(self, led_id: Union[str, int], mode: str, argument: Optional[int] = None) -> None:
        led_str = str(led_id)
        command = f"LED|{led_str}|{mode}"
        if argument is not None:
            command += f"|{argument}"
        self.transport.send_line(command)

    def flash_led(self, button_id: str, success: bool) -> None:
        period = 180 if success else 80
        duration = self.success_flash_ms if success else self.error_flash_ms
        self.send_led(button_id, "BLINK", period)
        threading.Thread(
            target=self._delayed_led_off,
            args=(button_id, duration / 1000.0),
            daemon=True,
        ).start()

    def _delayed_led_off(self, button_id: str, delay: float) -> None:
        time.sleep(delay)
        self.send_led(button_id, "OFF")


def normalize_program(entry: ProgramEntry) -> List[str]:
    if isinstance(entry, str):
        return [entry]
    if isinstance(entry, Sequence):
        return [str(token) for token in entry]
    if isinstance(entry, dict):
        command = entry.get("command")
        if not command:
            raise ValueError("Missing 'command' key in program entry")
        args = entry.get("args", [])
        tokens: List[str] = [str(command)]
        if isinstance(args, Sequence):
            tokens.extend(str(arg) for arg in args)
        else:
            tokens.append(str(args))
        return tokens
    raise TypeError(f"Unsupported program entry: {entry!r}")


def load_programs(config_path: Path) -> Dict[str, List[str]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    data = json.loads(config_path.read_text())
    programs: Dict[str, List[str]] = {}
    for key, value in data.items():
        try:
            programs[str(key)] = normalize_program(value)
        except Exception as exc:
            raise ValueError(f"Invalid entry for button {key}: {exc}") from exc
    if not programs:
        raise ValueError("Configuration does not define any programs.")
    return programs


def auto_detect_port(user_port: Optional[str]) -> str:
    if user_port:
        return user_port
    if list_ports is None:
        raise RuntimeError("pyserial is required to auto-detect ports. Install it or pass --port explicitly.")
    ports = list(list_ports.comports())
    if not ports:
        raise RuntimeError("No serial ports available. Plug in the Arduino or pass --port.")
    for port in ports:
        descriptor = (port.description or "").lower()
        if any(token in descriptor for token in ("arduino", "wchusb", "ch340")):
            logging.info("Detected Arduino on %s (%s)", port.device, port.description)
            return port.device
    logging.warning("Fell back to first serial port: %s", ports[0].device)
    return ports[0].device


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PC driver for the Arduino launcher panel")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/programs.json"),
        help="Path to button-program mapping JSON",
    )
    parser.add_argument("--port", help="Serial port (else auto-detect)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run without hardware. Type BTN commands manually for testing.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        programs = load_programs(args.config)
    except Exception as exc:
        raise SystemExit(f"Failed to load config: {exc}") from exc

    transport: TransportBase
    if args.simulate:
        logging.info("Running in simulation mode. Type lines like 'BTN|1|DOWN'.")
        transport = SimulationTransport()
    else:
        try:
            port = auto_detect_port(args.port)
        except Exception as exc:
            raise SystemExit(str(exc)) from exc
        transport = SerialTransport(port, args.baud)

    driver = ButtonDriver(programs, transport)

    try:
        while True:
            line = transport.read_line()
            if line is None:
                break
            driver.handle_line(line)
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    finally:
        transport.close()


if __name__ == "__main__":
    main()
