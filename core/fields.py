from django import forms
from django.db import models
from datetime import timedelta
import re


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
            total_seconds = int(value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        return value


class DurationHHMMFormField(forms.DurationField):
    """Form field che valida il formato hh:mm"""
    widget = DurationHHMMWidget
    
    def to_python(self, value):
        if value in (None, ''):
            return None
        if isinstance(value, timedelta):
            return value
        
        # Pattern per hh:mm (ore possono essere più di 24)
        pattern = r'^(\d+):([0-5]?\d)$'
        match = re.match(pattern, str(value).strip())
        
        if not match:
            raise forms.ValidationError(
                "Inserisci la durata nel formato hh:mm (es. 02:30 o 25:00)"
            )
        
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return timedelta(hours=hours, minutes=minutes)
    
    def prepare_value(self, value):
        if isinstance(value, timedelta):
            total_seconds = int(value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        return value


class DurationHHMMField(models.DurationField):
    """
    DurationField che nell'admin mostra il formato hh:mm invece di [DD] [HH:[MM:]]ss[.uuuuuu]
    
    Internamente è un normale DurationField, quindi supporta tutta l'aritmetica
    con date, datetime e altre durate.
    """
    
    def formfield(self, **kwargs):
        defaults = {'form_class': DurationHHMMFormField}
        defaults.update(kwargs)
        return super().formfield(**defaults)