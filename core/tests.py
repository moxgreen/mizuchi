import sqlite3
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase

from core.models import Consorzio, Giro, Persona, Ramo, Turno, TurnoProprietario


def _create_legacy_db(db_path: Path, *, include_duplicate=False):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE persona (
              id INTEGER NOT NULL,
              nome TEXT NOT NULL,
              UNIQUE (id)
            );
            CREATE TABLE giro (
              id INTEGER NOT NULL,
              ramo_bealera TEXT NOT NULL,
              tipo_giro TEXT NOT NULL,
              ordine INTEGER NOT NULL,
              id_utilizzatore INTEGER NOT NULL,
              int_tempo TIME NOT NULL,
              PRIMARY KEY (id)
            );
            CREATE TABLE ruolo (
              id INTEGER NOT NULL,
              id_giro INTEGER NOT NULL,
              id_utilizzatore INTEGER NOT NULL,
              id_utente INTEGER NOT NULL,
              intervallo_tempo TIME NOT NULL,
              ramo_bealera TEXT NOT NULL,
              PRIMARY KEY (id)
            );
            """
        )
        cur.executemany(
            "INSERT INTO persona (id, nome) VALUES (?, ?)",
            [
                (1, "Mario Rossi"),
                (2, "Luigi Bianchi"),
                (3, "Anna Verdi"),
            ],
        )

        giro_rows = [
            (10, "BOSCHETTO", "A", 30, 1, "03:00:00"),
            (11, "BOSCHETTO", "A", 60, 2, "01:30:00"),
            (12, "VARDA", "B", 40, 3, "02:00:00"),
        ]
        if include_duplicate:
            giro_rows.append((13, "BOSCHETTO", "A", 60, 3, "02:00:00"))

        cur.executemany(
            """
            INSERT INTO giro (id, ramo_bealera, tipo_giro, ordine, id_utilizzatore, int_tempo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            giro_rows,
        )

        cur.executemany(
            """
            INSERT INTO ruolo (id, id_giro, id_utilizzatore, id_utente, intervallo_tempo, ramo_bealera)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 10, 1, 1, "01:00:00", "BOSCHETTO"),
                (2, 10, 1, 2, "02:00:00", "BOSCHETTO"),
                (3, 11, 2, 2, "01:30:00", "BOSCHETTO"),
                (4, 12, 3, 3, "02:00:00", "VARDA"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


class ImportChiamognaCommandTests(TestCase):
    def test_imports_legacy_data_and_durations_match(self):
        Persona.objects.create(nome="to-delete", cognome="to-delete")

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "legacy.sqlite3"
            _create_legacy_db(source)

            out = StringIO()
            call_command("import_chiamogna", source=str(source), stdout=out)

        self.assertEqual(Consorzio.objects.count(), 1)
        self.assertEqual(Consorzio.objects.first().nome, "Chiamogna")
        self.assertEqual(Persona.objects.count(), 3)
        self.assertEqual(Ramo.objects.count(), 2)
        self.assertEqual(Giro.objects.count(), 2)
        self.assertEqual(Turno.objects.count(), 3)
        self.assertEqual(TurnoProprietario.objects.count(), 4)

        self.assertFalse(Persona.objects.filter(cognome="to-delete").exists())
        self.assertFalse(Persona.objects.exclude(nome="-").exists())

        self.assertFalse(Turno.objects.filter(turnoproprietario__isnull=True).exists())

        for turno in Turno.objects.all():
            total = turno.turnoproprietario_set.aggregate(total=Sum("tempo"))["total"]
            self.assertEqual(turno.durata, total)

    def test_remaps_duplicate_target_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "legacy.sqlite3"
            _create_legacy_db(source, include_duplicate=True)

            call_command("import_chiamogna", source=str(source))

        giro = Giro.objects.get(ramo__nome="BOSCHETTO", nome="Giro A")
        ordini = list(
            Turno.objects.filter(giro=giro).order_by("ordine").values_list("ordine", flat=True)
        )
        self.assertEqual(ordini, [30, 60, 61])

    def test_missing_source_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("import_chiamogna", source="/tmp/definitely-missing-file.sqlite3")
