from django.contrib import admin
from django.utils.html import format_html
from adminsortable2.admin import SortableAdminMixin, SortableInlineAdminMixin, SortableAdminBase
import csv
from django.http import HttpResponse
from datetime import timedelta
from .models import Persona, Consorzio, Ramo, Giro, Turno


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


class TurnoInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Turno
    extra = 1
    fields = ('ordine', 'utilizzatore', 'durata', 'proprietari')
    #readonly_fields = ('get_proprietari_display',)
    ordering = ['ordine']
    autocomplete_fields = ['utilizzatore']
    
    def get_proprietari_display(self, obj):
        if obj.pk:
            return ", ".join([str(p) for p in obj.proprietari.all()])
        return "-"
    get_proprietari_display.short_description = 'Proprietari'


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
class GiroAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ('nome', 'ordine', 'get_ramo', 'get_consorzio', 'num_turni', 'durata_totale')
    list_filter = ('ramo__consorzio', 'ramo')
    search_fields = ('nome', 'ramo__nome', 'ramo__consorzio__nome')
    inlines = [TurnoInline]
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
def esporta_programmazione_ramo(modeladmin, request, queryset):
    """
    Esporta la programmazione dei turni per ramo in formato CSV.
    Include ordine, utilizzatore, durata, e proprietari.
    """
    # Raggruppa turni per ramo
    rami_turni = {}
    for turno in queryset.select_related('utilizzatore', 'giro__ramo__consorzio').prefetch_related('proprietari'):
        ramo = turno.giro.ramo
        key = f"{ramo.consorzio.nome} - {ramo.nome}"
        if key not in rami_turni:
            rami_turni[key] = []
        rami_turni[key].append(turno)
    
    # Crea il file CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="programmazione_turni.csv"'
    response.write('\ufeff')  # BOM per Excel UTF-8
    
    writer = csv.writer(response)
    writer.writerow(['Consorzio - Ramo', 'Giro', 'Ordine', 'Utilizzatore', 'Durata (hh:mm)', 'Proprietari'])
    
    for ramo_nome, turni in sorted(rami_turni.items()):
        # Ordina turni per giro e ordine
        turni_ordinati = sorted(turni, key=lambda t: (t.giro.ordine, t.ordine))
        for turno in turni_ordinati:
            hours, remainder = divmod(turno.durata.total_seconds(), 3600)
            minutes = remainder // 60
            durata_str = f"{int(hours):02d}:{int(minutes):02d}"
            proprietari_str = ", ".join([str(p) for p in turno.proprietari.all()])
            
            writer.writerow([
                ramo_nome,
                turno.giro.nome,
                turno.ordine,
                str(turno.utilizzatore),
                durata_str,
                proprietari_str
            ])
    
    return response

esporta_programmazione_ramo.short_description = "Esporta programmazione per ramo (CSV)"


@admin.register(Turno)
class TurnoAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ('ordine', 'get_giro_completo', 'utilizzatore', 'durata_hhmm', 'get_proprietari_list')
    list_display_links = ('get_giro_completo', 'utilizzatore')
    list_filter = ('giro__ramo__consorzio', 'giro__ramo', 'giro')
    search_fields = ('utilizzatore__nome', 'utilizzatore__cognome', 'proprietari__nome', 'proprietari__cognome')
    autocomplete_fields = ['utilizzatore', 'proprietari']
    filter_horizontal = ('proprietari',)
    list_per_page = 100
    list_editable = ('ordine',)
    actions = [esporta_programmazione_ramo]
    
    fieldsets = (
        ('Informazioni Principali', {
            'fields': ('giro', 'ordine', 'utilizzatore')
        }),
        ('Durata', {
            'fields': ('durata', 'durata_hhmm_display')
        }),
        ('Proprietari', {
            'fields': ('proprietari',)
        }),
    )
    
    readonly_fields = ('durata_hhmm_display',)
    
    def get_giro_completo(self, obj):
        return str(obj.giro)
    get_giro_completo.short_description = 'Giro'
    get_giro_completo.admin_order_field = 'giro'
    
    def durata_hhmm(self, obj):
        hours, remainder = divmod(obj.durata.total_seconds(), 3600)
        minutes = remainder // 60
        return f"{int(hours):02d}:{int(minutes):02d}"
    durata_hhmm.short_description = 'Durata (hh:mm)'
    
    def durata_hhmm_display(self, obj):
        if obj.pk:
            hours, remainder = divmod(obj.durata.total_seconds(), 3600)
            minutes = remainder // 60
            return format_html('<strong>{:02d}:{:02d}</strong>', int(hours), int(minutes))
        return "-"
    durata_hhmm_display.short_description = 'Durata Visualizzata (hh:mm)'
    
    def get_proprietari_list(self, obj):
        if obj.pk:
            proprietari = list(obj.proprietari.all()[:3])
            if len(proprietari) == 0:
                return "-"
            display = ", ".join([str(p) for p in proprietari])
            total = obj.proprietari.count()
            if total > 3:
                display += f" (+ altri {total - 3})"
            return display
        return "-"
    get_proprietari_list.short_description = 'Proprietari'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('utilizzatore', 'giro__ramo__consorzio').prefetch_related('proprietari')
