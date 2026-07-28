import os
import time
import speech_recognition as sr
import subprocess
import wikipediaapi
from datetime import datetime
from gtts import gTTS

wiki = wikipediaapi.Wikipedia(
    user_agent='AsistenteLocal/1.0 (contacto: daviddiazdh)',
    language='es',
    extract_format=wikipediaapi.ExtractFormat.WIKI
)

NOMBRE_DEL_SERVIDOR = "servidor"

def hablar(texto):
    print(f"Asistente: {texto}")
    tts = gTTS(text=texto, lang='es', tld='com.mx')
    archivo_audio = "respuesta.mp3"
    tts.save(archivo_audio)
    os.system(f"mpg123 -q -a plug:dmix {archivo_audio}")
    os.remove(archivo_audio)

def ejecutar_comando_sistema(comando_dictado):
    print(f"\nProcesando acción para: '{comando_dictado}'")

    if "hola" in comando_dictado:
        print("¡Hola, David! Sistema en línea y escuchando.")
        hablar("Hola, David. El sistema está activo.")

    elif "hora" in comando_dictado:
        print("Hora del servidor:")
        ahora = datetime.now()
        texto_hora = f"{ahora.hour} con {ahora.minute} minutos"
        hablar(f"La hora del servidor es {texto_hora}")

    elif "memoria" in comando_dictado or "ram" in comando_dictado:
        print("Estado de la memoria RAM:")
        # Imprimimos la tabla normal en la consola para que la veas
        os.system("free -h")
        
        # Filtramos los números en Megabytes para que la voz no se enrede con las letras "Gi" o "Mi"
        usada = subprocess.getoutput("free -m | awk '/^Mem:/ {print $3}'")
        total = subprocess.getoutput("free -m | awk '/^Mem:/ {print $2}'")
        hablar(f"El servidor está usando {usada} megabytes de memoria RAM, de un total de {total} megabytes.")

    elif "docker" in comando_dictado or "servicios" in comando_dictado:
        print("Contenedores activos en Docker:")
        os.system("sudo docker ps --format 'table {{.Names}}\t{{.Status}}'")
        
        contenedores = subprocess.getoutput("sudo docker ps --format '{{.Names}}'")
        
        if contenedores.strip():
            # Reemplaza los saltos de línea por comas para que la voz haga pausas al leer
            lista_hablada = contenedores.replace('\n', ', ')
            hablar(f"Los contenedores activos son: {lista_hablada}")
        else:
            hablar("No tienes ningún contenedor de Docker activo.")

    elif "limpiar" in comando_dictado:
        print("Limpiando caché y temporales...")
        os.system("rm -rf /tmp/* 2>/dev/null || true")
        hablar("Los archivos temporales han sido vaciados.")

    elif "reproduce" in comando_dictado or "pon música" in comando_dictado:
        # Extraemos el nombre de la canción (todo lo que digas después de la palabra clave)
        if "reproduce" in comando_dictado:
            cancion = comando_dictado.split("reproduce")[1].strip()
        else:
            cancion = comando_dictado.split("pon música")[1].strip()

        print(f"Buscando música: {cancion}")
        hablar(f"Reproduciendo {cancion}")
        
        # Matamos cualquier canción que ya esté sonando para no mezclar audios
        os.system("pkill mpv")
        
        # Armamos el comando forzando la salida de audio por el huequito verde trasero
        comando = [
            "mpv", 
            "--no-video", 
            "--audio-device=alsa/plug:dmix", 
            f"ytdl://ytsearch:{cancion}"
        ]
        
        # Lo lanzamos con Popen (en segundo plano) apagando los textos de error para no ensuciar la consola
        subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif "detener" in comando_dictado or "silencio" in comando_dictado or "para la música" in comando_dictado:
        print("Deteniendo reproducción...")
        os.system("pkill mpv")
        hablar("Música detenida.")

    elif "volumen" in comando_dictado:
        print("Ajustando niveles de audio...")
        if "subir" in comando_dictado or "más" in comando_dictado:
            # Sube el volumen general un 15%
            os.system("amixer -c 0 sset Master 15%+")
            hablar("Volumen arriba.")
            
        elif "bajar" in comando_dictado or "menos" in comando_dictado:
            # Baja el volumen general un 15%
            os.system("amixer -c 0 sset Master 15%-")
            hablar("Volumen abajo.")
            
        elif "máximo" in comando_dictado:
            os.system("amixer -c 0 sset Master 100%")
            hablar("Volumen al máximo.")

    elif "definir" in comando_dictado:

        busqueda = comando_dictado.replace("definir", "").strip()

        pagina = wiki.page(busqueda)

        if pagina.exists():
            # Tomamos los primeros 1000 caracteres para no llenar el chat
            resumen = pagina.summary[:1000] + "..."
            enlace = pagina.fullurl
            
            # Creamos una respuesta elegante
            mensaje = (
                f"**Concepto: {pagina.title}**\n\n"
                f"{resumen}\n\n"
                f"Leer más: <{enlace}>"
            )
            print(mensaje)
            hablar(resumen[:500])
        else:
            print(f"ERROR: No encontré información sobre '{busqueda}'. Intenta ser más específico.")
            hablar(f"No encontré información sobre '{busqueda}'")
        
    else:
        print("Comando no reconocido en la lista.")
        hablar("Disculpa, no tengo ese comando.")

