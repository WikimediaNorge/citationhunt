import chdb

import flask
import flask_sslify
from flask.ext.compress import Compress

import os
import collections

def get_db():
    db = getattr(flask.g, '_db', None)
    if db is None:
        db = flask.g._db = chdb.init_db()
    return db

Category = collections.namedtuple('Category', ['id', 'title'])
CATEGORY_ALL = Category('all', '')
def get_categories():
    categories = getattr(flask.g, '_categories', None)
    if categories is None:
        cursor = get_db().cursor()
        cursor.execute('''
            SELECT id, title FROM categories WHERE id != "unassigned"
            ORDER BY title;
        ''')
        categories = [CATEGORY_ALL] + [Category(*row) for row in cursor]
        flask.g._categories = categories
    return categories

def get_category_by_id(catid, default = None):
    for c in get_categories():
        if catid == c.id:
            return c
    return default

def select_snippet_by_id(id):
    # The query below may match snippets with unassigned categories. That's
    # fine, we don't display the current category in the UI anyway.
    cursor = get_db().cursor()
    cursor.execute('''
        SELECT snippets.snippet, articles.url, articles.title
        FROM snippets, articles WHERE snippets.id = ? AND
        snippets.article_id = articles.page_id;''', (id,))
    ret = cursor.fetchone()
    if ret is None:
        ret = (None, None, None)
    return ret

def select_random_id(cat = CATEGORY_ALL):
    cursor = get_db().cursor()

    ret = None
    if cat is not CATEGORY_ALL:
        cursor.execute('''
            SELECT snippets.id FROM snippets, categories, articles
            WHERE categories.id = ? AND snippets.article_id = articles.page_id
            AND articles.category_id = categories.id ORDER BY RANDOM()
            LIMIT 1;''', (cat.id,))
        ret = cursor.fetchone()

    if ret is None:
        cursor.execute('''
            SELECT id FROM snippets ORDER BY RANDOM() LIMIT 1;''')
        ret = cursor.fetchone()

    assert ret and len(ret) == 1
    return ret[0]

app = flask.Flask(__name__)
if 'DYNO' in os.environ:
    flask_sslify.SSLify(app)
Compress(app)

@app.route('/')
def citation_hunt():
    id = flask.request.args.get('id')
    cat = flask.request.args.get('cat')

    if cat is not None:
        cat = get_category_by_id(cat)
        if cat is None:
            # invalid category, normalize to "all" and try again by id
            cat = CATEGORY_ALL
            return flask.redirect(
                flask.url_for('citation_hunt', id = id, cat = cat.id))
    else:
        cat = CATEGORY_ALL

    if id is not None:
        # pick snippet by id and just echo back the category, even
        # if the snippet doesn't belong to it.
        s, u, t = select_snippet_by_id(id)
        if (s, u, t) == (None, None, None):
            # invalid id
            flask.abort(404)
        return flask.render_template('index.html',
            snippet = s, url = u, title = t, current_category = cat)

    id = select_random_id(cat)
    return flask.redirect(
        flask.url_for('citation_hunt', id = id, cat = cat.id))

@app.route('/categories.html')
def categories_html():
    return flask.render_template('categories.html',
        categories = get_categories());

@app.after_request
def add_cache_header(response):
    if response.status_code != 302 and response.cache_control.max_age is None:
        response.cache_control.public = True
        response.cache_control.max_age = 3 * 24 * 60 * 60
    return response

@app.teardown_appcontext
def close_db(exception):
    db = getattr(flask.g, '_db', None)
    if db is not None:
        db.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = 'DEBUG' in os.environ
    app.run(host = '0.0.0.0', port = port, debug = debug)
