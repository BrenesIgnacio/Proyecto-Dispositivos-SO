"""Esto es un test para aprobar el comportamiento del driver sin hardware físico."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from driver import ButtonDriver, SimulationTransport, load_programs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config_path = Path("config/programs.json")
    programs = load_programs(config_path)

    def fake_popen(command, *args, **kwargs):
        logging.info("Simulated launch: %s", command)

    subprocess.Popen = fake_popen  # type: ignore[assignment]

    transport = SimulationTransport()
    driver = ButtonDriver(programs, transport)

    for button in range(1, 5):
        message = f"BTN|{button}|DOWN"
        logging.info("Injecting %s", message)
        driver.handle_line(message)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
