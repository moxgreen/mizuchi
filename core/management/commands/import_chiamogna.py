from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from core.models import Consorzio, Giro, Persona, Ramo, Turno, TurnoProprietario


_TIME_RE = re.compile(r"^(?P<hours>\d+):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d)$")


def _parse_hhmmss(raw: str, *, context: str) -> timedelta:
    match = _TIME_RE.match((raw or "").strip())
    if not match:
        raise CommandError(f"Invalid time format '{raw}' for {context}. Expected HH:MM:SS.")

    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


class Command(BaseCommand):
    help = "Import legacy chiamogna.sqlite3 data into current Django models."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="old_data/chiamogna.sqlite3",
            help="Path to source legacy sqlite database.",
        )
        parser.add_argument(
            "--consorzio-name",
            default="Chiamogna",
            help="Consorzio name to use/create for imported records.",
        )
        parser.add_argument(
            "--no-reset",
            action="store_true",
            help="Do not delete existing core data before import.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.is_absolute():
            source = Path(settings.BASE_DIR) / source

        if not source.exists() or not source.is_file():
            raise CommandError(f"Source database not found: {source}")

        consorzio_name = options["consorzio_name"].strip()
        if not consorzio_name:
            raise CommandError("--consorzio-name cannot be empty")

        reset = not options["no_reset"]

        conn = sqlite3.connect(source)
        conn.row_factory = sqlite3.Row

        try:
            persone_rows = conn.execute("SELECT id, nome FROM persona ORDER BY id").fetchall()
            giro_rows = conn.execute(
                """
                SELECT id, ramo_bealera, tipo_giro, ordine, id_utilizzatore, int_tempo
                FROM giro
                ORDER BY id
                """
            ).fetchall()
            ruolo_rows = conn.execute(
                """
                SELECT id, id_giro, id_utente, intervallo_tempo
                FROM ruolo
                ORDER BY id
                """
            ).fetchall()

            with transaction.atomic():
                if reset:
                    self.stdout.write("Reset enabled: deleting existing core data...")
                    TurnoProprietario.objects.all().delete()
                    Turno.objects.all().delete()
                    Giro.objects.all().delete()
                    Ramo.objects.all().delete()
                    Consorzio.objects.all().delete()
                    Persona.objects.all().delete()

                consorzio, _ = Consorzio.objects.get_or_create(
                    nome=consorzio_name,
                    defaults={"descrizione": "Import legacy chiamogna.sqlite3"},
                )

                legacy_persona_to_new: dict[int, Persona] = {}
                persone_created = 0
                for row in persone_rows:
                    legacy_id = int(row["id"])
                    cognome = (row["nome"] or "").strip() or "-"
                    persona = Persona.objects.create(nome="-", cognome=cognome)
                    legacy_persona_to_new[legacy_id] = persona
                    persone_created += 1

                tz = timezone.get_current_timezone()
                inizio_astratto = timezone.make_aware(datetime(2000, 1, 1, 0, 0, 0), tz)

                ramo_map: dict[str, Ramo] = {}
                ramo_names = sorted({str(row["ramo_bealera"]).strip() for row in giro_rows})
                rami_created = 0
                for ramo_name in ramo_names:
                    ramo = Ramo.objects.create(
                        nome=ramo_name,
                        descrizione="",
                        consorzio=consorzio,
                        inizio_astratto=inizio_astratto,
                    )
                    ramo_map[ramo_name] = ramo
                    rami_created += 1

                giro_map: dict[tuple[str, str], Giro] = {}
                giri_created = 0
                tipo_order_fallback = 3
                for ramo_name in ramo_names:
                    tipi = sorted(
                        {
                            str(row["tipo_giro"]).strip()
                            for row in giro_rows
                            if str(row["ramo_bealera"]).strip() == ramo_name
                        }
                    )
                    for tipo in tipi:
                        if tipo == "A":
                            ordine = 1
                        elif tipo == "B":
                            ordine = 2
                        else:
                            ordine = tipo_order_fallback
                            tipo_order_fallback += 1

                        giro = Giro.objects.create(
                            nome=f"Giro {tipo}",
                            ordine=ordine,
                            descrizione=(
                                f"Import legacy: ramo_bealera={ramo_name}, tipo_giro={tipo}"
                            ),
                            ramo=ramo_map[ramo_name],
                        )
                        giro_map[(ramo_name, tipo)] = giro
                        giri_created += 1

                legacy_giro_to_turno: dict[int, Turno] = {}
                turni_created = 0
                skipped_missing_utilizzatore = 0
                skipped_missing_giro_key = 0
                remapped_duplicate_ordine = 0
                remapped_examples: list[str] = []
                used_ordini_by_giro: dict[int, set[int]] = {}
                for row in giro_rows:
                    legacy_giro_id = int(row["id"])
                    ramo_name = str(row["ramo_bealera"]).strip()
                    tipo = str(row["tipo_giro"]).strip()
                    requested_ordine = int(row["ordine"])
                    legacy_utilizzatore_id = int(row["id_utilizzatore"])

                    utilizzatore = legacy_persona_to_new.get(legacy_utilizzatore_id)
                    if not utilizzatore:
                        skipped_missing_utilizzatore += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"Skipping legacy giro id={legacy_giro_id}: missing persona id={legacy_utilizzatore_id}"
                            )
                        )
                        continue

                    giro = giro_map.get((ramo_name, tipo))
                    if not giro:
                        skipped_missing_giro_key += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"Skipping legacy giro id={legacy_giro_id}: missing giro key ({ramo_name}, {tipo})"
                            )
                        )
                        continue

                    used_ordini = used_ordini_by_giro.setdefault(giro.pk, set())
                    ordine = requested_ordine
                    while ordine in used_ordini:
                        ordine += 1
                    if ordine != requested_ordine:
                        remapped_duplicate_ordine += 1
                        remapped_examples.append(
                            f"legacy_giro_id={legacy_giro_id} ({ramo_name}/{tipo}): {requested_ordine}->{ordine}"
                        )
                    used_ordini.add(ordine)

                    turno = Turno.objects.create(
                        utilizzatore=utilizzatore,
                        ordine=ordine,
                        giro=giro,
                    )
                    legacy_giro_to_turno[legacy_giro_id] = turno
                    turni_created += 1

                turnoproprietari_created = 0
                skipped_missing_turno = 0
                skipped_missing_proprietario = 0
                for row in ruolo_rows:
                    ruolo_id = int(row["id"])
                    legacy_giro_id = int(row["id_giro"])
                    legacy_proprietario_id = int(row["id_utente"])
                    tempo = _parse_hhmmss(
                        str(row["intervallo_tempo"]),
                        context=f"ruolo id={ruolo_id}",
                    )

                    turno = legacy_giro_to_turno.get(legacy_giro_id)
                    if not turno:
                        skipped_missing_turno += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"Skipping ruolo id={ruolo_id}: missing imported turno for legacy giro id={legacy_giro_id}"
                            )
                        )
                        continue

                    proprietario = legacy_persona_to_new.get(legacy_proprietario_id)
                    if not proprietario:
                        skipped_missing_proprietario += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"Skipping ruolo id={ruolo_id}: missing persona id={legacy_proprietario_id}"
                            )
                        )
                        continue

                    TurnoProprietario.objects.create(
                        turno=turno,
                        proprietario=proprietario,
                        tempo=tempo,
                    )
                    turnoproprietari_created += 1

                turni_without_owner = Turno.objects.filter(turnoproprietario__isnull=True).count()

                self.stdout.write(self.style.SUCCESS("Import completed."))
                self.stdout.write("Imported counts:")
                self.stdout.write(f"- Persona: {persone_created}")
                self.stdout.write(f"- Consorzio: {1 if consorzio else 0}")
                self.stdout.write(f"- Ramo: {rami_created}")
                self.stdout.write(f"- Giro: {giri_created}")
                self.stdout.write(f"- Turno: {turni_created}")
                self.stdout.write(f"- TurnoProprietario: {turnoproprietari_created}")

                self.stdout.write("Warnings/skips:")
                self.stdout.write(f"- Missing utilizzatore persona: {skipped_missing_utilizzatore}")
                self.stdout.write(f"- Missing giro key: {skipped_missing_giro_key}")
                self.stdout.write(f"- Missing imported turno: {skipped_missing_turno}")
                self.stdout.write(f"- Missing proprietario persona: {skipped_missing_proprietario}")
                self.stdout.write(f"- Duplicate ordini remapped: {remapped_duplicate_ordine}")
                if remapped_examples:
                    self.stdout.write("- Duplicate ordine examples:")
                    for example in remapped_examples:
                        self.stdout.write(f"  - {example}\n")
                self.stdout.write(f"- Turni without proprietario: {turni_without_owner}")

                mismatched_durata = (
                    Turno.objects.annotate(total=Sum("turnoproprietario__tempo"))
                    .exclude(durata=F("total"))
                    .count()
                )
                self.stdout.write(f"- Turni with durata mismatch: {mismatched_durata}")
        finally:
            conn.close()
