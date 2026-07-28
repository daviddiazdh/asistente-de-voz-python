import wikipediaapi

wiki = wikipediaapi.Wikipedia(
    user_agent='MiEstudioBot/1.0 (contacto: daviddiazdh)',
    language='es',
    extract_format=wikipediaapi.ExtractFormat.WIKI
)

busqueda = "Inteligencia Artificial"

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
else:
    print(f"ERROR: No encontré información sobre '{busqueda}'. Intenta ser más específico.")
