"""Pruebas del gate calendario-driven del orquestador automático."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import auto_update
from scripts.auto_update import (
    alertar_ciclo,
    cl_pendientes,
    rut_cuerpo,
    xbrl_max_periodo,
)


class CursorFalso:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class ConexionFalsa:
    def __init__(self, rows):
        self.cursor_falso = CursorFalso(rows)

    def cursor(self):
        return self.cursor_falso


class GateChileTest(unittest.TestCase):
    def test_pendiente_es_persistente_y_ordenado(self):
        conn = ConexionFalsa([("11111111-1",), (None,), ("22222222-2",)])

        self.assertEqual(cl_pendientes(conn), ["11111111-1", "22222222-2"])
        sql = conn.cursor_falso.sql
        self.assertIn("publication_date <= CURRENT_DATE", sql)
        self.assertIn("make_date(rpd.period_year, rpd.period_quarter * 3, 1)", sql)
        self.assertNotIn("CURRENT_DATE -", sql)
        self.assertIn("period_year * 10 + rpd.period_quarter", sql)
        self.assertIn("MAX(fd.period_year * 10 + fd.period_quarter)", sql)
        self.assertIsNone(conn.cursor_falso.params)

    def test_excluye_emisores_nunca_procesados(self):
        conn = ConexionFalsa([])

        self.assertEqual(cl_pendientes(conn), [])
        self.assertIn("EXISTS (SELECT 1 FROM financial_data f2", conn.cursor_falso.sql)

    def test_rut_del_pipeline_excluye_digito_verificador(self):
        self.assertEqual(rut_cuerpo("90.299.000-3"), "90299000")
        self.assertEqual(rut_cuerpo("96689310-9"), "96689310")

    def test_xbrl_max_periodo_ignora_archivos_no_trimestrales(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            company = root / "data" / "XBRL" / "Total" / "96689310-9_TRANSBANK"
            (company / "Estados_financieros_(XBRL)96689310_202509_extracted").mkdir(parents=True)
            (company / "Estados_financieros_(XBRL)96689310_202510_extracted").mkdir()
            with patch("scripts.auto_update.CMF", root):
                self.assertEqual(xbrl_max_periodo("96689310-9"), 20253)

    def test_xbrl_max_periodo_sin_descarga_es_cero(self):
        with TemporaryDirectory() as tmp, patch("scripts.auto_update.CMF", Path(tmp)):
            self.assertEqual(xbrl_max_periodo("11111111-1"), 0)


class AlertaBackupTest(unittest.TestCase):
    """El backup a Drive falló los ciclos del 24 y 25 de julio de 2026 y no salió una sola
    alerta: `alertar_ciclo` lo descartaba por best-effort sin mirar si se repetía."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parche = patch("scripts.auto_update.RACHA_BACKUP",
                       Path(self.tmp.name) / "logs" / ".backup_fallos_seguidos")
        parche.start()
        self.addCleanup(parche.stop)

    def _ciclo(self, *lineas):
        """Corre un ciclo con esas líneas de log y devuelve el correo enviado, o None."""
        enviados = []
        with patch.object(auto_update, "_BUF", list(lineas)), \
             patch.object(auto_update, "enviar_correo",
                          lambda asunto, cuerpo: enviados.append((asunto, cuerpo))):
            alertar_ciclo(1.0, live=True)
        return enviados[0] if enviados else None

    FALLO = "[t] ✗ backup a Drive rc=1: ERROR en sync de XBRL"
    OK = "[t] ✓ backup a Drive"

    def test_un_fallo_suelto_no_manda_correo(self):
        """Un 403 aislado de Google no merece un correo: esa parte del diseño se conserva."""
        self.assertIsNone(self._ciclo(self.FALLO))

    def test_dos_ciclos_seguidos_fallando_si_avisan(self):
        self._ciclo(self.FALLO)
        correo = self._ciclo(self.FALLO)
        self.assertIsNotNone(correo)
        asunto, cuerpo = correo
        self.assertIn("backup caído", asunto)
        self.assertIn("2 ciclos", asunto)
        self.assertIn("FALLANDO hace 2 ciclos seguidos", cuerpo)

    def test_un_backup_exitoso_reinicia_la_racha(self):
        self._ciclo(self.FALLO)
        self._ciclo(self.OK)
        self.assertIsNone(self._ciclo(self.FALLO))

    def test_la_racha_sobrevive_al_reinicio_del_contenedor(self):
        """Se persiste en archivo justamente porque el proceso no dura entre ciclos si el
        contenedor se reinicia; en memoria la racha se perdía y nunca llegaba al umbral."""
        self._ciclo(self.FALLO)
        self.assertEqual(auto_update.RACHA_BACKUP.read_text(), "1")

    def test_el_dry_run_no_toca_la_racha(self):
        with patch.object(auto_update, "_BUF", [self.FALLO]):
            alertar_ciclo(1.0, live=False)
        self.assertFalse(auto_update.RACHA_BACKUP.exists())


if __name__ == "__main__":
    unittest.main()
