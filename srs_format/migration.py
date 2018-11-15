import peewee as pv
from playhouse import sqlite_ext
from playhouse.migrate import SqliteMigrator, migrate
from datetime import datetime

from srs_format import db


def upgrade():
    settings = db.Settings.get()
    version = settings.info['version']
    migrator = SqliteMigrator(db.database)

    if version < '0.2':
        migrate(
            migrator.add_column('deck', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('media', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('model', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('template', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('note', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('card', 'info', sqlite_ext.JSONField(default=dict)),
            migrator.add_column('card', 'last_review', pv.TimestampField()),
        )
        settings.info['version'] = '0.2'
        settings.save()

    if version < '0.2.1':
        migrate(
            migrator.drop_column('card', 'last_review'),
            migrator.add_column('card', 'last_review', pv.DateTimeField(default=datetime.now)),
            migrator.drop_column('note', 'modified'),
            migrator.add_column('note', 'modified', pv.DateTimeField(default=datetime.now))
        )
        settings.info['version'] = '0.2.1'
        settings.save()
