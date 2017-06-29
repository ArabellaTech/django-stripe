# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-06-13 10:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aa_stripe', '0005_auto_20170613_0614'),
    ]

    operations = [
        migrations.AddField(
            model_name='stripesubscription',
            name='end_date',
            field=models.DateField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name='stripesubscription',
            name='canceled_at',
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
    ]
