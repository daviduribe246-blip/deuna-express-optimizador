
import streamlit as st
import pandas as pd
import requests
import time
from urllib.parse import quote_plus

st.set_page_config(
    page_title="DeUna Express | Optimizador de rutas",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
USER_AGENT = "deuna-express-academic-routing-prototype/1.0"

# -----------------------------
# Funciones cartográficas
# -----------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def geocode_address(address: str):
    params = {
        "q": address,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "co",
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None

    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "display_name": data[0].get("display_name", address),
    }

@st.cache_data(ttl=3600, show_spinner=False)
def build_osrm_matrix(coords_tuple):
    coords = ";".join(f"{lon},{lat}" for lat, lon in coords_tuple)
    url = f"{OSRM_TABLE_URL}/{coords}"
    params = {"annotations": "distance,duration"}

    r = requests.get(url, params=params, timeout=40)
    r.raise_for_status()
    data = r.json()

    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM respondió: {data}")

    distances_km = [
        [x / 1000 if x is not None else None for x in row]
        for row in data["distances"]
    ]
    durations_min = [
        [x / 60 if x is not None else None for x in row]
        for row in data["durations"]
    ]

    return distances_km, durations_min

# -----------------------------
# Motor de optimización
# -----------------------------
def route_cost(route, matrix):
    if not route:
        return 0.0

    total = matrix[0][route[0]]
    for a, b in zip(route[:-1], route[1:]):
        total += matrix[a][b]
    total += matrix[route[-1]][0]
    return total

def clarke_wright(cost_matrix, n_customers, target_routes):
    """
    Clarke & Wright simplificado para un depósito y múltiples domiciliarios.
    Cada cliente empieza en una ruta individual y las rutas se fusionan
    según el ahorro generado.

    Esta V1 todavía no incorpora:
    - capacidad por domiciliario,
    - ventanas de tiempo,
    - prioridades,
    - pedidos dinámicos después de cerrar el lote.
    """
    routes = {i: [i] for i in range(1, n_customers + 1)}
    customer_route = {i: i for i in range(1, n_customers + 1)}

    savings = []
    for i in range(1, n_customers + 1):
        for j in range(i + 1, n_customers + 1):
            s = cost_matrix[0][i] + cost_matrix[0][j] - cost_matrix[i][j]
            savings.append((s, i, j))

    savings.sort(reverse=True, key=lambda x: x[0])

    def merge_if_possible(i, j):
        ri_id = customer_route[i]
        rj_id = customer_route[j]

        if ri_id == rj_id:
            return False

        ri = routes[ri_id]
        rj = routes[rj_id]

        if i not in (ri[0], ri[-1]) or j not in (rj[0], rj[-1]):
            return False

        if ri[-1] != i:
            ri = list(reversed(ri))

        if rj[0] != j:
            rj = list(reversed(rj))

        merged = ri + rj

        routes[ri_id] = merged
        del routes[rj_id]

        for c in merged:
            customer_route[c] = ri_id

        return True

    for _, i, j in savings:
        if len(routes) <= target_routes:
            break
        merge_if_possible(i, j)

    # Si aún hay más rutas que domiciliarios, se combinan de forma controlada.
    while len(routes) > target_routes:
        ids = list(routes.keys())
        best = None

        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                ida, idb = ids[a], ids[b]
                ra, rb = routes[ida], routes[idb]

                before = route_cost(ra, cost_matrix) + route_cost(rb, cost_matrix)

                candidates = [
                    ra + rb,
                    ra + list(reversed(rb)),
                    list(reversed(ra)) + rb,
                    list(reversed(ra)) + list(reversed(rb)),
                ]

                for merged in candidates:
                    increase = route_cost(merged, cost_matrix) - before
                    if best is None or increase < best[0]:
                        best = (increase, merged, ida, idb)

        if best is None:
            break

        _, merged, keep_id, drop_id = best
        routes[keep_id] = merged
        del routes[drop_id]

        for c in merged:
            customer_route[c] = keep_id

    return list(routes.values())

def google_maps_route_link(depot, ordered_addresses):
    origin = quote_plus(depot)
    destination = quote_plus(depot)
    waypoints = "|".join(quote_plus(a) for a in ordered_addresses)

    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin}"
        f"&destination={destination}"
        f"&waypoints={waypoints}"
        "&travelmode=driving"
    )

