import peewee as pv
from playhouse import sqlite_ext, signals
from playhouse.shortcuts import model_to_dict, dict_to_model

from datetime import datetime, timedelta
import random
import json
from hashlib import md5
import logging
import pytimeparse
import dateutil.parser

from .default import DEFAULT
from .util import parse_query


database = sqlite_ext.SqliteDatabase(None)


class BaseModel(signals.Model):
    def to_dict(self, **kwargs):
        kwargs.setdefault('backrefs', True)
        kwargs.setdefault('max_depth', 2)
        kwargs.setdefault('manytomany', True)

        return model_to_dict(self, **kwargs)

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
    info = sqlite_ext.JSONField(default=dict)

    def __repr__(self):
        return f'<Deck: "{self.name}">'

    def __str__(self):
        return self.name


class Media(BaseModel):
    data = pv.BlobField()
    h = pv.TextField()
    info = sqlite_ext.JSONField(default=dict)

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
    info = sqlite_ext.JSONField(default=dict)


class Template(BaseModel):
    model = pv.ForeignKeyField(Model, backref='templates')
    name = pv.TextField()
    front = pv.TextField()
    back = pv.TextField(null=True)
    info = sqlite_ext.JSONField(default=dict)

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
    modified = pv.DateTimeField(constraints=[pv.SQL('DEFAULT CURRENT_TIMESTAMP')])

    info = sqlite_ext.JSONField(default=dict)

    def to_dict(self):
        return super(Note, self).to_dict(manytomany=False, backrefs=False,
                                         exclude=['_tags'], extra_attrs=['tags'])

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

    instance.modified = datetime.now()


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

    last_review = pv.DateTimeField(constraints=[pv.SQL('DEFAULT CURRENT_TIMESTAMP')])
    info = sqlite_ext.JSONField(default=dict)

    backup = None

    def to_dict(self, max_depth=2, **kwargs):
        d = super(Card, self).to_dict(manytomany=False, backrefs=False,
                                      exclude=['_decks', '_front', 'note'],
                                      extra_attrs=['decks', 'front', 'back'])
        d['note'] = self.note.to_dict()
        return d

    @property
    def decks(self):
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

    def right(self, step=1):
        self.undo()

        if not self.backup:
            self.backup = model_to_dict(self)

        print(self.srs_level)

        if self.srs_level is None:
            self.srs_level = 0
        else:
            self.srs_level = self.srs_level + step

        srs = Settings.get().srs
        try:
            self.next_review = datetime.now() + srs[self.srs_level]
        except IndexError:
            self.next_review = None

        assert isinstance(self.info, dict)

        self.info['lapse'] = 0
        self.info['streak'] = self.info.get('streak', 0) + 1
        self.info['total_right'] = self.info.get('total_right', 0) + 1

        self.save()

    correct = next_srs = right

    def easy(self, max_srs_level_enabled=3):
        if self.srs_level < max_srs_level_enabled:
            return self.right(step=2)
        else:
            raise ValueError

    def wrong(self, next_review=timedelta(minutes=10)):
        self.undo()

        if not self.backup:
            self.backup = model_to_dict(self)

        if self.srs_level is not None and self.srs_level > 0:
            self.srs_level = self.srs_level - 1

        assert isinstance(self.info, dict)

        self.info['streak'] = 0
        self.info['lapse'] = self.info.get('lapse', 0) + 1
        self.info['total_wrong'] = self.info.get('total_wrong', 0) + 1

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

    def reset(self):
        self.srs_level = None
        self.next_review = None
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
    def search(cls, q_str='', deck=None, tags=None, due=None, offset=0, limit=None):
        """

        :param q_str:
        :param deck:
        :param tags:
        :param bool|None|timedelta|datetime due:
        :param offset:
        :param limit:
        :return:
        """
        query = cls.select()
        due_is_set = False
        note_keys = None

        result = parse_query(q_str)
        if result:
            for seg in result:
                if len(seg) == 1:
                    if note_keys is None:
                        note_keys = set()
                        for srs_note in Note.select(Note.data):
                            note_keys.update(srs_note.data.keys())

                        note_keys = tuple(note_keys)
                    q_note = Note.data[note_keys[0]].contains(seg[0])

                    for k in note_keys[1:]:
                        q_note |= Note.data[k].contains(seg[0])

                    query = query.switch(cls).join(Note).where(q_note)
                else:
                    if seg[0] == 'due':
                        due_is_set = True
                        if seg[2].lower() == 'true':
                            query = query.switch(cls).where(cls.next_review < datetime.now())
                        elif seg[2].lower() == 'false':
                            query = query.switch(cls).where(cls.next_review.is_null(True))
                        else:
                            dur_sec = pytimeparse.parse(seg[2])
                            if dur_sec:
                                _due = datetime.now() + timedelta(seconds=dur_sec)
                            else:
                                _due = dateutil.parser.parse(seg[2])

                            query = query.switch(cls).where(cls.next_review < _due)
                    elif seg[0] == 'deck':
                        deck_q = (Deck.name == seg[2])
                        if seg[1] != '=':
                            deck_q = (deck_q | Deck.name.startswith(seg[2] + '::'))

                        query = query.switch(cls).join(CardDeck).join(Deck).where(deck_q)
                    elif seg[0] == 'tag':
                        if seg[1] == '=':
                            query = query.switch(cls).join(Note).join(NoteTag).join(Tag)\
                                .where(Tag.name == seg[2])
                        else:
                            query = query.switch(cls).join(Note).join(NoteTag).join(Tag)\
                                .where(Tag.name.contains(seg[2]))
                    else:
                        if seg[1] == '=':
                            query = query.switch(cls).join(Note).where(Note.data[seg[0]] == seg[2])
                        elif seg[1] == '>':
                            query = query.switch(cls).join(Note).where(Note.data[seg[0]] > seg[2])
                        elif seg[1] == '<':
                            query = query.switch(cls).join(Note).where(Note.data[seg[0]] < seg[2])
                        else:
                            query = query.switch(cls).join(Note).where(Note.data[seg[0]].contains(seg[2]))

        if due is True:
            query = query.switch(cls).where(cls.next_review < datetime.now())
        elif due is False:
            query = query.switch(cls).where(cls.next_review.is_null(True))
        elif isinstance(due, timedelta):
            query = query.switch(cls).where(cls.next_review < datetime.now() + due)
        elif isinstance(due, datetime):
            query = query.switch(cls).where(cls.next_review < due)
        else:
            if not due_is_set:
                query = query.where((cls.next_review < datetime.now()) | cls.next_review.is_null(True))

        if deck:
            query = query.switch(cls).join(CardDeck).join(Deck).where(Deck.name.startswith(deck + '::')
                                                                      | (Deck.name == deck))

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
    instance.modified = datetime.now()


def init_tables():
    database.create_tables([Settings,
                            Tag, Note, NoteTag,
                            Deck, Card, CardDeck,
                            Media, Model, Template])
    Settings.get_or_create()
