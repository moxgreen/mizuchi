import logging
from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from .fields import DurationHHMMField

# Create your models here.
class Persona(models.Model):
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    telefono = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    indirizzo = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Persone"

    def __str__(self):
        return f"{self.nome} {self.cognome}"

class Consorzio(models.Model):
    nome = models.CharField(max_length=100)
    descrizione = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Consorzi"
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Ramo(models.Model):
    nome = models.CharField(max_length=100)
    descrizione = models.TextField(blank=True, null=True)
    consorzio = models.ForeignKey(Consorzio, on_delete=models.CASCADE, related_name='rami')
    
    # CONVENZIONE: L'anno salvato sarà sempre il 2000 (che è bisestile)
    # Esempio salvato nel DB: 2000-05-15 08:30:00
    inizio_astratto = models.DateTimeField(
        help_text="Inserisci giorno e ora. L'anno verrà ignorato (sarà salvato come 2000)."
    )

    class Meta:
        verbose_name_plural = "Rami"
        ordering = ['consorzio', 'nome']

    def __str__(self):
        return self.nome
    
class Giro(models.Model):
    nome = models.CharField(max_length=100)
    ordine = models.IntegerField()
    descrizione = models.TextField(blank=True, null=True)
    ramo = models.ForeignKey(Ramo, on_delete=models.CASCADE, related_name='giri')

    class Meta:
        verbose_name_plural = "Giri"
        ordering = ['ramo', 'nome']

    def __str__(self):
        return f"{self.ramo.consorzio.nome} - {self.ramo.nome} - {self.nome}"
    
class Turno(models.Model):
    utilizzatore = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name='turni_utilizzatore')
    proprietari = models.ManyToManyField(Persona, related_name='turni_proprietario', through='TurnoProprietario')
    durata = DurationHHMMField(editable=False, default=timedelta(0))
    ordine = models.IntegerField()
    giro = models.ForeignKey(Giro, on_delete=models.CASCADE, related_name='turni')

    class Meta:
        verbose_name_plural = "Turni"
        ordering = ['giro', 'ordine']
        unique_together = [['giro', 'ordine']]

    def __str__(self):
        return f"Turno {self.ordine} - {self.utilizzatore.nome} ({self.durata})"
    
    def clean(self):
        """Valida che il turno abbia almeno un proprietario"""
        super().clean()
        if self.pk:  # Solo se l'oggetto esiste già nel DB
            if not self.turnoproprietario_set.exists():
                raise ValidationError("Un turno deve avere almeno un proprietario con tempo allocato.")
    
    def ricalcola_durata(self):
        """Ricalcola e aggiorna la durata del turno sommando i tempi allocati dei proprietari"""
        total_durata = self.turnoproprietario_set.aggregate(
            totale=models.Sum('tempo')
        )['totale'] or timedelta(0)
        
        logging.debug(f"Ricalcolata durata per Turno {self.pk}: {total_durata}")
        
        # Usa update() per evitare ricorsione e per bypassare save()
        Turno.objects.filter(pk=self.pk).update(durata=total_durata)
        # Aggiorna l'istanza corrente
        self.durata = total_durata


class TurnoProprietario(models.Model):
    """Modello intermediario per gestire il tempo allocato a ciascun proprietario in un turno"""
    turno = models.ForeignKey(Turno, on_delete=models.CASCADE)
    proprietario = models.ForeignKey(Persona, on_delete=models.CASCADE)
    tempo = DurationHHMMField(
        help_text="Tempo allocato a questo proprietario (hh:mm)"
    )
    
    class Meta:
        verbose_name = "Proprietario Turno"
        verbose_name_plural = "Proprietari Turno"
        unique_together = [['turno', 'proprietario']]
    
    def __str__(self):
        hours, remainder = divmod(self.tempo.total_seconds(), 3600)
        minutes = remainder // 60
        return f"{self.proprietario} - {int(hours):02d}:{int(minutes):02d}"
    
    def save(self, *args, **kwargs):
        """Salva e ricalcola la durata totale del turno"""
        logging.debug(f"Salvataggio TurnoProprietario: Turno {self.turno.pk}, Proprietario {self.proprietario.pk}, Tempo {self.tempo}")
        super().save(*args, **kwargs)
        self.turno.ricalcola_durata()
    
    def delete(self, *args, **kwargs):
        """Elimina e ricalcola la durata totale del turno"""
        turno = self.turno
        super().delete(*args, **kwargs)
        turno.ricalcola_durata()