# -----------------------------
# Interfaz
# -----------------------------
st.title("🚚 DeUna Express")
st.subheader("Optimizador web de rutas de última milla")
st.caption(
    "Prototipo académico: el usuario ingresa direcciones y el sistema genera "
    "automáticamente la matriz de viaje y las rutas sugeridas."
)

with st.sidebar:
    st.header("Configuración del lote")

    depot = st.text_input(
        "Dirección del punto de salida",
        placeholder="Ej.: Calle 15 # 7-25, Riohacha, La Guajira"
    )

    couriers = st.number_input(
        "Número de domiciliarios disponibles",
        min_value=1,
        max_value=20,
        value=2,
        step=1
    )

    objective = st.selectbox(
        "Objetivo de optimización",
        ["Tiempo de viaje", "Distancia"]
    )

    st.divider()
    st.caption(
        "Versión 1: un depósito, rutas cerradas y un lote estático de pedidos."
    )

st.markdown("### 1. Ingrese los pedidos")

example = pd.DataFrame({
    "Pedido": ["P001", "P002", "P003", "P004"],
    "Cliente": ["", "", "", ""],
    "Dirección": ["", "", "", ""],
})

orders = st.data_editor(
    example,
    num_rows="dynamic",
    hide_index=True,
    use_container_width=True,
    column_config={
        "Pedido": st.column_config.TextColumn("Pedido", required=True),
        "Cliente": st.column_config.TextColumn("Cliente"),
        "Dirección": st.column_config.TextColumn(
            "Dirección",
            required=True,
            help="Incluya Riohacha, La Guajira cuando sea posible."
        ),
    }
)

st.markdown("### 2. Ejecute la optimización")

optimize = st.button(
    "⚡ Optimizar rutas",
    type="primary",
    use_container_width=True
)

