import os
import time
import speech_recognition as sr
import subprocess
import wikipediaapi
from datetime import datetime
from gtts import gTTS
import asyncio
import multiprocessing
import requests
import socket
import json
import shutil
import tinytuya

# ---------------------------------------------------------
# CONFIGURACIONES GLOBALES Y HARDWARE
# ---------------------------------------------------------
NOMBRE_DEL_SERVIDOR = "servidor"
proceso_voz = None
proceso_mpv = None
proceso_ytdl = None
mpv_socket_actual = None  # Ruta dinámica del socket activo

# Datos del bombillo Tuya QPW70-F
DEVICE_ID = "eb72862a9c80d1eaaalyes"
DEVICE_IP = "192.168.101.87"
LOCAL_KEY = "#MO8SB-rPIufZ;$I"

bulb = tinytuya.BulbDevice(DEVICE_ID, DEVICE_IP, LOCAL_KEY)
bulb.set_version(3.3)
bulb.set_socketPersistent(False)
bulb.set_socketTimeout(3)

wiki = wikipediaapi.Wikipedia(
    user_agent='AsistenteLocal/1.0 (contacto: daviddiazdh)',
    language='es',
    extract_format=wikipediaapi.ExtractFormat.WIKI
)

# ---------------------------------------------------------
# 1. MOTOR DE VOZ (PROCESO INDEPENDIENTE)
# ---------------------------------------------------------
def tarea_hablar(texto):
    """Esta función vive aislada en otro proceso para poder matarla."""
    try:
        tts = gTTS(text=texto, lang='es', tld='com.mx')
        archivo_audio = f"/tmp/respuesta_{multiprocessing.current_process().pid}.mp3"
        tts.save(archivo_audio)

        # Salida gestionada automáticamente por PipeWire
        os.system(f"mpg123 -q {archivo_audio}")
        if os.path.exists(archivo_audio):
            os.remove(archivo_audio)
    except Exception as e:
        print(f"Error en la voz: {e}")


def hablar(texto):
    """Gestor inteligente de la voz. Mata el audio anterior si existe."""
    global proceso_voz

    if proceso_voz and proceso_voz.is_alive():
        proceso_voz.terminate()
        proceso_voz.join()
        os.system("pkill -x mpg123 2>/dev/null")

    proceso_voz = multiprocessing.Process(target=tarea_hablar, args=(texto,))
    proceso_voz.start()


# ---------------------------------------------------------
# 2. CONTROL DEL BOMBILLO TUYA
# ---------------------------------------------------------
def controlar_bombillo(accion, **kwargs):
    """Envía comandos al bombillo Tuya en un hilo separado."""
    try:
        if accion == "encender":
            bulb.turn_on()
        elif accion == "apagar":
            bulb.turn_off()
        elif accion == "blanco":
            bulb.turn_on()
            bulb.set_multiple_values({
                '21': 'white',                        # Modo luz blanca
                '22': kwargs.get('brillo', 1000),     # Brillo (10 a 1000)
                '23': kwargs.get('temperatura', 300)  # Temperatura (0 cálido - 1000 frío)
            })
        elif accion == "color":
            bulb.turn_on()
            r, g, b = kwargs['rgb']
            bulb.set_colour(r, g, b)
        elif accion == "brillo":
            bulb.turn_on()
            bulb.set_multiple_values({
                '22': kwargs['valor']
            })
        return True
    except Exception as e:
        print(f"[ERROR TUYA] No se pudo comunicar con el bombillo: {e}")
        return False


# ---------------------------------------------------------
# 3. FUNCIONES DE RED / BÚSQUEDA Y CONTROL MPV
# ---------------------------------------------------------
def limpiar_socket(ruta_socket):
    """Elimina el archivo de socket si existe."""
    if ruta_socket and os.path.exists(ruta_socket):
        try:
            os.unlink(ruta_socket)
        except OSError:
            pass


def detener_reproduccion():
    """Detiene limpiamente yt-dlp, mpv y elimina el socket activo."""
    global proceso_mpv, proceso_ytdl, mpv_socket_actual

    for proc in (proceso_ytdl, proceso_mpv):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                proc.kill()

    proceso_ytdl = None
    proceso_mpv = None

    os.system("pkill -x mpv 2>/dev/null")
    os.system("pkill -x yt-dlp 2>/dev/null")

    limpiar_socket(mpv_socket_actual)
    mpv_socket_actual = None