def bucle_asistente():
    r = sr.Recognizer()
    
    # Búsqueda dinámica del micrófono ---
    micros_disponibles = sr.Microphone.list_microphone_names()
    indice_usb = None
    
    print("Escaneando hardware de audio...")
    for i, nombre in enumerate(micros_disponibles):
        # Buscamos "USB Audio" o "AB13X"
        if "USB Audio" in nombre or "AB13X" in nombre:
            indice_usb = i
            print(f"Micrófono '{nombre}' mapeado correctamente en el índice {i}")
            break
            
    if indice_usb is None:
        print("No se encontró el micrófono USB en la lista de PyAudio. Usando el predeterminado (0).")
        print("Hardware detectado:", micros_disponibles)
        indice_usb = 0
    
    mic = sr.Microphone(device_index=indice_usb)

    with mic as source:
        print("\n Calibrando estática de fondo por 2 segundos...")
        r.adjust_for_ambient_noise(source, duration=2)
        r.dynamic_energy_threshold = True
	
        hablar("El sistema de audio está cien por ciento operativo. ¿Qué hacemos ahora?")
        print("Para ejecutar algo, di primero la palabra clave: 'Servidor' (Ej: 'Servidor, dame la hora')")
        print("Para salir del bucle, presiona Ctrl+C en la terminal.")
        print("-" * 60)

        while True:
            try:
                # print("\n Esperando palabra clave...")
                # Escucha silenciosa (frases cortas de máximo 4 segundos para detectar el llamado)
                audio = r.listen(source, timeout=None, phrase_time_limit=5)
                
                # print(" Analizando posible comando...")
                texto = r.recognize_google(audio, language="es-VE").lower()
                
                # Comprobamos si nos están llamando
                if NOMBRE_DEL_SERVIDOR in texto:
                    print(f"¡Te escuché!: \"{texto}\"")
                    
                    # Limpiamos la palabra 'servidor' para quedarnos solo con la orden
                    comando = texto.replace(NOMBRE_DEL_SERVIDOR, "").strip()
                    
                    if comando:
                        ejecutar_comando_sistema(comando)
                    else:
                        hablar("¿Sí?, dime.")
                        print("¿Sí? Dime qué comando quieres ejecutar.")
                
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Error de red: {e}")
                time.sleep(5)
            except KeyboardInterrupt:
                print("\nDesactivando el asistente en bucle. ¡Nos vemos!")
                break

if __name__ == "__main__":
    bucle_asistente()