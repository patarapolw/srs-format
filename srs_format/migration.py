import peewee as pv
from playhouse import sqlite_ext
from playhouse.migrate import SqliteMigrator, migrate

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
