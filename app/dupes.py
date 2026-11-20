"""0.41.0 (Miguel, 20 Nov 2026): the duplicate check run when a feature is filed.

Pure and model-free: the new item's title plus first paragraph against every OPEN feature and bug on the board
(title plus first paragraph each). Words are lower-cased, stop words dropped, a light stem applied; each item becomes
a TF-IDF vector (IDF over the open items, so words every item shares count for little) with title words counted
twice. Matches are the items whose cosine similarity reaches THRESHOLD and that share at least MIN_SHARED words;
the best MAX_MATCHES are kept. Not a duplicate: an item either one links to (#N, repo#N, issue URL; follow-ups and
split parts name each other), and a part of the same plan (same author, another repo, filed within SIBLING_S).
Tuned on the open board of 20 Nov 2026 (259 features and bugs): 24 hits at 0.5, mostly real overlaps, versus 125 at
0.34. The host fetches the items and posts the comment.
"""
import math
import re

LABEL = 'possible-duplicate'
COMMENT_HEAD = 'Possible duplicate of'
THRESHOLD = 0.5
SIBLING_S = 6 * 3600
MIN_SHARED = 2
MAX_MATCHES = 3
STOP = set('''a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each else even ever every few for from further get gets
got had has have having he her here hers him his how i if in into is it its itself just let like make makes me more most
my need needs new no nor not now of off on once only or other our out over own please same she should so some such than
that the their them then there these they this those through to too under until up us use used using very want wants
was we were what when where which while who why will with would you your yours yourself able way thing things something
someone anything there's it's i'd i'm don't doesn't can't won't isn't should've could've also really maybe still just
wizard wizardos app apps feature features bug bugs issue issues add adds added show shows shown see seen one two'''.split())
_WORD = re.compile(r"[a-z0-9][a-z0-9'+-]*")


def stem(w):
    w = w.strip("'-+")
    for suf, n in (('ies', 'y'), ('ing', ''), ('ed', ''), ('es', ''), ('s', '')):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)] + n
    return w


def words(text):
    out = []
    for w in _WORD.findall((text or '').lower()):
        w = stem(w)
        if len(w) >= 3 and w not in STOP and not w.isdigit():
            out.append(w)
    return out


def terms(title, para):
    """Weighted term counts: title words twice, first-paragraph words once."""
    tf = {}
    for w in words(title):
        tf[w] = tf.get(w, 0) + 2
    for w in words(para):
        tf[w] = tf.get(w, 0) + 1
    return tf


def refs(body, repo, org='humanitylabs-org'):
    """Issue ids a body links to, lower-cased 'owner/repo#n'."""
    body, out = body or '', set()
    for m in re.finditer(r'(?:github\.com/)?([\w.-]+)/([\w.-]+)(?:#|/issues/|/pull/)(\d+)', body):
        out.add(f'{m.group(1)}/{m.group(2)}#{m.group(3)}'.lower())
    for m in re.finditer(r'(?<![\w/.-])([\w.-]+)#(\d+)', body):
        out.add(f'{org}/{m.group(1)}#{m.group(2)}'.lower())
    for m in re.finditer(r'(?<![\w/#])#(\d+)', body):
        out.add(f'{repo}#{m.group(1)}'.lower())
    return out


def related(new, it):
    """Linked either way, or a sibling part of one plan (same author, another repo, filed close together)."""
    a, b = str(new.get('id') or '').lower(), str(it.get('id') or '').lower()
    if (b and b in (new.get('refs') or set())) or (a and a in (it.get('refs') or set())):
        return True
    na, ia = (new.get('author') or '').lower(), (it.get('author') or '').lower()
    nt, itt = new.get('ts'), it.get('ts')
    return bool(na and na == ia and new.get('repo') != it.get('repo') and nt is not None and itt is not None
                and abs(nt - itt) <= SIBLING_S)


def matches(new, items, threshold=THRESHOLD, limit=MAX_MATCHES):
    """new = {'title', 'para'}; items = [{'id', 'title', 'para', ...}] -> best matches (each item + 'score'), best first."""
    docs = [(it, terms(it.get('title'), it.get('para'))) for it in items or [] if not related(new, it)]
    q = terms(new.get('title'), new.get('para'))
    if not q or not docs:
        return []
    n = len(docs) + 1
    df = {}
    for _, tf in docs + [(None, q)]:
        for w in tf:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + n / c) for w, c in df.items()}

    def vec(tf):
        v = {w: c * idf[w] for w, c in tf.items()}
        return v, math.sqrt(sum(x * x for x in v.values())) or 1.0

    qv, qn = vec(q)
    out = []
    for it, tf in docs:
        if not tf:
            continue
        v, vn = vec(tf)
        shared = [w for w in qv if w in v]
        if len(shared) < MIN_SHARED:
            continue
        score = sum(qv[w] * v[w] for w in shared) / (qn * vn)
        if score >= threshold:
            out.append({k: v for k, v in it.items() if k != 'refs'} | {'score': round(score, 3)})
    out.sort(key=lambda x: -x['score'])
    return out[:limit]


def comment(found):
    """The one short comment: 'Possible duplicate of owner/repo#1, owner/repo#2' (GitHub links each)."""
    return COMMENT_HEAD + ' ' + ', '.join(f['id'] for f in found)
