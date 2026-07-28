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

# Configuraciones Globales
NOMBRE_DEL_SERVIDOR = "servidor"
proceso_voz = None

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
    print(f"Asistente: {texto}")
    try:
        tts = gTTS(text=texto, lang='es', tld='com.mx')
        # Usamos /tmp y el PID del proceso para que Linux limpie automáticamente la basura
        # y evitar conflictos si dos procesos intentan usar el mismo archivo.
        archivo_audio = f"/tmp/respuesta_{multiprocessing.current_process().pid}.mp3"
        tts.save(archivo_audio)
        
        # Reproduce el audio
        os.system(f"mpg123 -q -a plug:dmix {archivo_audio}")
        os.remove(archivo_audio)
    except Exception as e:
        print(f"Error en la voz: {e}")

def hablar(texto):
    """Gestor inteligente de la voz. Mata el audio anterior si existe."""
    global proceso_voz
    
    # Si ya está hablando, lo aniquilamos (modelo de interrupción)
    if proceso_voz and proceso_voz.is_alive():
        proceso_voz.terminate()
        proceso_voz.join()
        # Matamos el proceso de mpg123 a nivel del sistema operativo
        os.system("pkill mpg123 2>/dev/null") 
        
    proceso_voz = multiprocessing.Process(target=tarea_hablar, args=(texto,))
    proceso_voz.start()


# ---------------------------------------------------------
# 2. FUNCIONES DE BÚSQUEDA PESADAS
# ---------------------------------------------------------
def buscar_en_wiki(busqueda):
    """Función de red que bloquea. La enviaremos a un hilo."""
    pagina = wiki.page(busqueda)
    if pagina.exists():
        resumen = pagina.summary.split('\n')[0]
        enlace = pagina.fullurl
        mensaje = (
            f"\n**Concepto: {pagina.title}**\n\n"
            f"{resumen}\n\n"
            f"Leer más: <{enlace}>\n"
        )
        print(mensaje)
        return resumen
    else:
        print(f"ERROR: No encontré información sobre '{busqueda}'. Intenta ser más específico.")
        return f"No encontré información sobre '{busqueda}'"


def obtener_ofertas_steam_api():
    # Parámetros: Tienda=Steam, En oferta=Sí, Ordenar por=Ahorro, Mínimo de rating en Steam=80%
    url = "https://www.cheapshark.com/api/1.0/deals?storeID=1&onSale=1&sortBy=Savings&steamRating=80"
    
    # Añadimos un header básico para buenas prácticas
    headers = {'User-Agent': 'MiAsistenteLocal/1.0'}
    respuesta = requests.get(url, headers=headers).json()

    return respuesta

# ---------------------------------------------------------
# 3. CEREBRO ASÍNCRONO DEL ASISTENTE
# ---------------------------------------------------------
async def procesar_comando(comando_dictado):
    print(f"\nProcesando acción para: '{comando_dictado}'")

    if "hola" in comando_dictado:
        print("¡Hola, David! Sistema en línea y escuchando.")
        hablar("Hola, David. El sistema está activo.")

    elif "hora" in comando_dictado:
        ahora = datetime.now()
        texto_hora = f"{ahora.hour} con {ahora.minute} minutos"
        print(f"Hora del servidor: {texto_hora}")
        hablar(f"La hora del servidor es {texto_hora}")

    elif "memoria" in comando_dictado or "ram" in comando_dictado:
        print("Estado de la memoria RAM:")
        os.system("free -h")
        
        usada = subprocess.getoutput("free -m | awk '/^Mem:/ {print $3}'")
        total = subprocess.getoutput("free -m | awk '/^Mem:/ {print $2}'")
        hablar(f"El servidor está usando {usada} megabytes de memoria RAM, de un total de {total} megabytes.")

    elif "docker" in comando_dictado or "servicios" in comando_dictado:
        print("Contenedores activos en Docker:")
        os.system("sudo docker ps --format 'table {{.Names}}\t{{.Status}}'")
        
        contenedores = subprocess.getoutput("sudo docker ps --format '{{.Names}}'")
        if contenedores.strip():
            lista_hablada = contenedores.replace('\n', ', ')
            hablar(f"Los contenedores activos son: {lista_hablada}")
        else:
            hablar("No tienes ningún contenedor de Docker activo.")

    elif "limpiar" in comando_dictado:
        print("Limpiando caché y temporales...")
        os.system("rm -rf /tmp/* 2>/dev/null || true")
        hablar("Los archivos temporales han sido vaciados.")

    elif "reproduce" in comando_dictado or "pon música" in comando_dictado:
        if "reproduce" in comando_dictado:
            cancion = comando_dictado.split("reproduce")[1].strip()
        else:
            cancion = comando_dictado.split("pon música")[1].strip()

        print(f"Buscando música: {cancion}")
        hablar(f"Reproduciendo {cancion}")
        os.system("pkill mpv 2>/dev/null")
        
        comando = [
            "mpv", "--no-video", "--audio-device=alsa/plug:dmix", f"ytdl://ytsearch:{cancion}"
        ]
        subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- COMANDO DE SILENCIO TOTAL ---
    elif "detener" in comando_dictado or "silencio" in comando_dictado or "para la música" in comando_dictado:
        print("Deteniendo todos los audios...")
        os.system("pkill mpv 2>/dev/null")
        os.system("pkill mpg123 2>/dev/null")
        
        global proceso_voz
        if proceso_voz and proceso_voz.is_alive():
            proceso_voz.terminate()
            proceso_voz.join()
        
        # Solo lo decimos si el usuario no pidió "silencio" estricto
        if "silencio" not in comando_dictado:
            hablar("Reproducción detenida.")

    elif "volumen" in comando_dictado:
        print("Ajustando niveles de audio...")
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
        print(f"Buscando '{busqueda}' en la red...")
        
        # Ejecutamos la búsqueda de Wikipedia en un hilo para NO congelar el asistente
        texto_respuesta = await asyncio.to_thread(buscar_en_wiki, busqueda)
        hablar(texto_respuesta)

    elif "ofertas" in comando_dictado or "steam" in comando_dictado:
        print("Buscando las mejores ofertas en Steam...")
        
        lista_juegos = obtener_ofertas_steam_api()
        
        # Hacemos que la voz lea solo el top 3
        top3 = "Estas son las tres mejores ofertas en este momento:\n"
        
        for juego in lista_juegos[:3]:
            nombre = juego['title']
            descuento = round(float(juego['savings']))
            top3 += f"{nombre} con un {descuento} por ciento de descuento.\n"

        hablar(top3)
        hablar("He impreso la lista completa con otras 57 ofertas en tu consola.")
        
        # Imprimimos la lista masiva en la terminal para que la leas con calma
        print("\n--- LISTA COMPLETA DE OFERTAS ---")
        for juego in lista_juegos:
            print(f"- {juego['title']} - {round(float(juego['savings']))}% off (${juego['salePrice']})")
        print("---------------------------------\n")
    
    else:
        print("Comando no reconocido en la lista.")
        hablar("Disculpa, no tengo ese comando.")


