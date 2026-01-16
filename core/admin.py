from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from datetime import timedelta
from .models import Persona, Consorzio, Ramo, Giro, Turno, TurnoProprietario


# =======================
# PERSONA ADMIN
# =======================
@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ('cognome', 'nome', 'email', 'telefono', 'indirizzo')
    list_display_links = ('cognome', 'nome')
    search_fields = ('nome', 'cognome', 'email', 'telefono')
    ordering = ('cognome', 'nome')
    list_per_page = 50


# =======================
# INLINES
# =======================
class RamoInline(admin.TabularInline):
    model = Ramo
    extra = 1
    fields = ('nome', 'inizio_astratto', 'descrizione')
    show_change_link = True


class GiroInline(admin.TabularInline):
    model = Giro
    extra = 1
    fields = ('nome', 'ordine', 'descrizione')
    show_change_link = True
    ordering = ['ordine']


class TurnoProprietarioInline(admin.TabularInline):
    model = TurnoProprietario
    extra = 1
    fields = ('proprietario', 'tempo')
    autocomplete_fields = ['proprietario']
    


# =======================
# CONSORZIO ADMIN
# =======================
@admin.register(Consorzio)
class ConsorzioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'descrizione', 'num_rami')
    search_fields = ('nome',)
    inlines = [RamoInline]
    
    def num_rami(self, obj):
        return obj.rami.count()
    num_rami.short_description = 'N. Rami'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('rami')


# =======================
# RAMO ADMIN
# =======================
@admin.register(Ramo)
class RamoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'consorzio', 'inizio_astratto_display', 'num_giri')
    list_filter = ('consorzio',)
    search_fields = ('nome', 'consorzio__nome')
    autocomplete_fields = []
    inlines = [GiroInline]
    ordering = ('consorzio', 'nome')
    
    def inizio_astratto_display(self, obj):
        return obj.inizio_astratto.strftime('%d/%m %H:%M')
    inizio_astratto_display.short_description = 'Inizio (gg/mm hh:mm)'
    
    def num_giri(self, obj):
        return obj.giri.count()
    num_giri.short_description = 'N. Giri'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('consorzio').prefetch_related('giri')


# =======================
# GIRO ADMIN
# =======================
@admin.register(Giro)
class GiroAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ordine', 'get_ramo', 'get_consorzio', 'num_turni', 'durata_totale')
    list_filter = ('ramo__consorzio', 'ramo')
    search_fields = ('nome', 'ramo__nome', 'ramo__consorzio__nome')
    inlines = []
    ordering = ('ramo__consorzio', 'ramo', 'nome')
    
    def get_ramo(self, obj):
        return obj.ramo.nome
    get_ramo.short_description = 'Ramo'
    get_ramo.admin_order_field = 'ramo__nome'
    
    def get_consorzio(self, obj):
        return obj.ramo.consorzio.nome
    get_consorzio.short_description = 'Consorzio'
    get_consorzio.admin_order_field = 'ramo__consorzio__nome'
    
    def num_turni(self, obj):
        return obj.turni.count()
    num_turni.short_description = 'N. Turni'
    
    def durata_totale(self, obj):
        total = sum([t.durata for t in obj.turni.all()], timedelta())
        hours, remainder = divmod(total.total_seconds(), 3600)
        minutes = remainder // 60
        return f"{int(hours):02d}:{int(minutes):02d}"
    durata_totale.short_description = 'Durata Totale'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('ramo__consorzio').prefetch_related('turni')


# =======================
# TURNO ADMIN
# =======================
@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ('ordine', 'get_giro_completo', 'utilizzatore', 'durata')
    list_display_links = ('get_giro_completo', 'utilizzatore')
    list_filter = ('giro__ramo__consorzio', 'giro__ramo', 'giro')
    search_fields = ('utilizzatore__nome', 'utilizzatore__cognome')
    autocomplete_fields = ['utilizzatore']
    list_per_page = 100
    list_editable = ('ordine',)
    inlines = [TurnoProprietarioInline]
    
    fieldsets = (
        ('Informazioni Principali', {
            'fields': ('giro', 'ordine', 'utilizzatore')
        }),
        ('Durata', {
            'fields': ('durata',)
        }),
    )
    
    readonly_fields = ('durata',)
    
    def get_giro_completo(self, obj):
        return str(obj.giro)
    get_giro_completo.short_description = 'Giro'
    get_giro_completo.admin_order_field = 'giro'
    
    # def durata_hhmm(self, obj):
    #     hours, remainder = divmod(obj.durata.total_seconds(), 3600)
    #     minutes = remainder // 60
    #     return f"{int(hours):02d}:{int(minutes):02d}"
    # durata_hhmm.short_description = 'Durata calcolata (hh:mm)'
    
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('utilizzatore', 'giro__ramo__consorzio')
