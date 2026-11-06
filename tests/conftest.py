"""Se carga antes que cualquier prueba: los datos van a una carpeta temporal,
nunca a docs/data (los datos reales del radar)."""
import os
import tempfile

os.environ["DIR_DATOS"] = tempfile.mkdtemp(prefix="radar-pruebas-")
os.environ.setdefault("COMISION_TAKER", "0.0008")  # las pruebas usan costos fijos
