import shlex
import json
import re

ADDITIONAL_CHAR = ''.join(re.findall(r'\w', ''.join(chr(u) for u in range(0x10FFFF))))


def parse_query(q: str, operators=(':', '=', '>', '<')):
    """
    :param str q:
    :param list operators:
    :return list|None:
    >>> parse_query('')
    >>> parse_query('a')
    [['a']]
    >>> parse_query('a:b')
    [['a', ':', 'b']]
    >>> parse_query('a:b c:d')
    [['a', ':', 'b'], ['c', ':', 'd']]
    >>> parse_query('a:b:c')
    >>> parse_query("a:'b c'")
    [['a', ':', 'b c']]
    >>> parse_query("a:'b c")
    >>> parse_query("'a b':c")
    [['a b', ':', 'c']]
    >>> parse_query("'a:b':c")
    [['a:b', ':', 'c']]
    >>> parse_query('tag:微信')
    [['tag', ':', '微信']]
    """
    if q:
        try:
            queue = []
            sub_queue = []
            shl = shlex.shlex(q)
            shl.wordchars += ADDITIONAL_CHAR
            for token in list(shl) + ['a']:
                if token in operators:
                    if len(sub_queue) == 1:
                        sub_queue.append(token)
                    else:
                        return
                else:
                    if token[0] == '"':
                        token = json.loads(token)
                    elif token[0] == "'":
                        token = json.loads(token
                                           .replace("'", '\0')
                                           .replace('"', "'")
                                           .replace('\0', '"'))

                    if len(sub_queue) == 0:
                        sub_queue.append(token)
                    elif len(sub_queue) == 1:
                        queue.append(sub_queue)
                        sub_queue = [token]
                    elif len(sub_queue) == 2:
                        sub_queue.append(token)
                    elif len(sub_queue) == 3:
                        queue.append(sub_queue)
                        sub_queue = [token]
                    else:
                        return
        except ValueError:
            return

        return queue
    return
