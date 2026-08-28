
# DeUna Express — Optimizador web de rutas

Aplicación web académica desarrollada con Python y Streamlit.

## Qué hace

El usuario:

1. Ingresa la dirección del punto de salida.
2. Indica cuántos domiciliarios están disponibles.
3. Escribe los pedidos y direcciones.
4. Presiona **Optimizar rutas**.

El sistema:

1. Convierte direcciones en coordenadas.
2. Genera automáticamente una matriz de tiempos y distancias.
3. Ejecuta una heurística de Clarke & Wright.
4. Asigna y ordena los clientes por ruta.
5. Muestra distancia, tiempo y secuencia.
6. Genera un botón para abrir cada recorrido en Google Maps.

## Importante

El usuario final NO necesita instalar Python cuando la aplicación está publicada
en Internet. Solo necesita abrir el enlace desde un navegador.

---

# Publicación en Streamlit Community Cloud

## Paso 1. Crear una cuenta en GitHub

Entre en:

https://github.com/

Cree una cuenta si todavía no tiene una.

## Paso 2. Crear un repositorio

Cree un repositorio, por ejemplo:

deuna-express-optimizador

Suba a ese repositorio los archivos de esta carpeta:

- app.py
- requirements.txt
- runtime.txt
- .streamlit/config.toml

## Paso 3. Entrar a Streamlit Community Cloud

Entre en:

https://share.streamlit.io/

Inicie sesión con GitHub.

## Paso 4. Crear la aplicación

Seleccione:

Create app / Deploy an app

Configure:

Repository:
su-usuario/deuna-express-optimizador

Branch:
main

Main file path:
app.py

Luego pulse Deploy.

Después de unos minutos recibirá una dirección web parecida a:

https://deuna-express-optimizador.streamlit.app

Ese será el enlace que podrá abrir la secretaria desde un computador o celular.

---

# Alcance de esta V1

- Un único depósito.
- Lote estático de pedidos.
- Número configurable de domiciliarios.
- Optimización por tiempo o distancia.
- Clarke & Wright simplificado.
- Mapa de los puntos.
- Botón para abrir la ruta en Google Maps.
- Matriz de viaje generada automáticamente.

# Próxima V2 recomendada

1. Carga masiva desde Excel.
2. Capacidad por domiciliario.
3. Ventanas de tiempo.
4. Prioridades.
5. Batches de 30 o 60 minutos.
6. Historial de optimizaciones.
7. Registro de hora de recepción y entrega.
8. Indicadores de desempeño.
9. Inicio de sesión.
10. Base de datos.

# Nota técnica

Esta versión usa servicios públicos de Nominatim/OpenStreetMap y OSRM para
prototipado académico y pruebas de bajo volumen. Para una operación empresarial
continua conviene migrar a un proveedor comercial o a una infraestructura
propia, respetando límites de uso y condiciones de servicio.
