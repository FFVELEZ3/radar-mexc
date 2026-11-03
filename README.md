# Radar MEXC

Panel web, alertas por Telegram y bot de operación automática para futuros de MEXC.
Cada 15 minutos analiza los 10 perpetuos USDT con más volumen, muestra qué tan cerca
está cada par de una señal, sigue cada señal hasta el objetivo o el stop y, cuando
hay evidencia suficiente, opera solo en tu cuenta con frenos de seguridad.

Todo corre gratis en GitHub; tu PC puede estar apagada.

## Cómo protege tu dinero

El bot arranca en **modo automático**, que funciona así:

1. **Papel primero.** Cada señal se sigue sin dinero real hasta que haya al menos
   30 señales cerradas.
2. **Pasa a real solo con evidencia.** Si esas señales en papel ganan en promedio,
   empieza a operar con dinero real. Si no, sigue en papel indefinidamente.
3. **Vuelve a papel si se deteriora.** Si las últimas 20 señales cerradas pierden en
   promedio, deja de usar dinero real hasta que se recuperen.

Y en real, antes de cada orden revisa estos frenos:

| Freno | Valor por defecto |
|---|---|
| Pérdida si toca el stop | $1 por operación |
| Posiciones abiertas a la vez | máximo 2, y una sola por par |
| Pérdida máxima del día | $3 (cuenta lo perdido + el peor caso de lo abierto) |
| Pérdida máxima del mes | $10 |
| Apalancamiento | 3x con margen aislado |
| Precio alejado de la entrada | no entra si se movió más de 0.5 ATR |
| Mínimo del contrato | no entra si obligaría a arriesgar más de tu $1 |

Cada orden lleva su stop loss y take profit como órdenes en MEXC desde el primer
momento. Si una operación cumple 48 horas sin tocar ninguno, el bot la cierra.

Nada de esto garantiza ganancias: limita cuánto puedes perder y solo arriesga
dinero cuando los resultados lo respaldan.

## Qué verás en el panel

- **Indicadores:** señales activas, resultado acumulado, estrategias con ventaja y
  tendencia del mercado.
- **Bot automático:** si está en papel o en real y por qué, avance hacia las 30
  señales, resultado real del día y del mes frente a sus frenos.
- **Señales activas:** entrada, stop, objetivo, posición del precio y si es REAL o PAPEL.
- **Radar:** los 10 pares ordenados por cercanía a una señal.
- **Detalle del par:** gráfico de 7 días con EMAs y entradas históricas, y la
  lista de condiciones de cada estrategia con ✓.
- **Pestañas:** historial de señales, operaciones reales en MEXC, backtest y método.

En el celular, ábrelo en el navegador y usa **Agregar a pantalla de inicio**.

---

## Instalación (unos 30 minutos, mejor desde la PC)

### 1. Bot de Telegram

1. En Telegram busca **@BotFather**, escribe `/newbot` y sigue los pasos. Guarda el **token**.
2. Escríbele cualquier mensaje a tu bot nuevo.
3. Abre `https://api.telegram.org/botTU_TOKEN/getUpdates` (con tu token) y copia el
   número que sigue a `"chat":{"id":`. Ese es tu **chat ID**.

### 2. Repositorio en GitHub

1. Crea una cuenta gratuita en github.com.
2. **New repository** → nombre `radar-mexc` → **Public** → **Create repository**.
   Tiene que ser público para que el panel y la ejecución cada 15 minutos sean gratis.
3. **uploading an existing file** → arrastra **todo el contenido** de esta carpeta
   (incluidas `.github` y `docs`) → **Commit changes**.
   En Mac, `.github` viene oculta: si no se sube, créala con **Add file → Create new
   file**, nombre `.github/workflows/senales.yml`, y pega su contenido.

**Qué es público:** el código, el panel y los registros de ejecución. Cualquiera con
el enlace puede ver las señales y los resultados de tus operaciones en dólares. Tu
saldo y tus claves nunca se publican: las claves quedan cifradas como secretos.

### 3. Secretos de Telegram

**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
|---|---|
| `TELEGRAM_TOKEN` | el token de BotFather |
| `TELEGRAM_CHAT_ID` | tu chat ID |

### 4. Panel

**Settings → Pages** → *Source*: **Deploy from a branch** → rama `main`, carpeta
`/docs` → **Save**. Tu panel queda en `https://TU_USUARIO.github.io/radar-mexc/`.

### 5. Primera ejecución

1. Pestaña **Actions** → si lo pide, habilita los workflows.
2. **Radar MEXC** → **Run workflow** → modo `prueba`. Te llega un mensaje a Telegram.
3. Corre otra vez en modo `senales`. En 2 o 3 minutos el panel se llena.

Desde aquí ya funciona en papel. El paso 6 conecta tu cuenta para que pueda operar
en real cuando tenga evidencia.