def enviar_comando_mpv(comando):
    """Envía comandos (pausa, adelantar, etc.) al reproductor MPV activo."""
    if not mpv_socket_actual or not os.path.exists(mpv_socket_actual):
        print("No hay música reproduciéndose actualmente.")
        return False

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(mpv_socket_actual)
        mensaje = json.dumps({"command": comando}) + "\n"
        s.sendall(mensaje.encode('utf-8'))
        s.shutdown(socket.SHUT_WR)
        s.recv(1024)
        s.close()
        return True
    except Exception as e:
        print(f"No se pudo enviar el comando a MPV ({e}).")
        return False


def buscar_en_wiki(busqueda):
    pagina = wiki.page(busqueda)
    if pagina.exists():
        resumen = pagina.summary.split('\n')[0]
        return resumen
    else:
        return f"No encontré información sobre '{busqueda}'"


def obtener_ofertas_venezuela():
    url = "https://store.steampowered.com/api/featuredcategories/?l=spanish&cc=VE"
    try:
        respuesta = requests.get(url, timeout=5).json()
        ofertas = respuesta.get('specials', {}).get('items', [])
        juegos_procesados = []
        for juego in ofertas:
            juegos_procesados.append({
                'titulo': juego['name'],
                'precio_actual': juego['final_price'] / 100,
                'descuento': juego['discount_percent']
            })
        return juegos_procesados
    except Exception as e:
        print(f"Error consultando Steam: {e}")
        return []