if optimize:
    try:
        df = orders.copy()
        df["Pedido"] = df["Pedido"].fillna("").astype(str).str.strip()
        df["Cliente"] = df["Cliente"].fillna("").astype(str).str.strip()
        df["Dirección"] = df["Dirección"].fillna("").astype(str).str.strip()
        df = df[(df["Pedido"] != "") & (df["Dirección"] != "")].reset_index(drop=True)

        if not depot.strip():
            st.error("Ingrese la dirección del punto de salida.")
            st.stop()

        if df.empty:
            st.error("Ingrese por lo menos un pedido con su dirección.")
            st.stop()

        if int(couriers) > len(df):
            st.warning(
                "Hay más domiciliarios que pedidos. El sistema usará como máximo "
                f"{len(df)} rutas."
            )

        target_routes = min(int(couriers), len(df))

        with st.status("Procesando el lote...", expanded=True) as status:
            st.write("📍 Localizando el punto de salida...")
            depot_geo = geocode_address(depot)

            if depot_geo is None:
                st.error(
                    "No fue posible localizar el punto de salida. "
                    "Revise la dirección e intente nuevamente."
                )
                st.stop()

            points = [depot_geo]
            unresolved = []

            st.write("📍 Localizando las direcciones de los clientes...")

            for idx, row in df.iterrows():
                address = row["Dirección"]

                if "riohacha" not in address.lower():
                    address = f"{address}, Riohacha, La Guajira, Colombia"

                geo = geocode_address(address)

                if geo is None:
                    unresolved.append((row["Pedido"], row["Dirección"]))
                else:
                    points.append(geo)

                # Respeta el uso moderado del servicio público.
                time.sleep(1.05)

            if unresolved:
                st.error("No fue posible localizar una o más direcciones:")
                for pedido, direccion in unresolved:
                    st.write(f"• {pedido}: {direccion}")
                st.info(
                    "Corrija esas direcciones. Conviene incluir barrio, calle/carrera "
                    "y la ciudad."
                )
                st.stop()

            st.write("🧮 Generando automáticamente la matriz de viaje...")

            coords_tuple = tuple(
                (round(p["lat"], 7), round(p["lon"], 7))
                for p in points
            )

            dist_km, dur_min = build_osrm_matrix(coords_tuple)

            cost_matrix = dur_min if objective == "Tiempo de viaje" else dist_km

            st.write("🚚 Ejecutando el algoritmo de Clarke & Wright...")

            routes = clarke_wright(
                cost_matrix=cost_matrix,
                n_customers=len(df),
                target_routes=target_routes,
            )

            status.update(
                label="Optimización completada",
                state="complete"
            )

        st.divider()
        st.markdown("## Resultado de la optimización")

        total_distance = 0.0
        total_time = 0.0

        metric1, metric2, metric3 = st.columns(3)

        for rnum, route in enumerate(routes, start=1):
            distance = route_cost(route, dist_km)
            duration = route_cost(route, dur_min)

            total_distance += distance
            total_time += duration

            selected = [df.iloc[i - 1] for i in route]

            sequence = (
                ["Depósito"]
                + [str(r["Pedido"]) for r in selected]
                + ["Depósito"]
            )

            with st.container(border=True):
                st.markdown(f"### Domiciliario {rnum}")
                st.write(" → ".join(sequence))

                c1, c2 = st.columns(2)
                c1.metric("Distancia estimada", f"{distance:.2f} km")
                c2.metric("Tiempo estimado", f"{duration:.1f} min")

                detail = pd.DataFrame({
                    "Orden": list(range(1, len(selected) + 1)),
                    "Pedido": [r["Pedido"] for r in selected],
                    "Cliente": [r["Cliente"] for r in selected],
                    "Dirección": [r["Dirección"] for r in selected],
                })

                st.dataframe(
                    detail,
                    use_container_width=True,
                    hide_index=True
                )

                maps_link = google_maps_route_link(
                    depot,
                    [r["Dirección"] for r in selected]
                )

                st.link_button(
                    "🗺️ Abrir esta ruta en Google Maps",
                    maps_link,
                    use_container_width=True
                )

        metric1.metric("Rutas generadas", len(routes))
        metric2.metric("Distancia total", f"{total_distance:.2f} km")
        metric3.metric("Tiempo acumulado", f"{total_time:.1f} min")

        st.markdown("### Mapa de los puntos")
        map_df = pd.DataFrame({
            "lat": [p["lat"] for p in points],
            "lon": [p["lon"] for p in points],
        })
        st.map(map_df, use_container_width=True)

        with st.expander("Ver matriz generada automáticamente"):
            labels = ["Depósito"] + df["Pedido"].tolist()
            matrix_df = pd.DataFrame(
                cost_matrix,
                index=labels,
                columns=labels
            )

            decimals = 1 if objective == "Tiempo de viaje" else 2
            st.dataframe(
                matrix_df.round(decimals),
                use_container_width=True
            )

            unit = "minutos" if objective == "Tiempo de viaje" else "kilómetros"
            st.caption(f"Unidad de la matriz: {unit}.")

        st.info(
            "Esta matriz es generada por el sistema. El usuario no tiene que "
            "construirla ni escribirla manualmente."
        )

    except requests.RequestException as e:
        st.error(
            "No fue posible comunicarse con el servicio cartográfico. "
            "Intente nuevamente en unos minutos."
        )
        st.caption(str(e))

    except Exception as e:
        st.error("Se produjo un error durante la optimización.")
        st.exception(e)
