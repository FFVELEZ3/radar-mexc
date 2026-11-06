"""Configuración del sistema de señales.

Cada valor se puede cambiar sin tocar el código, creando una variable con el
mismo nombre en GitHub (Settings > Secrets and variables > Actions > Variables).
"""
import os


def _num(nombre, defecto):
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return defecto
    try:
        return type(defecto)(float(valor))
    except ValueError:
        return defecto


# --- Mercado ---
NUM_PARES = _num("NUM_PARES", 20)              # pares de mayor volumen a vigilar
DIAS_HISTORIA = _num("DIAS_HISTORIA", 365)     # historial para el backtest
EXCLUIR = [s.strip().upper() for s in os.getenv("EXCLUIR", "USDC_USDT").split(",") if s.strip()]

# --- Costos (MEXC futuros USDT-M, orden a mercado = taker) ---
# Las señales las ejecuta Freddy a mano desde la app: la tarifa estándar de taker en
# futuros USDT-M es 0.04 % por lado (algunas fuentes y promociones dan 0.02 %; se usa la
# más alta). Las órdenes por API pagan 0.08 % desde el 1/6/2026: eso solo aplica al bot
# automático (ejecutor.py usa COMISION_API).
COMISION_TAKER = _num("COMISION_TAKER", 0.0004)   # 0.04 % por lado, operación manual
COMISION_API = _num("COMISION_API", 0.0008)       # 0.08 % por lado, órdenes por API
DESLIZAMIENTO = _num("DESLIZAMIENTO", 0.0003)     # 0.03 % por lado, prudente

# --- Gestión de la operación ---
ATR_STOP = _num("ATR_STOP", 1.5)          # stop = 1.5 x ATR(14)
RATIO_BENEFICIO = _num("RATIO_BENEFICIO", 2.0)  # take profit = 2 x distancia del stop (modo "fija")
# "escalonada": TP1 1R (50 %) → stop a la entrada, TP2 2R (30 %), TP3 3R (20 %) · "fija": un objetivo
# "auto": cada estrategia usa la que mejor funcionó en el 70 % antiguo del historial
GESTION = os.getenv("GESTION", "auto").strip().lower() or "auto"
VELAS_MAXIMAS = _num("VELAS_MAXIMAS", 48)  # cierre por tiempo: 48 velas de 1h
VELAS_MAXIMAS_TENDENCIA = _num("VELAS_MAXIMAS_TENDENCIA", 120)  # modo tendencia: hasta 5 días

# --- Tamaño de posición ---
RIESGO_POR_OPERACION_USD = _num("RIESGO_POR_OPERACION_USD", 1.0)  # pérdida si toca el stop
APALANCAMIENTO = _num("APALANCAMIENTO", 3)

# --- Operación automática ---
# apagado  = no opera; simulado = solo en papel;
# auto     = papel hasta que el historial demuestre ventaja, luego real (recomendado);
# real     = opera siempre en real (los frenos de abajo siguen activos).
MODO = os.getenv("MODO", "auto").strip().lower() or "auto"
# Seguro principal: mientras no sea "si", el bot NUNCA envía órdenes a MEXC aunque la clave
# lo permita; solo lee saldo y posiciones (modo "solo lectura").
PERMITIR_ORDENES = os.getenv("PERMITIR_ORDENES", "no").strip().lower() in ("si", "sí", "1", "true", "yes")
MIN_SENALES_PARA_REAL = _num("MIN_SENALES_PARA_REAL", 30)  # cerradas en papel
VENTANA_PAUSA = 20               # si las últimas 20 cerradas pierden en promedio, vuelve a papel
MAX_POSICIONES = _num("MAX_POSICIONES", 2)
LIMITE_PERDIDA_DIARIA = _num("LIMITE_PERDIDA_DIARIA", 3.0)    # USD
LIMITE_PERDIDA_MENSUAL = _num("LIMITE_PERDIDA_MENSUAL", 10.0)  # USD

# --- Filtro de calidad: solo se envían señales con ventaja comprobada ---
MIN_OPERACIONES = _num("MIN_OPERACIONES", 30)        # en todo el historial
MIN_OPERACIONES_OOS = _num("MIN_OPERACIONES_OOS", 8)  # en el tramo fuera de muestra
MIN_FACTOR_BENEFICIO = _num("MIN_FACTOR_BENEFICIO", 1.15)
# Estadístico t de la expectativa: con 2.0, solo ~0.6 % de estrategias sobre
# precios aleatorios pasan el filtro (medido con 180 simulaciones).
MIN_T = _num("MIN_T", 2.0)
# Nivel "candidata": una estrategia que no pasa par por par (pocas operaciones por par) pero
# gana sumando todos los pares con t >= 3, y es positiva en la parte antigua y en la reciente.
# Sus señales se avisan por Telegram marcadas como "en validación" y se siguen en papel.
MIN_T_CONJUNTO_CANDIDATA = _num("MIN_T_CONJUNTO_CANDIDATA", 3.0)
MIN_OPS_CONJUNTO_CANDIDATA = _num("MIN_OPS_CONJUNTO_CANDIDATA", 200)
FRACCION_EN_MUESTRA = 0.70  # 70 % del historial para evaluar, 30 % para confirmar

# --- Panel ---
INTERVALO_MIN = _num("INTERVALO_MIN", 5)  # minutos entre análisis (modo continuo)
DIR_DATOS = os.getenv("DIR_DATOS", "docs/data")

# --- Avisos ---
ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Guayaquil")
HORA_RESUMEN = _num("HORA_RESUMEN", 8)   # hora local del resumen diario
# Avisar también los setups SIN ventaja comprobada (solo para estudiar, marcados como tales)
# Avisos de "setup formándose" (a una condición de completarse). Apagados: Freddy solo quiere entradas reales.
PREAVISOS = os.getenv("PREAVISOS", "no").strip().lower() in ("si", "sí", "1", "true", "yes")
AVISAR_OBSERVACION = os.getenv("AVISAR_OBSERVACION", "no").strip().lower() in ("si", "sí", "1", "true", "yes")
MAX_DISTANCIA_ATR = 0.5  # si el precio se alejó más de 0.5 ATR de la entrada, no entrar
