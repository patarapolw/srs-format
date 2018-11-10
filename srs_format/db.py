import peewee as pv
from playhouse import sqlite_ext, signals
from playhouse.shortcuts import model_to_dict, dict_to_model

from datetime import datetime, timedelta
import random
import json
from typing import Any
from hashlib import md5
import logging

from .default import DEFAULT


database = sqlite_ext.SqliteDatabase(None)


class BaseModel(signals.Model):
    class Meta:
        database = database


class SrsField(pv.TextField):
    def db_value(self, value):
        if value:
            return json.dumps([v.total_seconds() for v in value])

    def python_value(self, value):
        if value:
            return [timedelta(seconds=v) for v in json.loads(value)]
        else:
            return DEFAULT['srs']


class ConstraintField(pv.TextField):
    def db_value(self, value):
        if value:
            if isinstance(value, list):
                value = dict.fromkeys(value)
            return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def python_value(self, value):
        if value:
            return sorted(json.loads(value).keys())


class Settings(BaseModel):
    srs = SrsField(default=DEFAULT['srs'])
    info = sqlite_ext.JSONField(default=DEFAULT['info'])


class Tag(BaseModel):
    name = pv.TextField(unique=True, collation='NOCASE')

    def __repr__(self):
        return f'<Tag: "{self.name}">'

    def __str__(self):
        return self.name


class Deck(BaseModel):
    name = pv.TextField(unique=True, collation='NOCASE')

    def __repr__(self):
        return f'<Deck: "{self.name}">'

    def __str__(self):
        return self.name

    @classmethod
    def get_deck_dict(cls, super_deck=None):
        if super_deck is None:
            super_deck = ''
        else:
            if not isinstance(super_deck, str):
                super_deck = '::'.join(super_deck)
            super_deck += '::'

        def _node_index(dx, comparison):
            for i, node in enumerate(dx.setdefault('nodes', list())):
                if node['text'] == comparison:
                    return i

        def _recurse_name_part(dx, np, _srs_deck, depth=0):
            i = _node_index(dx, np[depth])

            if i is not None:
                di = dx['nodes'][i]
            else:
                dx['nodes'].append(dict())
                di = dx['nodes'][-1]
                di['text'] = np[depth]

            if depth < len(np) - 1:
                return _recurse_name_part(di, np, _srs_deck, depth + 1)
            else:
                di['deck'] = _srs_deck

        d = dict()
        for srs_deck in cls.select().where(cls.name.startswith(super_deck)).order_by(cls.name):
            name_parts = srs_deck.name.replace(super_deck, '').split('::')
            _recurse_name_part(d, name_parts, srs_deck)

        return d


class Media(BaseModel):
    data = pv.BlobField()
    h = pv.TextField()

    class Meta:
        indexes = [
            # pv.SQL('CREATE UNIQUE INDEX media_data_hash ON media (MD5(data))'),
        ]


@signals.pre_save(sender=Media)
def media_pre_save(model_class, instance, created):
    instance.h = md5(instance.data).hexdigest()


class Model(BaseModel):
    name = pv.TextField(unique=True)
    key_fields = sqlite_ext.JSONField(default=list)
    css = pv.TextField(null=True)
    js = pv.TextField(null=True)


class Template(BaseModel):
    model = pv.ForeignKeyField(Model, backref='templates')
    name = pv.TextField()
    front = pv.TextField()
    back = pv.TextField(null=True)

    def test_front(self, d):
        text = self.front
        for k, v in d.items():
            text = text.replace('{{%s}}' % k, str(v))

        return text

    class Meta:
        indexes = [
            (('model_id', 'name'), True),
            (('model_id', 'front'), True),
        ]


class Note(BaseModel):
    model = pv.ForeignKeyField(Model, backref='notes')
    data = sqlite_ext.JSONField()              # format = dict()
    constraint = ConstraintField(unique=True)  # format = list()
    _tags = pv.ManyToManyField(Tag, backref='notes')

    created = pv.DateTimeField(constraints=[pv.SQL('DEFAULT CURRENT_TIMESTAMP')])
    modified = pv.TimestampField()

    @property
    def tags(self):
        return [t.name for t in self._tags]

    def mark(self, tag='marked'):
        Tag.get_or_create(name=tag)[0].notes.add(self)

    add_tag = mark

    def unmark(self, tag='marked'):
        Tag.get_or_create(name=tag)[0].notes.remove(self)

    remove_tag = unmark


NoteTag = Note._tags.get_through_model()