### 6. Clave de API de MEXC (para operar en real)

1. En MEXC completa la verificación **KYC** si no la tienes.
2. **Futuros → Configuración**: deja la cuenta en modo **Simple** (no Unificado). En
   modo Unificado MEXC no acepta margen aislado y el bot no podría abrir órdenes.
3. **Perfil → Gestión de API → Crear API**:
   - Marca **solo** los permisos de **Futuros** (lectura y trading).
   - **Nunca** marques retiros ni transferencias.
   - No vincules una IP: GitHub cambia de IP en cada ejecución. Si MEXC indica que la
     clave vence, anota la fecha para renovarla.
4. Copia la **Access Key** y la **Secret Key**.
5. En GitHub, crea dos secretos más:

| Nombre | Valor |
|---|---|
| `MEXC_API_KEY` | Access Key |
| `MEXC_API_SECRET` | Secret Key |

6. Pasa a la billetera de **Futuros** solo el dinero que aceptas arriesgar. El bot
   nunca usa más margen del que haya ahí.

### 7. Ajustes (opcional)

**Settings → Secrets and variables → Actions → Variables**:

| Variable | Qué hace | Por defecto |
|---|---|---|
| `MODO` | `auto`, `simulado` (solo papel), `real` (siempre real) o `apagado` | `auto` |
| `RIESGO_POR_OPERACION_USD` | Pérdida si toca el stop | `1` |
| `APALANCAMIENTO` | Apalancamiento con margen aislado | `3` |
| `MAX_POSICIONES` | Posiciones reales abiertas a la vez | `2` |
| `LIMITE_PERDIDA_DIARIA` | Freno diario en USD | `3` |
| `LIMITE_PERDIDA_MENSUAL` | Freno mensual en USD | `10` |
| `NUM_PARES` | Pares de mayor volumen a vigilar | `10` |
| `MIN_T` | Exigencia del filtro estadístico | `2` |
| `HORA_RESUMEN` | Hora de Ecuador del resumen diario | `8` |

**Para detener el bot de inmediato:** crea la variable `MODO` con valor `apagado`.
Las posiciones ya abiertas conservan su stop y objetivo en MEXC.

---

## Alertas de Telegram

- Señal nueva, indicando si se sigue en papel o si el bot la abrirá en real.
- Orden real abierta, con contratos, entrada, stop, objetivo, margen y riesgo.
- Señal que el bot decidió no abrir en real, con el freno que la detuvo.
- Cierre de cada señal y de cada operación real, con el resultado.
- Cambio de modo (papel ↔ real), resumen diario y fallas (máximo una cada 3 horas).

---

## Cómo decide

**Estrategias** (1h, siempre a favor de la tendencia de 4h):

| Estrategia | Long cuando… | Short cuando… |
|---|---|---|
| Retroceso en tendencia | 4h alcista, el precio retrocede a la EMA20 y cierra sobre el máximo previo | espejo en tendencia bajista |
| Ruptura de rango | cierra sobre el máximo de 20 velas con ADX > 20 | cierra bajo el mínimo de 20 velas |
| Rebote de RSI | 4h alcista y el RSI sale de sobreventa (cruza 35 al alza) | 4h bajista y el RSI cruza 65 a la baja |

**Stop y objetivo:** stop a 1.5 × ATR(14); objetivo al doble de esa distancia; cierre
a las 48 h si no toca ninguno.

**Costos:** desde el 1 de junio de 2026 MEXC cobra 0.08 % taker en las órdenes de
futuros enviadas por API. El backtest usa ese valor más 0.03 % de deslizamiento por
lado, y si en una vela se tocan stop y objetivo cuenta la pérdida.

**Filtro:** solo hay señal si la combinación tiene, en el último año, al menos 30
operaciones, gana en el primer 70 % y en el 30 % más reciente, factor de beneficio
≥ 1.15 y estadístico t ≥ 2. Con precios aleatorios, solo el 0.6 % pasa.

---

## Límites

- El pasado no garantiza el futuro; los frenos acotan la pérdida, no la eliminan.
- Un hueco brusco de precio puede ejecutar el stop peor de lo previsto.
- GitHub puede retrasar las ejecuciones 5 a 20 minutos. Por eso el stop y el objetivo
  viven en MEXC desde que se abre la orden, y el bot no entra si el precio ya se movió.
- Si MEXC bloquea las consultas desde GitHub o rechaza una orden, recibes el aviso con
  el motivo.

## En tu PC (opcional)

```bash
pip install -r requirements.txt
python main.py backtest            # reporte de todas las combinaciones
python -m tests.test_motor         # pruebas del motor
python -m tests.test_ejecutor      # pruebas del bot con un MEXC simulado
python -m tests.demo               # datos de demostración para ver el panel
```

Herramienta de análisis y ejecución, no asesoría financiera. Opera solo con dinero
que puedas perder.
