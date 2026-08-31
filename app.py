import streamlit as st
import pandas as pd
import requests
import time
from urllib.parse import quote_plus
import pulp

st.set_page_config(page_title="DeUna Express | VRP", page_icon="🛵", layout="wide")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
USER_AGENT = "deuna-express-vrp-degree-project/2.0"

@st.cache_data(ttl=86400, show_spinner=False)
def geocode(address):
    r = requests.get(
        NOMINATIM_URL,
        params={"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "co"},
        headers={"User-Agent": USER_AGENT},
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}

@st.cache_data(ttl=3600, show_spinner=False)
def matrices(coords_tuple):
    coords = ";".join(f"{lon},{lat}" for lat, lon in coords_tuple)
    r = requests.get(
        f"{OSRM_TABLE_URL}/{coords}",
        params={"annotations": "distance,duration"},
        timeout=50,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(str(data))
    d = [[x/1000 for x in row] for row in data["distances"]]
    t = [[x/60 for x in row] for row in data["durations"]]
    return d, t

def solve_vrp(cost, n, m, limit=60):
    N = range(1, n+1)
    V = range(0, n+1)
    K = range(1, m+1)

    model = pulp.LpProblem("DeUna_Express_VRP", pulp.LpMinimize)

    x = {(i,j,k): pulp.LpVariable(f"x_{i}_{j}_{k}", cat="Binary")
         for k in K for i in V for j in V if i != j}
    y = {k: pulp.LpVariable(f"y_{k}", cat="Binary") for k in K}
    u = {i: pulp.LpVariable(f"u_{i}", lowBound=1, upBound=n) for i in N}

    model += pulp.lpSum(cost[i][j]*x[i,j,k]
                        for k in K for i in V for j in V if i != j)

    for j in N:
        model += pulp.lpSum(x[i,j,k] for k in K for i in V if i != j) == 1

    for k in K:
        for h in N:
            model += (
                pulp.lpSum(x[i,h,k] for i in V if i != h)
                ==
                pulp.lpSum(x[h,j,k] for j in V if j != h)
            )

    for k in K:
        model += pulp.lpSum(x[0,j,k] for j in N) == y[k]
        model += pulp.lpSum(x[i,0,k] for i in N) == y[k]

    model += pulp.lpSum(y[k] for k in K) == m

    for i in N:
        for j in N:
            if i != j:
                model += (
                    u[i] - u[j]
                    + n*pulp.lpSum(x[i,j,k] for k in K)
                    <= n - 1
                )

    model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=limit))
    status = pulp.LpStatus[model.status]

    routes = []
    for k in K:
        if pulp.value(y[k]) is None or pulp.value(y[k]) < 0.5:
            continue
        route = [0]
        current = 0
        seen = set()
        for _ in range(n+2):
            nxt = None
            for j in V:
                if current != j and (current,j,k) in x:
                    v = pulp.value(x[current,j,k])
                    if v is not None and v > 0.5:
                        nxt = j
                        break
            if nxt is None:
                break
            route.append(nxt)
            if nxt == 0:
                break
            if nxt in seen:
                break
            seen.add(nxt)
            current = nxt
        routes.append((k, route))

    return status, pulp.value(model.objective), routes

def route_value(route, matrix):
    return sum(matrix[a][b] for a,b in zip(route[:-1], route[1:]))

def maps_link(depot, addresses):
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(depot)}"
        f"&destination={quote_plus(depot)}"
        f"&waypoints={'|'.join(quote_plus(a) for a in addresses)}"
        "&travelmode=driving"
    )

st.title("🛵 DeUna Express")
st.subheader("Optimización de rutas por batch")
st.caption("Modelo VRP entero-mixto: clientes y motocicletas variables en cada batch.")

with st.sidebar:
    st.header("Configuración")
    batch = st.text_input("Identificador del batch", "Batch 1")
    depot = st.text_input("Dirección del depósito")
    motos = st.number_input("Motocicletas a utilizar", min_value=1, max_value=30, value=2)
    criterio = st.selectbox("Criterio", ["Menor tiempo total", "Menor distancia total"])
    limite = st.selectbox("Tiempo máximo de cálculo", [30,60,120], index=1)

st.markdown("## Pedidos del batch")
df0 = pd.DataFrame({
    "Pedido": ["P001","P002","P003","P004"],
    "Cliente": ["","","",""],
    "Dirección": ["","","",""]
})
orders = st.data_editor(df0, num_rows="dynamic", hide_index=True, use_container_width=True)