# ---------------------------------------------------------
# 4. CEREBRO ASÍNCRONO DEL ASISTENTE
# ---------------------------------------------------------
async def procesar_comando(comando_dictado):
    global proceso_voz, proceso_mpv, proceso_ytdl, mpv_socket_actual
    print(f"\nProcesando acción para: '{comando_dictado}'")

    if "hola" in comando_dictado:
        hablar("Hola, David. El sistema está activo.")

    elif "hora" in comando_dictado:
        ahora = datetime.now()
        texto_hora = f"{ahora.hour} con {ahora.minute} minutos"
        hablar(f"La hora del servidor es {texto_hora}")

    elif "memoria" in comando_dictado or "ram" in comando_dictado:
        usada = subprocess.getoutput("free -m | awk '/^Mem:/ {print $3}'")
        total = subprocess.getoutput("free -m | awk '/^Mem:/ {print $2}'")
        hablar(f"El servidor está usando {usada} megabytes de memoria RAM, de un total de {total} megabytes.")

    elif "docker" in comando_dictado or "servicios" in comando_dictado:
        contenedores = subprocess.getoutput("sudo docker ps --format '{{.Names}}'")
        if contenedores.strip():
            lista_hablada = contenedores.replace('\n', ', ')
            hablar(f"Los contenedores activos son: {lista_hablada}")
        else:
            hablar("No tienes ningún contenedor de Docker activo.")

    elif "limpiar" in comando_dictado:
        os.system("rm -rf /tmp/respuesta_*.mp3 2>/dev/null || true")
        hablar("Los archivos temporales han sido vaciados.")

    # --- CONTROLES DEL BOMBILLO TUYA ---
    elif any(p in comando_dictado for p in ["enciende la luz", "prende la luz", "enciende el bombillo", "prende el bombillo", "enciende luz"]):
        ok = await asyncio.to_thread(controlar_bombillo, "encender")
        hablar("Luz encendida." if ok else "No pude conectar con el bombillo.")

    elif any(p in comando_dictado for p in ["apaga la luz", "apaga el bombillo", "apaga luz"]):
        ok = await asyncio.to_thread(controlar_bombillo, "apagar")
        hablar("Luz apagada." if ok else "No pude conectar con el bombillo.")

    elif any(p in comando_dictado for p in ["luz blanca", "color blanco", "modo blanco", "luz cálida"]):
        ok = await asyncio.to_thread(controlar_bombillo, "blanco", brillo=1000, temperatura=300)
        hablar("Luz blanca activada." if ok else "Error al cambiar a luz blanca.")

    elif "luz fría" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "blanco", brillo=1000, temperatura=1000)
        hablar("Luz blanca fría activada." if ok else "Error al cambiar la temperatura.")

    elif "rojo" in comando_dictado or "roja" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(255, 0, 0))
        hablar("Luz en rojo." if ok else "Error al cambiar el color.")

    elif "azul" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(0, 0, 255))
        hablar("Luz en azul." if ok else "Error al cambiar el color.")

    elif "verde" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(0, 255, 0))
        hablar("Luz en verde." if ok else "Error al cambiar el color.")

    elif "morado" in comando_dictado or "morada" in comando_dictado or "violeta" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(160, 0, 255))
        hablar("Luz en morado." if ok else "Error al cambiar el color.")

    elif "amarillo" in comando_dictado or "amarilla" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(255, 200, 0))
        hablar("Luz en amarillo." if ok else "Error al cambiar el color.")

    elif "naranja" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(255, 80, 0))
        hablar("Luz en naranja." if ok else "Error al cambiar el color.")

    elif "rosado" in comando_dictado or "rosa" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(255, 20, 147))
        hablar("Luz en rosado." if ok else "Error al cambiar el color.")

    elif "cian" in comando_dictado or "celeste" in comando_dictado:
        ok = await asyncio.to_thread(controlar_bombillo, "color", rgb=(0, 255, 255))
        hablar("Luz en celeste." if ok else "Error al cambiar el color.")

    elif "brillo" in comando_dictado:
        if "máximo" in comando_dictado or "sube" in comando_dictado or "cien" in comando_dictado:
            ok = await asyncio.to_thread(controlar_bombillo, "brillo", valor=1000)
            hablar("Brillo al máximo." if ok else "Error al ajustar el brillo.")
        elif "medio" in comando_dictado or "mitad" in comando_dictado:
            ok = await asyncio.to_thread(controlar_bombillo, "brillo", valor=500)
            hablar("Brillo al cincuenta por ciento." if ok else "Error al ajustar el brillo.")
        elif "baja" in comando_dictado or "bajo" in comando_dictado or "mínimo" in comando_dictado:
            ok = await asyncio.to_thread(controlar_bombillo, "brillo", valor=150)
            hablar("Brillo reducido." if ok else "Error al ajustar el brillo.")

    # --- CONTROLES DE MÚSICA Y MPV ---
    elif "reproduce" in comando_dictado or "pon música" in comando_dictado or "reanuda" in comando_dictado:
        cancion = ""
        if "pon música" in comando_dictado:
            partes = comando_dictado.split("pon música", 1)
            if len(partes) > 1:
                cancion = partes[1].strip()
        elif "reproduce" in comando_dictado:
            partes = comando_dictado.split("reproduce", 1)
            if len(partes) > 1:
                cancion = partes[1].strip()

        if cancion == "" or "reanuda" in comando_dictado:
            print("Reanudando música...")
            if enviar_comando_mpv(["set_property", "pause", False]):
                hablar("Reanudando")
            else:
                hablar("No hay música en pausa.")
        else:
            print(f"Buscando nueva música: {cancion}")
            hablar(f"Reproduciendo {cancion}")

            detener_reproduccion()

            if proceso_voz and proceso_voz.is_alive():
                await asyncio.to_thread(proceso_voz.join)

            mpv_socket_actual = f"/tmp/mpv_socket_{os.getpid()}_{int(time.time())}"
            ruta_ytdlp = shutil.which("yt-dlp") or "yt-dlp"

            comando_ytdl = [
                ruta_ytdlp,
                "--js-runtimes", "node",
                "-f", "bestaudio/best",
                "--no-playlist",
                "-o", "-",
                f"ytsearch1:{cancion}"
            ]

            comando_mpv = [
                "mpv",
                "--no-video",
                "--audio-device=auto",
                f"--input-ipc-server={mpv_socket_actual}",
                "-"
            ]

            log_file = open("mpv_error.log", "a", buffering=1)

            proceso_ytdl = subprocess.Popen(
                comando_ytdl,
                stdout=subprocess.PIPE,
                stderr=log_file
            )

            proceso_mpv = subprocess.Popen(
                comando_mpv,
                stdin=proceso_ytdl.stdout,
                stdout=log_file,
                stderr=subprocess.STDOUT
            )

            proceso_ytdl.stdout.close()
            log_file.close()

    elif "pausa" in comando_dictado:
        print("Pausando música...")
        enviar_comando_mpv(["set_property", "pause", True])

    elif "adelanta" in comando_dictado:
        print("Adelantando 20 segundos...")
        enviar_comando_mpv(["seek", 20])

    elif "atrasa" in comando_dictado or "retrocede" in comando_dictado:
        print("Retrocediendo 20 segundos...")
        enviar_comando_mpv(["seek", -20])

    elif "repite" in comando_dictado or "repetir" in comando_dictado:
        print("Activando bucle para la canción actual...")
        if enviar_comando_mpv(["set_property", "loop", "inf"]):
            hablar("Repetición activada.")

    # --- COMANDO DE SILENCIO TOTAL ---
    elif "detener" in comando_dictado or "silencio" in comando_dictado or "para la música" in comando_dictado:
        print("Deteniendo todos los audios...")
        detener_reproduccion()
        os.system("pkill -x mpg123 2>/dev/null")

        if proceso_voz and proceso_voz.is_alive():
            proceso_voz.terminate()
            proceso_voz.join()

        if "silencio" not in comando_dictado:
            hablar("Reproducción detenida.")

    elif "volumen" in comando_dictado:
        if "subir" in comando_dictado or "más" in comando_dictado:
            os.system("wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 10%+")
            hablar("Volumen arriba.")
        elif "bajar" in comando_dictado or "menos" in comando_dictado:
            os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ 10%-")
            hablar("Volumen abajo.")
        elif "máximo" in comando_dictado:
            os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0")
            hablar("Volumen al máximo.")

    elif "definir" in comando_dictado:
        busqueda = comando_dictado.replace("definir", "").strip()
        texto_respuesta = await asyncio.to_thread(buscar_en_wiki, busqueda)
        hablar(texto_respuesta)

    elif "ofertas" in comando_dictado or "steam" in comando_dictado:
        lista_juegos = await asyncio.to_thread(obtener_ofertas_venezuela)
        if lista_juegos:
            texto = "Estas son las tres ofertas principales:\n"
            for juego in lista_juegos[:3]:
                texto += f"{juego['titulo']}, con un {juego['descuento']} por ciento de descuento, a {juego['precio_actual']} dólares.\n"
            hablar(texto)
        else:
            hablar("No pude conectar con los servidores de Steam.")

    else:
        print("Comando no reconocido.")
        hablar("Disculpa, no tengo ese comando.")


