import peewee
from datetime import datetime

from . import db
from .builder import TemplateBuilder


def init(filename, create=True, **kwargs)->None:
    db.database.init(filename, **kwargs)

    if create:
        db.init_tables()


def find_model(_any=None, id_=None, name=None):
    if _any:
        if isinstance(_any, int):
            id_ = _any
        elif isinstance(_any, str):
            name = _any

    if id_:
        return db.Model.get_or_none(id=id_).id
    elif name:
        return db.Model.get_or_none(name=name).id
    else:
        raise ValueError


def create_model(name, key_fields: list, templates: list):
    """

    :param name:
    :param list of str key_fields:
    :param list of Union[dict, TemplateBuilder] templates:
    :return:
    """
    with db.database.atomic():
        srs_model = db.Model.create(
            name=name,
            key_fields=key_fields
        )

        for template in templates:
            db.Template.create(
                model_id=srs_model.id,
                name=template['name'],
                front=template['front']
            )

        return srs_model.id


def find_notes(q_str: str=None, **kwargs):
    if q_str:
        raise NotImplementedError

    q = db.Note.select()

    for k, v in kwargs.items():
        q = q.where(db.Note.data[k] == v)

    return [n.id for n in q]


def create_note(model_id, data: dict, tags: list=None):
    srs_note = db.Note.create(
        model_id=model_id,
        data=data
    )

    if tags:
        notes_add_tags([srs_note.id], tags)

    return srs_note.id


def update_note(note_id, **kwargs):
    srs_note = db.Note.get(id=note_id)
    srs_note.data.update(kwargs)
    srs_note.modified = datetime.now()
    srs_note.save()


def notes_add_tag(note_ids, tag: str, ignore_errors=True):
    for note_id in note_ids:
        srs_note = db.Note.get(id=note_id)
        try:
            srs_note.add_tag(tag)
        except peewee.IntegrityError:
            if not ignore_errors:
                raise


def notes_add_tags(note_ids, tags, ignore_errors=True):
    for tag in tags:
        notes_add_tag(note_ids, tag, ignore_errors=ignore_errors)


def notes_remove_tag(note_ids, tag):
    for note_id in note_ids:
        srs_note = db.Note.get(id=note_id)
        srs_note.remove_tag(tag)


def cards_add_deck(card_ids, deck: str, ignore_errors=True):
    for card_id in card_ids:
        srs_card = db.Card.get(id=card_id)
        try:
            srs_card.add_deck(deck)
        except peewee.IntegrityError:
            if not ignore_errors:
                raise


def cards_remove_deck(card_ids, deck: str):
    for card_id in card_ids:
        srs_card = db.Card.get(id=card_id)
        srs_card.remove_deck(deck)
