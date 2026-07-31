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

# Configuraciones Globales
NOMBRE_DEL_SERVIDOR = "servidor"
proceso_voz = None
MPV_SOCKET = "/tmp/mpv_socket"  # Canal de comunicación para controlar la música

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
        
        os.system(f"mpg123 -q -a plug:dmix {archivo_audio}")
        os.remove(archivo_audio)
    except Exception as e:
        print(f"Error en la voz: {e}")

def hablar(texto):
    """Gestor inteligente de la voz. Mata el audio anterior si existe."""
    global proceso_voz
    
    if proceso_voz and proceso_voz.is_alive():
        proceso_voz.terminate()
        proceso_voz.join()
        os.system("pkill mpg123 2>/dev/null") 
        
    proceso_voz = multiprocessing.Process(target=tarea_hablar, args=(texto,))
    proceso_voz.start()

# ---------------------------------------------------------
# 2. FUNCIONES DE RED / BÚSQUEDA Y CONTROL MPV
# ---------------------------------------------------------
def enviar_comando_mpv(comando):
    """Envía comandos (pausa, adelantar, etc) al reproductor MPV activo."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(MPV_SOCKET)
        mensaje = json.dumps({"command": comando}) + "\n"
        s.sendall(mensaje.encode('utf-8'))
        s.close()
    except Exception as e:
        print("No se pudo enviar el comando. ¿Hay música reproduciéndose?")


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
# 3. CEREBRO ASÍNCRONO DEL ASISTENTE
# ---------------------------------------------------------
async def procesar_comando(comando_dictado):
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
        os.system("rm -rf /tmp/* 2>/dev/null || true")
        hablar("Los archivos temporales han sido vaciados.")

    # --- CONTROLES DE MÚSICA Y MPV ---
    
    elif "reproduce" in comando_dictado or "pon música" in comando_dictado or "reanuda" in comando_dictado:
        cancion = ""
        if "pon música" in comando_dictado:
            partes = comando_dictado.split("pon música")
            if len(partes) > 1: cancion = partes[1].strip()
        elif "reproduce" in comando_dictado:
            partes = comando_dictado.split("reproduce")
            if len(partes) > 1: cancion = partes[1].strip()

        # Si el usuario solo dice "reanuda" o "reproduce" sin decir una canción, quitamos la pausa
        if cancion == "" or "reanuda" in comando_dictado:
            print("Reanudando música...")
            enviar_comando_mpv(["set_property", "pause", False])
            hablar("Reanudando")
        else:
            print(f"Buscando nueva música: {cancion}")
            hablar(f"Reproduciendo {cancion}")
            os.system("pkill mpv 2>/dev/null")
            os.system(f"rm -f {MPV_SOCKET} 2>/dev/null") # Limpiar socket viejo
            
            # Lanzamos MPV habilitando el socket de comunicación
            comando = [
                "mpv", "--no-video", "--audio-device=alsa/plug:dmix", 
                f"--input-ipc-server={MPV_SOCKET}", 
                f"ytdl://ytsearch:{cancion}"
            ]
            subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif "pausa" in comando_dictado:
        print("Pausando música...")
        enviar_comando_mpv(["set_property", "pause", True])
        # No decimos "Música en pausa" en audio porque taparía la acción de pausar,
        # pero puedes descomentar la siguiente línea si quieres que lo diga:
        # hablar("En pausa")

    elif "adelanta" in comando_dictado:
        print("Adelantando 20 segundos...")
        enviar_comando_mpv(["seek", 20])
        # hablar("Adelantando")

    elif "atrasa" in comando_dictado or "retrocede" in comando_dictado:
        print("Retrocediendo 20 segundos...")
        enviar_comando_mpv(["seek", -20])

    elif "repite" in comando_dictado or "repetir" in comando_dictado:
        print("Activando bucle para la canción actual...")
        enviar_comando_mpv(["set_property", "loop", "inf"])
        hablar("Repetición activada.")

    # --- COMANDO DE SILENCIO TOTAL ---
    elif "detener" in comando_dictado or "silencio" in comando_dictado or "para la música" in comando_dictado:
        print("Deteniendo todos los audios...")
        os.system("pkill mpv 2>/dev/null")
        os.system("pkill mpg123 2>/dev/null")
        
        global proceso_voz
        if proceso_voz and proceso_voz.is_alive():
            proceso_voz.terminate()
            proceso_voz.join()
        
        if "silencio" not in comando_dictado:
            hablar("Reproducción detenida.")

    elif "volumen" in comando_dictado:
        if "subir" in comando_dictado or "más" in comando_dictado:
            os.system("amixer -c 0 sset Master 15%+")
            hablar("Volumen arriba.")
        elif "bajar" in comando_dictado or "menos" in comando_dictado:
            os.system("amixer -c 0 sset Master 15%-")
            hablar("Volumen abajo.")
        elif "máximo" in comando_dictado:
            os.system("amixer -c 0 sset Master 100%")
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
# 4. BUCLE DE ESCUCHA INFINITO
# ---------------------------------------------------------
def escuchar_microfono(r, source):
    try:
        return r.listen(source, timeout=None, phrase_time_limit=5)
    except sr.WaitTimeoutError:
        return None

def decodificar_audio(r, audio):
    try:
        return r.recognize_google(audio, language="es-VE").lower()
    except:
        return ""

async def bucle_asistente_async():
    r = sr.Recognizer()
    r.energy_threshold = 150
    r.dynamic_energy_threshold = True

    micros_disponibles = sr.Microphone.list_microphone_names()
    indice_usb = None
    
    for i, nombre in enumerate(micros_disponibles):
        if "USB Audio" in nombre or "AB13X" in nombre:
            indice_usb = i
            break
            
    if indice_usb is None:
        indice_usb = 0
    
    mic = sr.Microphone(device_index=indice_usb)

    with mic as source:
        print("\nCalibrando estática de fondo por 2 segundos...")
        await asyncio.to_thread(r.adjust_for_ambient_noise, source, duration=2)
        r.dynamic_energy_threshold = True
    
        hablar("El sistema de audio está cien por ciento operativo.")
        print("Esperando comandos...")

        while True:
            try:
                audio = await asyncio.to_thread(escuchar_microfono, r, source)
                if not audio: continue
                
                texto = await asyncio.to_thread(decodificar_audio, r, audio)
                if not texto: continue
                    
                if NOMBRE_DEL_SERVIDOR in texto:
                    print(f"¡Te escuché!: \"{texto}\"")
                    comando = texto.replace(NOMBRE_DEL_SERVIDOR, "").strip()
                    
                    if comando:
                        asyncio.create_task(procesar_comando(comando))
                    else:
                        hablar("¿Sí?, dime.")
                        
            except sr.RequestError as e:
                await asyncio.sleep(5)
            except KeyboardInterrupt:
                break
            except Exception as e:
                await asyncio.sleep(1)


# ---------------------------------------------------------
# ARRANQUE DEL SISTEMA
# ---------------------------------------------------------
if __name__ == "__main__":
    os.system("rm -f /tmp/respuesta_*.mp3 2>/dev/null")
    os.system(f"rm -f {MPV_SOCKET} 2>/dev/null")
    os.system("pkill mpv 2>/dev/null")
    os.system("pkill mpg123 2>/dev/null")

    try:
        asyncio.run(bucle_asistente_async())
    except KeyboardInterrupt:
        os.system(f"rm -f {MPV_SOCKET} 2>/dev/null")
        os.system("pkill mpg123 2>/dev/null")
        os.system("pkill mpv 2>/dev/null")