# ---------------------------------------------------------
# 5. BUCLE DE ESCUCHA INFINITO
# ---------------------------------------------------------
def escuchar_microfono(r, source):
    try:
        return r.listen(source, timeout=None, phrase_time_limit=5)
    except sr.WaitTimeoutError:
        return None


def decodificar_audio(r, audio):
    try:
        return r.recognize_google(audio, language="es-VE").lower()
    except Exception:
        return ""


async def bucle_asistente_async():
    r = sr.Recognizer()
    r.energy_threshold = 150
    r.dynamic_energy_threshold = True

    micros_disponibles = sr.Microphone.list_microphone_names()
    indice_usb = None

    for i, nombre in enumerate(micros_disponibles):
        if "lifecam" in nombre.lower() or "vx-2000" in nombre.lower():
            indice_usb = i
            break

    if indice_usb is None:
        indice_usb = 8

    mic = sr.Microphone(device_index=indice_usb)

    with mic as source:
        print("\nCalibrando estática de fondo por 2 segundos...")
        await asyncio.to_thread(r.adjust_for_ambient_noise, source, duration=2)
        r.dynamic_energy_threshold = True

        hablar("El sistema de audio y la iluminación están cien por ciento operativos.")
        print("Esperando comandos...")

        while True:
            try:
                audio = await asyncio.to_thread(escuchar_microfono, r, source)
                if not audio:
                    continue

                texto = await asyncio.to_thread(decodificar_audio, r, audio)
                if not texto:
                    continue

                if NOMBRE_DEL_SERVIDOR in texto:
                    print(f"¡Te escuché!: \"{texto}\"")
                    comando = texto.replace(NOMBRE_DEL_SERVIDOR, "", 1).strip()

                    if comando:
                        asyncio.create_task(procesar_comando(comando))
                    else:
                        hablar("¿Sí?, dime.")

            except sr.RequestError:
                await asyncio.sleep(5)
            except KeyboardInterrupt:
                break
            except Exception:
                await asyncio.sleep(1)


# ---------------------------------------------------------
# ARRANQUE DEL SISTEMA
# ---------------------------------------------------------
if __name__ == "__main__":
    os.system("rm -f /tmp/respuesta_*.mp3 2>/dev/null")
    os.system("pkill -x mpv 2>/dev/null")
    os.system("pkill -x mpg123 2>/dev/null")

    try:
        asyncio.run(bucle_asistente_async())
    except KeyboardInterrupt:
        detener_reproduccion()
        os.system("pkill -x mpg123 2>/dev/null")