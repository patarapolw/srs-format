from datetime import timedelta

DEFAULT = {
    'srs': [
        timedelta(minutes=10),
        timedelta(hours=4),
        timedelta(hours=8),
        timedelta(days=1),
        timedelta(days=3),
        timedelta(weeks=1),
        timedelta(weeks=2),
        timedelta(weeks=4),
        timedelta(weeks=16)
    ],
    'info': {
        'version': '0.1'
    }
}
