from flask import Flask, render_template, jsonify, request  # type: ignore
from time import perf_counter
import math

app = Flask(__name__)

BASE_TIMES = {
    'blando': 80.0,
    'medio': 80.4,
    'duro': 80.7,
    'intermedio': 90.0,
    'lluvia': 95.0,
}

# Curvas de degradación / ritmo base
DEGRADE_FACTORS = {
    'blando': 1.005,
    'medio': 1.002,
    'duro': 1.00095,
    'intermedio': 1.001,
    'lluvia': 1.0012,
}

# Modificadores por clima
WEATHER_MOD = {
    'dry': {
        'blando': 1.0,
        'medio': 1.0,
        'duro': 1.0,
        'intermedio': 1.1,
        'lluvia': 1.2,
    },
    'rain': {
        'blando': 1.1,
        'medio': 1.1,
        'duro': 1.1,
        'intermedio': 0.9,
        'lluvia': 1.0,
    },
    'heavyrain': {
        'blando': 1.2,
        'medio': 1.2,
        'duro': 1.2,
        'intermedio': 1.0,
        'lluvia': 0.9,
    }
}

# Función genérica
def tiempo_neumatico(tipo: str, vuelta: int, weather: str):
    base = BASE_TIMES[tipo]
    factor = DEGRADE_FACTORS[tipo] ** (vuelta**2)
    weather_mod = WEATHER_MOD.get(weather, WEATHER_MOD['dry'])[tipo]
    return (base * weather_mod + factor)

# Precomputar tiempos de stints para cada tipo de neumático y duración
def precalcular_tiempos(NUM_LAPS, weather: str, extra_stint=0):
    print(f"[DEBUG] Entrando en precalcular_tiempos: NUM_LAPS={NUM_LAPS}, extra_stint={extra_stint}")
    tiempos = {"blando": {}, "medio": {}, "duro": {}, "intermedio": {}, "lluvia": {}}
    
    for tipo in tiempos:
        for duracion in range(0, NUM_LAPS + extra_stint + 1):
            if duracion == 0:
                tiempos[tipo][duracion] = 0
            else:
                tiempos[tipo][duracion] = sum(tiempo_neumatico(tipo, v, weather) for v in range(1,duracion+1))
        print(f"[DEBUG]   {tipo}: precomputados {len(tiempos[tipo])} valores")
    print("[DEBUG] Salida de precalcular_tiempos")
    
    return tiempos

# Formatear segundos en h, m, s
def formatear_tiempo(segundos):
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos = segundos % 60
    return f"{int(horas)}h {int(minutos)}m {segundos:.2f}s"
    

# -----------------------------------------------------------
# Algoritmo de Programación Dinámica optimizado y corregido
# -----------------------------------------------------------
def encontrar_mejores_estrategias_dp(
    NUM_LAPS,
    PENALIZACION_PARADA,
    PENALIZACION_PARADA_EVENTO,
    tiempos_prec,
    already_pitted,
    current_tyre,
    current_tyre_laps,
):
    print(f"[DEBUG] Iniciando DP: NUM_LAPS={NUM_LAPS}, PEN_PARADA={PENALIZACION_PARADA}, PEN_EVENT={PENALIZACION_PARADA_EVENTO}, already_pitted={already_pitted}, current_tyre={current_tyre}, current_tyre_laps={current_tyre_laps}")
    tipos = ["blando", "medio", "duro", "intermedio", "lluvia"]
    max_paradas = 3
    V = NUM_LAPS  # vueltas restantes

    dp = {}
    prev = {}

    # Estado inicial “sin parar”
    initial_last = current_tyre if current_tyre else None
    dp[(0, 0, initial_last, 0)] = 0

    # Estado inicial “con parada en 0” → cambiar a cada compuesto t ≠ current_tyre
    if current_tyre:
        for t in tipos:
            if t != current_tyre: 
                dp[(0, 1, t, 1)] = PENALIZACION_PARADA_EVENTO
                prev[(0, 1, t, 1)] = (0, 0, initial_last, 0, t, 0)
                print(f"[DEBUG] Estado inicial con pitstop 0: dp(0,1,{t},1) = {PENALIZACION_PARADA_EVENTO}")
            else:               
                dp[(0, 1, t, 0)] = PENALIZACION_PARADA_EVENTO
                prev[(0, 1, t, 0)] = (0, 0, initial_last, 0, t, 0)
                print(f"[DEBUG] Estado inicial con pitstop 0: dp(0,1,{t},1) = {PENALIZACION_PARADA_EVENTO}")


    # Recorremos todos los posibles estados
    for v_prev in range(V + 1):
        for s_prev in range(max_paradas + 1):
            for last_prev in tipos + [None]:
                for c_prev in range(max_paradas + 1):
                    estado = (v_prev, s_prev, last_prev, c_prev)
                    if estado not in dp:
                        continue
                    tiempo_prev = dp[estado]
                    if v_prev == V:
                        continue

                    for dur in range(1, V - v_prev + 1):
                        for t in tipos:
        
                            s_next = s_prev + (1 if v_prev > 0 else 0)
                            if s_next > max_paradas:
                                continue

                            cambios = c_prev + (1 if (last_prev and t != last_prev) else 0)
                            if cambios > s_next:
                                continue
                            if not already_pitted and s_next > 0 and cambios < 1:
                                continue

                            # Si es el primer stint SIN haber parado, continúo el desgaste:
                            if (v_prev == 0 and s_prev == 0
                                    and last_prev == current_tyre
                                    and current_tyre_laps > 0
                                    and t == current_tyre):
                                base = tiempos_prec[t][dur + current_tyre_laps] - tiempos_prec[t][current_tyre_laps]
                            else:
                                # Cualquier otro caso (incluido pit-stop en vuelta 0) es un neumático fresco
                                base = tiempos_prec[t][dur]

                            if v_prev == 0:
                                penalty = 0
                            else:
                                penalty = PENALIZACION_PARADA

                            nuevo_t = tiempo_prev + base + penalty
                            nuevo_estado = (v_prev + dur, s_next, t, cambios)

                            # DEBUG: registro de actualización de DP
                            if nuevo_estado not in dp or nuevo_t < dp[nuevo_estado]:
                                dp[nuevo_estado] = nuevo_t
                                prev[nuevo_estado] = (v_prev, s_prev, last_prev, c_prev, t, dur)
                                #print(f"[DEBUG] dp{nuevo_estado} = {nuevo_t:.2f} (prev {estado}, stint {(t,dur)}, penalty={penalty})")

    print(f"[DEBUG] DP finalizado: tamaño dp={len(dp)} estados")

    # Extraer las 4 estrategias más rápidas generales
    # 1) Filtrar todos los estados finales (vuelta == V)
    final_states = [ (key, dp[key]) for key in dp if key[0] == V ]
    if not final_states:
        print("[DEBUG] No se encontraron estados finales en DP")
        return {}

    # 2) Ordenar por tiempo ascendente y quedarnos con los 4 primeros
    final_states.sort(key=lambda x: x[1])
    top4 = final_states[:4]
    labels = ['Alpha', 'Bravo', 'Charlie', 'Delta']

    resultados = {}
    for label, (key, tiempo_val) in zip(labels, top4):
        # reconstruir secuencia desde prev
        seq = []
        cur = key
        while cur in prev:
            v0, s0, last0, c0, t, dur = prev[cur]
            seq.append((t, dur))
            cur = (v0, s0, last0, c0)
        seq.reverse()
        # si viniera alguna vuelta 0, se filtra igual que antes
        resultados[label] = (tiempo_val, seq)

    # 3) Global = la misma que Alpha (la más rápida de las cuatro)
    resultados['global'] = resultados['Alpha']

    # Formatear tiempos
    for k in list(resultados.keys()):
        ts, st = resultados[k]
        resultados[k] = (formatear_tiempo(ts), st)

    return resultados