@signals.pre_save(sender=Note)
def note_pre_save(model_class, instance, created):
    ls = Model.get(id=instance.model_id).key_fields
    d = dict()

    for k in ls:
        d[k] = instance.data[k]
    instance.constraint = d


@signals.post_save(sender=Note)
def note_post_save(model_class, instance, created):
    if created:
        with database.atomic():
            note_id = instance.id
            for template in instance.model.templates:
                if template.test_front(dict()) != template.test_front(instance.data):
                    try:
                        Card.create(
                            template_id=template.id,
                            note_id=note_id
                        )
                    except pv.IntegrityError as e:
                        logging.error(e)


class Card(BaseModel):
    template = pv.ForeignKeyField(Template, backref='cards')
    note = pv.ForeignKeyField(Note, backref='cards')
    _front = pv.TextField(unique=True)
    srs_level = pv.IntegerField(null=True)
    next_review = pv.DateTimeField(null=True)
    _decks = pv.ManyToManyField(Deck, backref='cards')

    backup = None

    @property
    def deck(self):
        return [d.name for d in self._decks]

    @property
    def front(self):
        text = self.template.front
        for k, v in self.note.data.items():
            text = text.replace('{{%s}}' % k, str(v))

        return text

    @property
    def back(self):
        text = self.template.back
        if not text:
            return '\n'.join(' ' * 4 + line for line in json.dumps(
                self.note.data,
                indent=2, ensure_ascii=False
            ).split('\n'))

        for k, v in self.note.data.items():
            text = text.replace('{{%s}}' % k, str(v))

        return text

    def __repr__(self):
        return self.front

    @property
    def data(self):
        return self.note.data

    def add_deck(self, deck_name):
        Deck.get_or_create(name=deck_name)[0].cards.add(self)

    def remove_deck(self, deck_name):
        Deck.get_or_create(name=deck_name)[0].cards.remove(self)

    def mark(self, tag='marked'):
        return self.note.mark(tag)

    def unmark(self, tag='marked'):
        return self.note.unmark(tag)

    def right(self):
        if not self.backup:
            self.backup = model_to_dict(self)

        if not self.srs_level:
            self.srs_level = 0
        else:
            self.srs_level = self.srs_level + 1

        srs = Settings.get().srs
        try:
            self.next_review = datetime.now() + srs[self.srs_level]
        except IndexError:
            self.next_review = None

        self.save()

    correct = next_srs = right

    def wrong(self, next_review=timedelta(minutes=10)):
        if not self.backup:
            self.backup = model_to_dict(self)

        if self.srs_level and self.srs_level > 0:
            self.srs_level = self.srs_level - 1

        self.bury(next_review)

    incorrect = previous_srs = wrong

    def bury(self, next_review=timedelta(hours=4)):
        if not self.backup:
            self.backup = model_to_dict(self)

        if isinstance(next_review, timedelta):
            self.next_review = datetime.now() + next_review
        else:
            self.next_review = next_review
        self.save()

    def undo(self):
        if self.backup:
            dict_to_model(Card, self.backup).save()

    @classmethod
    def iter_quiz(cls, **kwargs):
        db_cards = list(cls.search(**kwargs))
        random.shuffle(db_cards)

        return iter(db_cards)

    @classmethod
    def iter_due(cls, **kwargs):
        return cls.iter_quiz(due=True, **kwargs)

    @classmethod
    def search(cls, deck=None, tags=None, due=Any, offset=0, limit=None):
        query = cls.select()

        if due is True:
            query = query.where(Card.next_review < datetime.now())
        elif due is False:
            query = query.where(Card.next_review >= datetime.now())
        elif due is None:
            query = query.where(Card.next_review.is_null(True))
        elif isinstance(due, timedelta):
            query = query.where(Card.next_review < datetime.now() + due)
        elif isinstance(due, datetime):
            query = query.where(Card.next_review < due)

        if deck:
            if not isinstance(deck, str):
                deck = '::'.join(deck)

            query = query.switch(cls).join(CardDeck).join(Deck).where(Deck.name.startswith(deck))

        if tags:
            for tag in tags:
                query = query.switch(cls).join(Note).join(NoteTag).join(Tag).where(Tag.name.contains(tag))

        query = query.order_by(cls.next_review.desc())

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query


CardDeck = Card._decks.get_through_model()


@signals.pre_save(sender=Card)
def card_pre_save(model_class, instance, created):
    instance._front = instance.front


def init_tables():
    database.create_tables([Settings,
                            Tag, Note, NoteTag,
                            Deck, Card, CardDeck,
                            Media, Model, Template])
    Settings.get_or_create()