# ---------------------------------------------------------
# 4. BUCLE DE ESCUCHA INFINITO (NO BLOQUEANTE)
# ---------------------------------------------------------
def escuchar_microfono(r, source):
    """Envuelve la función bloqueante de escucha."""
    try:
        return r.listen(source, timeout=None, phrase_time_limit=5)
    except sr.WaitTimeoutError:
        return None

def decodificar_audio(r, audio):
    """Envuelve la decodificación por red de Google."""
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
    
    print("Escaneando hardware de audio...")
    for i, nombre in enumerate(micros_disponibles):
        if "USB Audio" in nombre or "AB13X" in nombre:
            indice_usb = i
            print(f"Micrófono '{nombre}' mapeado correctamente en el índice {i}")
            break
            
    if indice_usb is None:
        print("No se encontró el micrófono USB. Usando el predeterminado (0).")
        indice_usb = 0
    
    mic = sr.Microphone(device_index=indice_usb)

    with mic as source:
        print("\nCalibrando estática de fondo por 2 segundos...")
        await asyncio.to_thread(r.adjust_for_ambient_noise, source, duration=2)
        r.dynamic_energy_threshold = True
    
        hablar("El sistema de audio está cien por ciento operativo. ¿Qué hacemos ahora?")
        print("Para ejecutar algo, di primero la palabra clave: 'Servidor'")
        print("Para salir del bucle, presiona Ctrl+C en la terminal.")
        print("-" * 60)

        while True:
            try:
                # 1. ESCUCHAR (Se envía a un hilo para que el bucle siga activo)
                audio = await asyncio.to_thread(escuchar_microfono, r, source)
                if not audio:
                    continue
                
                # 2. DECODIFICAR (También a un hilo porque Google tarda 1-2 segundos)
                texto = await asyncio.to_thread(decodificar_audio, r, audio)
                
                if not texto:
                    continue
                    
                # 3. VERIFICAR COMANDO
                if NOMBRE_DEL_SERVIDOR in texto:
                    print(f"¡Te escuché!: \"{texto}\"")
                    comando = texto.replace(NOMBRE_DEL_SERVIDOR, "").strip()
                    
                    if comando:
                        # DISPARA LA ACCIÓN EN SEGUNDO PLANO Y VUELVE A ESCUCHAR AL INSTANTE
                        asyncio.create_task(procesar_comando(comando))
                    else:
                        hablar("¿Sí?, dime.")
                        print("¿Sí? Dime qué comando quieres ejecutar.")
                        
            except sr.RequestError as e:
                print(f"Error de red: {e}")
                await asyncio.sleep(5)
            except KeyboardInterrupt:
                print("\nDesactivando el asistente en bucle. ¡Nos vemos!")
                break
            except Exception as e:
                print(f"Error inesperado en el bucle principal: {e}")
                await asyncio.sleep(1)


# ---------------------------------------------------------
# ARRANQUE DEL SISTEMA
# ---------------------------------------------------------
if __name__ == "__main__":
    # Limpiamos audios huérfanos de sesiones anteriores al arrancar
    os.system("rm -f /tmp/respuesta_*.mp3 2>/dev/null")
    os.system("pkill mpv 2>/dev/null")
    os.system("pkill mpg123 2>/dev/null")

    try:
        # Inicia el motor asíncrono
        asyncio.run(bucle_asistente_async())
    except KeyboardInterrupt:
        print("\nSistema apagado manualmente.")
        os.system("pkill mpg123 2>/dev/null")
        os.system("pkill mpv 2>/dev/null")