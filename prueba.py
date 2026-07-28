import requests

def obtener_mejores_descuentos_steam():
    # Parámetros: Tienda=Steam, En oferta=Sí, Ordenar por=Ahorro, Mínimo de rating en Steam=80%
    url = "https://www.cheapshark.com/api/1.0/deals?storeID=1&onSale=1&sortBy=Savings&steamRating=85"
    
    # Añadimos un header básico para buenas prácticas
    headers = {'User-Agent': 'MiAsistenteLocal/1.0'}
    respuesta = requests.get(url, headers=headers).json()

    print("💰 MEJORES DESCUENTOS DE STEAM (Juegos con buenas reseñas) 💰\n")
    for juego in respuesta:
        nombre = juego['title']
        precio_normal = juego['normalPrice']
        precio_oferta = juego['salePrice']
        descuento = round(float(juego['savings']))
        
        print(f"🎮 {nombre}")
        print(f"   Ahorro: {descuento}% (De ${precio_normal} a ${precio_oferta})\n")

obtener_mejores_descuentos_steam()