if st.button("🚀 Optimizar rutas", type="primary", use_container_width=True):
    df = orders.copy()
    for c in ["Pedido","Cliente","Dirección"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = df[(df["Pedido"]!="") & (df["Dirección"]!="")].reset_index(drop=True)

    n = len(df)
    m = int(motos)

    if not depot.strip():
        st.error("Ingrese la dirección del depósito.")
        st.stop()
    if n == 0:
        st.error("Ingrese al menos un pedido.")
        st.stop()
    if m > n:
        st.error("No puede utilizar más motocicletas que clientes en este modelo.")
        st.stop()

    with st.status("Procesando...", expanded=True) as status_box:
        st.write("Geocodificando depósito y clientes...")
        p0 = geocode(depot)
        if p0 is None:
            st.error("No fue posible localizar el depósito.")
            st.stop()

        points = [p0]
        for _, row in df.iterrows():
            addr = row["Dirección"]
            if "riohacha" not in addr.lower():
                addr += ", Riohacha, La Guajira, Colombia"
            p = geocode(addr)
            if p is None:
                st.error(f"No fue posible localizar: {row['Dirección']}")
                st.stop()
            points.append(p)
            time.sleep(1.05)

        st.write("Generando matrices automáticas...")
        coords = tuple((round(p["lat"],7), round(p["lon"],7)) for p in points)
        dist, dur = matrices(coords)

        cost = dur if criterio == "Menor tiempo total" else dist
        unit = "min" if criterio == "Menor tiempo total" else "km"

        st.write("Resolviendo el modelo matemático VRP...")
        solver_status, objective, routes = solve_vrp(cost, n, m, int(limite))
        status_box.update(label="Optimización finalizada", state="complete")

    if not routes:
        st.error(f"No se obtuvieron rutas. Estado: {solver_status}")
        st.stop()

    st.markdown(f"## Resultado — {batch}")
    a,b,c,d = st.columns(4)
    a.metric("Clientes", n)
    b.metric("Motocicletas", m)
    c.metric("Estado", solver_status)
    d.metric("Función objetivo", f"{objective:.2f} {unit}" if objective is not None else "N/D")

    total_d = 0
    total_t = 0

    for k, route in routes:
        clients = [node for node in route if node != 0]
        rows = [df.iloc[node-1] for node in clients]
        rd = route_value(route, dist)
        rt = route_value(route, dur)
        total_d += rd
        total_t += rt

        with st.container(border=True):
            st.markdown(f"### Motocicleta {k}")
            st.write(" → ".join(["Depósito"] + [str(r["Pedido"]) for r in rows] + ["Depósito"]))
            c1,c2,c3 = st.columns(3)
            c1.metric("Clientes asignados", len(rows))
            c2.metric("Distancia", f"{rd:.2f} km")
            c3.metric("Tiempo", f"{rt:.1f} min")

            detail = pd.DataFrame({
                "Orden": range(1, len(rows)+1),
                "Pedido": [r["Pedido"] for r in rows],
                "Cliente": [r["Cliente"] for r in rows],
                "Dirección": [r["Dirección"] for r in rows],
            })
            st.dataframe(detail, hide_index=True, use_container_width=True)
            st.link_button("Abrir ruta en Google Maps",
                           maps_link(depot, [r["Dirección"] for r in rows]),
                           use_container_width=True)

    st.markdown("### Indicadores globales")
    q1,q2 = st.columns(2)
    q1.metric("Distancia total", f"{total_d:.2f} km")
    q2.metric("Tiempo total acumulado", f"{total_t:.1f} min")

    st.markdown("### Mapa")
    st.map(pd.DataFrame({"lat":[p["lat"] for p in points],
                         "lon":[p["lon"] for p in points]}),
           use_container_width=True)

    with st.expander("Ver matriz generada automáticamente"):
        labels = ["Depósito"] + df["Pedido"].tolist()
        mat = pd.DataFrame(cost, index=labels, columns=labels)
        st.dataframe(mat.round(1 if unit=="min" else 2), use_container_width=True)

    with st.expander("Ver formulación matemática implementada"):
        st.latex(r"\min Z=\sum_{k\in K}\sum_{i\in V}\sum_{j\in V,\ j\neq i} c_{ij}x_{ijk}")
        st.markdown("""
- Cada cliente se visita exactamente una vez.
- Se conserva el flujo en cada cliente para cada motocicleta.
- Cada motocicleta utilizada sale y regresa al depósito.
- Se utilizan exactamente las motocicletas indicadas para el batch.
- Se eliminan subrutas mediante restricciones MTZ.
- `c_ij` corresponde a tiempo o distancia según el criterio seleccionado.
        """)
