from django import forms
from django.db import models
from datetime import timedelta
import re


def format_duration_hhmm(duration):
    """Formatta un timedelta come hh:mm"""
    if duration is None:
        return "00:00"
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


class DurationHHMM(timedelta):
    """Sottoclasse di timedelta che mostra sempre il formato hh:mm"""
    
    def __str__(self):
        return format_duration_hhmm(self)
    
    def __repr__(self):
        return f"DurationHHMM({format_duration_hhmm(self)})"


class DurationHHMMWidget(forms.TextInput):
    """Widget per DurationField che mostra e accetta solo il formato hh:mm"""
    
    def __init__(self, attrs=None):
        default_attrs = {'placeholder': 'hh:mm', 'style': 'width: 80px;'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)
    
    def format_value(self, value):
        if value is None or value == '':
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, timedelta):
            return format_duration_hhmm(value)
        return value


class DurationHHMMFormField(forms.DurationField):
    """Form field che valida il formato hh:mm"""
    widget = DurationHHMMWidget
    
    def to_python(self, value):
        if value in (None, ''):
            return None
        if isinstance(value, timedelta):
            return DurationHHMM(seconds=value.total_seconds())
        
        # Pattern per hh:mm (ore possono essere più di 24)
        pattern = r'^(\d+):([0-5]?\d)$'
        match = re.match(pattern, str(value).strip())
        
        if not match:
            raise forms.ValidationError(
                "Inserisci la durata nel formato hh:mm (es. 02:30 o 25:00)"
            )
        
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return DurationHHMM(hours=hours, minutes=minutes)
    
    def prepare_value(self, value):
        if isinstance(value, timedelta):
            return format_duration_hhmm(value)
        return value


class DurationHHMMField(models.DurationField):
    """
    DurationField che mostra sempre il formato hh:mm invece di [DD] [HH:[MM:]]ss[.uuuuuu]
    
    Internamente è un normale DurationField, quindi supporta tutta l'aritmetica
    con date, datetime e altre durate.
    """
    
    def formfield(self, **kwargs):
        defaults = {'form_class': DurationHHMMFormField}
        defaults.update(kwargs)
        return super().formfield(**defaults)
    
    def from_db_value(self, value, expression, connection):
        """Converte il valore dal DB in DurationHHMM"""
        if value is None:
            return None
        if isinstance(value, timedelta):
            return DurationHHMM(seconds=value.total_seconds())
        return value
    
    def to_python(self, value):
        """Converte qualsiasi valore in DurationHHMM"""
        if value is None:
            return None
        if isinstance(value, DurationHHMM):
            return value
        if isinstance(value, timedelta):
            return DurationHHMM(seconds=value.total_seconds())
        # Delega al parent per parsing stringhe standard
        parsed = super().to_python(value)
        if parsed is not None:
            return DurationHHMM(seconds=parsed.total_seconds())
        return None
    
    def value_to_string(self, obj):
        """Per serializzazione"""
        value = self.value_from_object(obj)
        return format_duration_hhmm(value)