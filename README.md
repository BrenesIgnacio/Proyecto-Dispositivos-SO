## Panel de Lanzamiento Arduino

Este proyecto conecta un Arduino Uno (cuatro botones + cuatro LEDs) con un driver Python en segundo plano, de modo que cada botón puede lanzar un programa de escritorio personalizado. La comunicación viaja por el puerto COM virtual USB usando comandos de texto cortos.

### Protocolo serie (texto, terminado en nueva línea)

Todos los comandos son cadenas ASCII terminadas por `\n`. Los segmentos se separan con el carácter pipe (`|`). Los comandos desconocidos se ignoran.

#### Arduino ➜ PC (eventos de botón)

```
BTN|<button_id>|<event>
```

- `button_id`: 1–4 (de izquierda a derecha).
- `event`: `DOWN` cuando el botón pasa de liberado a presionado, `UP` cuando se libera, `HOLD` se envía periódicamente mientras el botón permanece presionado (reservado para uso futuro).

Ejemplo: `BTN|2|DOWN` significa que se presionó el botón #2. El driver Python reacciona al evento `DOWN` lanzando el programa asignado a ese botón.

#### PC ➜ Arduino (feedback de LED)

```
LED|<led_id>|<mode>[|<argument>]
```

- `led_id`: 1–4 (mismo orden que los botones).
- `mode`: uno de `ON`, `OFF` o `BLINK`.
- `argument` (solo para `BLINK`): periodo de parpadeo en milisegundos. Por defecto es 500 ms si se omite.

Ejemplos:

- `LED|3|ON` — enciende el LED #3 de forma continua.
- `LED|1|OFF` — apaga el LED #1.
- `LED|4|BLINK|250` — parpadea el LED #4 cada 250 ms.

El firmware de Arduino mantiene el temporizado de parpadeo con `millis()`, así el enlace serie queda libre para nuevos mensajes.

### Estructura del repositorio

```
Firmware/   # Sketch de Arduino que implementa el protocolo
Driver/     # Driver Python que lanza programas y se comunica con el Arduino
config/     # JSON editable por el usuario que describe qué programa lanza cada botón
```

Las instrucciones detalladas de instalación, compilación y uso están más abajo en este README (se completarán una vez finalizado el código).

## Pasos del funcionamiento

### 1. Grabar el firmware en el Arduino

1. Abrir `Firmware/LauncherPanel.ino` en el IDE de Arduino.
2. Selecciona **Arduino Uno** y el puerto serie correcto.
3. Hacer clic en **Upload**. Al reiniciar, la placa imprime `READY|ARDUINO` por USB para que el driver Python sepa que está lista.

### 2. Instala el driver Python

En un entorno virtual (VM):

```bash
cd /ruta/a/Proyecto\ Dispositivos
python3 -m venv .venv
source .venv/bin/activate
pip install -r Driver/requirements.txt
```

En un entorno real:

- Linux (Debian/Ubuntu)
    - Instalar Python y pip si hace falta:
        ```bash
        sudo apt update
        sudo apt install -y python3 python3-pip
        ```
    - Instalar para el usuario (recomendado, evita usar sudo pip):
        ```bash
        python3 -m pip install --user -r Driver/requirements.txt
        ```
        Asegúrate de que ~/.local/bin esté en tu PATH.
    - Si prefieres instalar globalmente (administrador):
        ```bash
        sudo python3 -m pip install -r Driver/requirements.txt
        ```

- macOS
    - Con Homebrew:
        ```bash
        brew install python
        python3 -m pip install --user -r Driver/requirements.txt
        ```
    - O, para instalación global:
        ```bash
        sudo python3 -m pip install -r Driver/requirements.txt
        ```

- Windows
    - Abrir PowerShell o CMD (como administrador para instalación global) y ejecutar:
        ```powershell
        py -3 -m pip install -r Driver/requirements.txt
        ```
    - Para instalación por usuario (sin permisos de admin):
        ```powershell
        py -3 -m pip install --user -r Driver/requirements.txt
        ```
        Si usas --user, añade %APPDATA%\Python\PythonXX\Scripts (o la ruta que corresponda) al PATH.

Notas:
- La instalación global (sudo / administrador) modifica el Python del sistema y puede interferir con paquetes del sistema: se recomienda usar --user si no necesita acceso para todos los usuarios.
- Tras la instalación, ejecuta el driver igual que antes:
    ```bash
    python Driver/driver.py --log-level INFO
    ```
- Si se instaló con --user, usa el mismo intérprete `python`/`python3` que usaste para instalar los paquetes.  

### 3. Asigna programas a los botones

Editar `config/programs.json`. Cada entrada puede ser:

- Una cadena con la ruta del ejecutable (Windows o Linux).
- Un array JSON con el ejecutable seguido de los argumentos.
- Un objeto `{ "command": "ruta", "args": ["--flag", "valor"] }`.

Ejemplo (`config/programs.json`):

```json
{
	"1": "C:/Program Files/Mozilla Firefox/firefox.exe",
	"2": "notepad.exe",
	"3": "C:/Windows/System32/calc.exe",
	"4": ["/usr/bin/firefox", "https://www.arduino.cc"]
}
```

Los números de botón son 1–4 de izquierda a derecha. Deja cualquier botón sin asignar eliminando su entrada.

## Ejecutar el driver

```bash
python Driver/driver.py --log-level INFO
```

Comportamiento:

- El driver detecta automáticamente el puerto serie del Arduino (puedes forzar con `--port /dev/ttyACM0`).
- Al presionar un botón, Arduino envía `BTN|n|DOWN`. El driver lanza el programa configurado usando `subprocess.Popen`.
- El driver envía inmediatamente `LED|n|BLINK|180` en caso de éxito o `LED|n|BLINK|80` en caso de error, y luego apaga el LED automáticamente.

### Modo simulación (sin hardware)

```bash
python Driver/driver.py --simulate --log-level DEBUG
```

Escribe mensajes de prueba (por ejemplo, `BTN|1|DOWN`) y observa cómo el driver lanza aplicaciones mientras los comandos LED se imprimen en la consola.

## Mapa del repositorio

```
Circuito.png       # diagrama de conexiones (render Tinkercad)
Firmware/          # Sketch de Arduino
Driver/driver.py   # Servicio Python en segundo plano
Driver/requirements.txt
config/programs.json
```
