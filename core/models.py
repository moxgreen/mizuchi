from django.db import models

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
    proprietari = models.ManyToManyField(Persona, related_name='turni_proprietario')
    durata = models.DurationField()
    ordine = models.IntegerField()
    giro = models.ForeignKey(Giro, on_delete=models.CASCADE, related_name='turni')

    class Meta:
        verbose_name_plural = "Turni"
        ordering = ['giro', 'ordine']
        unique_together = [['giro', 'ordine']]

    def __str__(self):
        return f"Turno {self.ordine} - {self.utilizzatore.nome} ({self.durata})"