@app.route('/calcular', methods=['POST'])
def calcular():
    try:
        data = request.get_json()
        NUM_LAPS = data['laps']
        PENALIZACION_PARADA = data['pitStopTime']
        PENALIZACION_PARADA_EVENTO = data.get('firstPitStopTimeEvent', PENALIZACION_PARADA)
        current_tyre = data.get('currentTyre')
        current_tyre_laps = data.get('currentTyreLaps', 0)
        already_pitted = data.get('alreadyPitted', False)
        weather = data.get('weather')

        if weather == 'rain' or weather == 'heavyrain':
            already_pitted = True

        print(f"[DEBUG] Entrada /calcular: laps={NUM_LAPS}, weather={weather}, currentTyre={current_tyre}, currentTyreLaps={current_tyre_laps}, alreadyPitted={already_pitted}")

        tiempos_prec = precalcular_tiempos(NUM_LAPS, weather, current_tyre_laps)
        #remaining = NUM_LAPS - current_tyre_laps
        remaining = NUM_LAPS
        print(f"[DEBUG] Vueltas restantes para DP: {remaining}")
        if remaining <= 0:
            print("[DEBUG] No quedan vueltas, carrera terminada")
            return jsonify({})

        inicio = perf_counter()
        dp_res = encontrar_mejores_estrategias_dp(
            remaining,
            PENALIZACION_PARADA,
            PENALIZACION_PARADA_EVENTO,
            tiempos_prec,
            already_pitted,
            current_tyre,
            current_tyre_laps
        )
        fin = perf_counter()
        print(f"[DEBUG] Resultado bruto DP_res: {dp_res}")
        print(f"[DEBUG] Tiempo DP: {fin - inicio:.4f}s")

        # Serializar para JSON
        respuesta = {}
        for paradas, (tiempo_fmt, estrat) in dp_res.items():
            print(f"[DEBUG] Serializando estrategia para {paradas} paradas: {estrat} con tiempo {tiempo_fmt}")
            visual = {"tiempo": tiempo_fmt, "estrategia": []}
            v0 = 0
            
            #if current_tyre and current_tyre_laps > 0:
            #    visual["estrategia"].append({
            #       "neumatico": current_tyre,
            #        "inicio": 0,
            #        "fin": 0
            #    })
            #    v0 = current_tyre_laps
            
            for tipo, dur in estrat:
                visual["estrategia"].append({
                    "neumatico": tipo,
                    "inicio": v0,
                    "fin": v0 + dur
                })
                v0 += dur
            respuesta[str(paradas)] = visual

        print(f"[DEBUG] Respuesta final enviada al cliente: {respuesta}")
        return jsonify(respuesta)

    except Exception as e:
        print("[DEBUG] Error en cálculo:", e)
        return jsonify({"error": str(e)}), 500

# Resto de rutas sin cambios
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/learn')
def learn():
    return render_template('learn.html')

@app.route('/circuits')
def circuits():
    return render_template('circuits.html')

@app.route('/teams')
def teams():
    return render_template('teams.html')

@app.route('/drivers')
def drivers():
    return render_template('drivers.html')

@app.route('/pagina1')
def pagina1():
    return render_template('pag1.html')

@app.route('/pagina2')
def pagina2():
    return render_template('pag2.html')

@app.route('/strategy')
def strategy():
    return render_template('strategy.html')

@app.route('/race')
def race():
    return render_template('race.html')

if __name__ == "__main__":
    app.run(debug=True)