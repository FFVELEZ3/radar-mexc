"""Gestión de la salida de una operación, igual para el backtest, el seguimiento y el bot.

Modo "escalonada" (como los analistas profesionales, pero con buen riesgo/beneficio):
  TP1 a 1R cierra el 50 %  → el stop pasa a la entrada (cubriendo comisiones)
  TP2 a 2R cierra el 30 %
  TP3 a 3R cierra el 20 % restante
Modo "fija": un solo objetivo a RATIO_BENEFICIO x riesgo.

Supuestos prudentes, vela por vela:
- Si la vela abre más allá del stop (hueco), se sale a la apertura.
- Si en la misma vela se tocan el stop y un objetivo, se asume primero el stop.
- Si en la vela en que se toca un objetivo el precio también vuelve al nuevo stop
  (entrada), se asume que lo tocó: no se le da al sistema el beneficio de la duda.
"""
import config as C

COSTO_LADO = C.COMISION_TAKER + C.DESLIZAMIENTO


def tramos(modo=None):
    if (modo or C.GESTION) == "fija":  # "auto" sin decidir aún: se muestra la escalonada
        return [(float(C.RATIO_BENEFICIO), 1.0)]
    return [(1.0, 0.5), (2.0, 0.3), (3.0, 0.2)]


def objetivos(lado, entrada, riesgo, modo=None):
    return [entrada + lado * r * riesgo for r, _ in tramos(modo)]


def stop_protegido(lado, entrada):
    """Stop en la entrada más lo justo para pagar las comisiones de entrada y salida."""
    return entrada + lado * COSTO_LADO * 2 * entrada


class Posicion:
    def __init__(self, lado, entrada, stop, riesgo, modo=None):
        self.lado, self.entrada, self.riesgo = lado, entrada, riesgo
        self.stop_inicial = self.stop = stop
        self.objetivos = objetivos(lado, entrada, riesgo, modo)
        self.fracciones = [f for _, f in tramos(modo)]
        self.hechos = 0          # objetivos alcanzados
        self.abierta = 1.0       # fracción todavía abierta
        self.bruto = 0.0         # resultado en precio, ponderado por fracción
        self.costos = COSTO_LADO * entrada
        self.velas = 0
        self.motivo = None
        self.salida_media = None
        self._suma_salidas = 0.0

    def _cerrar(self, fraccion, precio):
        self.bruto += fraccion * self.lado * (precio - self.entrada)
        self.costos += COSTO_LADO * precio * fraccion
        self._suma_salidas += fraccion * precio
        self.abierta -= fraccion
        if self.abierta <= 1e-9:
            self.abierta = 0.0
            self.salida_media = self._suma_salidas

    def _contra(self, precio):     # ¿el precio está en o más allá del stop?
        return self.lado * (precio - self.stop) <= 0

    def vela(self, o, h, l, c):
        """Procesa una vela. Devuelve True si la operación quedó cerrada."""
        if not self.abierta:
            return True
        primera = self.velas == 0
        self.velas += 1
        malo, bueno = (l, h) if self.lado == 1 else (h, l)
        if not primera and self._contra(o):
            self._cerrar(self.abierta, o)
            self.motivo = "protegida" if self.hechos else "stop"
            return True
        if self._contra(malo):
            self._cerrar(self.abierta, self.stop)
            self.motivo = "protegida" if self.hechos else "stop"
            return True
        while self.hechos < len(self.objetivos) and self.lado * (bueno - self.objetivos[self.hechos]) >= 0:
            frac = self.fracciones[self.hechos] if self.hechos < len(self.objetivos) - 1 else self.abierta
            self._cerrar(min(frac, self.abierta), self.objetivos[self.hechos])
            self.hechos += 1
            if self.hechos == 1 and len(self.objetivos) > 1:
                self.stop = stop_protegido(self.lado, self.entrada)
        if not self.abierta:
            self.motivo = "objetivo"
            return True
        if self.hechos and self._contra(malo):
            self._cerrar(self.abierta, self.stop)
            self.motivo = "protegida"
            return True
        if self.velas >= C.VELAS_MAXIMAS:
            self._cerrar(self.abierta, c)
            self.motivo = "tiempo"
            return True
        return False

    def r(self, precio_actual=None):
        """Resultado en R: realizado + lo abierto valorado a precio_actual (si se da)."""
        bruto, costos = self.bruto, self.costos
        if self.abierta and precio_actual is not None:
            bruto += self.abierta * self.lado * (precio_actual - self.entrada)
            costos += COSTO_LADO * precio_actual * self.abierta
        return (bruto - costos) / self.riesgo


def r_si_llega(lado, entrada, stop, riesgo, k, modo=None):
    """R neto si el precio llega al objetivo k (0 = TP1) y después vuelve al stop vigente."""
    p = Posicion(lado, entrada, stop, riesgo, modo)
    obj = p.objetivos[k]
    p.vela(entrada, max(entrada, obj), min(entrada, obj), obj)
    if p.abierta:
        p._cerrar(p.abierta, p.stop)
    return p.r()


def apalancamiento_max(distancia_stop, margen_mant=0.005):
    """Apalancamiento con el que la liquidación queda bastante más lejos que el stop."""
    return max(1, int(1 / (distancia_stop / 0.7 + margen_mant)))
