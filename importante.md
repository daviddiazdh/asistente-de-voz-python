# Guía Técnica: Configuración de Audio y Asistente de Voz Local

Este documento resume la arquitectura del sistema de audio, las causas de los fallos encontrados durante la integración (PipeWire / WirePlumber / ALSA) y los comandos de mantenimiento y resolución de problemas.

---

## 1. Resumen Técnico del Problema y Solución

### Dispositivos de Hardware
* **Tarjeta de Audio Interna:** `HDA Intel PCH` (Realtek `ALC897` - Tarjeta ALSA `0`).
* **Salida Física (Cornetas):** Canal `Front` / Conector verde analógico (`hw:0,0`).
* **Entrada de Voz (Micrófono):** Microsoft `LifeCam VX-2000` (USB Mono).

### Diagnóstico de Fallos Iniciales
1. **Conflicto con `lightdm` (Causa Principal del *Dummy Output*):**
   La pantalla de inicio de sesión (`lightdm`) ejecutaba su propia instancia de PipeWire y WirePlumber en segundo plano durante el encendido. Esto bloqueaba la tarjeta ALSA (`hw:0,0`) bajo el error `Dispositivo o recurso ocupado`, impidiendo que el usuario principal (`david`) inicializara la salida analógica y enviando el audio a `Dummy Output`.
2. **Canal ALSA Mutado:**
   El mezclador de la placa (`ALC897`) mantenía el subcanal analógico `Front` silenciado (`[off]`) por defecto al encender el equipo.
3. **Bloqueos Directos a ALSA por Python:**
   Herramientas como `mpg123` o `sr.Microphone` abrían directamente la tarjeta ALSA en lugar de pasar por el servidor virtual de PipeWire/PulseAudio.

---

## 2. Configuraciones Clave Implementadas

### A. Bloqueo de Audio en `lightdm` (Aislamiento de Tarjeta)
Se enmascaró la pila de audio para el usuario del sistema `lightdm`, garantizando que solo el usuario `david` administre el hardware desde el encendido:

```bash
# Archivos creados como enlaces simbólicos hacia /dev/null en:
# /var/lib/lightdm/.config/systemd/user/
- pipewire.service
- pipewire.socket
- pipewire-pulse.service
- pipewire-pulse.socket
- wireplumber.service
```

### B. Servicio Systemd (`~/.config/systemd/user/asistente.service`)
El servicio espera a que PipeWire reconozca la salida analógica y el micrófono USB, desmutea `Front` y `Master` en ALSA, ajusta el volumen al 100% y ejecuta el asistente:

```ini
[Unit]
Description=Asistente de Voz Local (Audio, Musica y Tuya)
After=pipewire.service pipewire-pulse.service wireplumber.service sound.target
Wants=pipewire.service pipewire-pulse.service wireplumber.service
PartOf=wireplumber.service

[Service]
Type=simple
WorkingDirectory=/home/david/asistente-de-voz-python
Environment="PYTHONUNBUFFERED=1"
Environment="XDG_RUNTIME_DIR=%t"
Environment="PULSE_SERVER=unix:%t/pulse/native"
Environment="PATH=/home/david/asistente-de-voz-python/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/bin/sh -c 'for i in $(seq 1 20); do wpctl status | awk "/Sinks:/,/Sink endpoints:/" | grep -q "Built-in Audio" && wpctl status | awk "/Sources:/,/Source endpoints:/" | grep -q "LifeCam" && break; sleep 1; done; MIC_ID=$(wpctl status | awk "/Sources:/,/Source endpoints:/" | grep "LifeCam" | sed -n "s/^[^0-9]*\\([0-9]\\+\\)\\..*/\\1/p" | head -n 1); [ -n "$MIC_ID" ] && wpctl set-default "$MIC_ID"; amixer -c 0 sset "Auto-Mute Mode" Disabled 2>/dev/null; amixer -c 0 sset Front 100% unmute; amixer -c 0 sset Master 100% unmute; wpctl set-mute @DEFAULT_AUDIO_SINK@ 0; wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0'
ExecStart=/home/david/asistente-de-voz-python/venv/bin/python /home/david/asistente-de-voz-python/asistente_async.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

### C. Ajustes en `asistente_async.py`
1. **Motor de Voz sin Bloqueo ALSA:**
   `os.system(f"mpg123 -o pulse -q {archivo_audio}")` obliga a `mpg123` a enviar la voz mediante PulseAudio/PipeWire.
2. **Priorización de Servidor Virtual en Micrófono:**
   En `bucle_asistente_async()`, el código busca primero el dispositivo `pipewire`, `pulse` o `default` para tomar el micrófono fijado globalmente por PipeWire sin acaparar el dispositivo de hardware exclusivo.

---

## 3. Comandos Útiles de Mantenimiento y Diagnóstico

### Verificación Rápida del Sistema de Audio
```bash
# Ver estado general de nodos de salida (Sinks) y entrada (Sources)
wpctl status

# Consultar volumen actual de la salida predeterminada
wpctl get-volume @DEFAULT_AUDIO_SINK@

# Ajustar volumen al 100%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0

# Verificar niveles del mezclador físico ALSA
amixer -c 0 sget Front; amixer -c 0 sget Master
```

### Gestión del Servicio del Asistente
```bash
# Ver estado actual y últimos logs en tiempo real
systemctl --user status asistente.service --no-pager -n 20

# Ver logs continuos del asistente
journalctl --user -u asistente.service -f

# Reiniciar el servicio manualmente
systemctl --user restart asistente.service
```

### Probar Sonido Directo por PipeWire (Sin bloquear terminales)
```bash
# Reproducir archivo de prueba nativo por PipeWire
pw-play /usr/share/sounds/alsa/Front_Center.wav
```

---

## 4. Guía de Solución de Problemas (Troubleshooting)

### Caso 1: El asistente responde en logs pero no se escucha nada
1. **Verificar si ALSA silenció el canal analógico `Front`:**
   ```bash
   amixer -c 0 sset Front 100% unmute
   amixer -c 0 sset Master 100% unmute
   ```
2. **Verificar que el volumen en PipeWire no esté mudo:**
   ```bash
   wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
   wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0
   ```

### Caso 2: El sistema cae a `Dummy Output` tras una actualización
1. **Verificar qué proceso tiene bloqueado `/dev/snd/`:**
   ```bash
   sudo fuser -v /dev/snd/*
   ```
2. **Reiniciar la pila de audio del usuario:**
   ```bash
   systemctl --user restart pipewire pipewire-pulse wireplumber
   ```

### Caso 3: Proceso de prueba de audio bloqueado en la terminal (`speaker-test` / `pw-play`)
Si una terminal se congela al ejecutar pruebas de sonido:
1. Abrir otra ventana o pestaña de terminal (`Ctrl + Shift + T`).
2. Eliminar el proceso atascado a la fuerza:
   ```bash
   pkill -9 -x speaker-test; pkill -9 -x pw-play
   ```

### Caso 4: Revertir el bloqueo de audio en `lightdm` (Instrucción Futura)
Si en el futuro deseas devolverle los sonidos a la pantalla de login:
```bash
LIGHTDM_HOME=$(getent passwd lightdm | cut -d: -f6)
sudo rm -rf "$LIGHTDM_HOME/.config/systemd/user"
sudo reboot
```