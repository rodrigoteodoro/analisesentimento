import logging
import threading
from json import loads
from uuid import uuid1

from flask import Flask
from flask import abort, g, request
from flask import jsonify
from flask_cors import CORS
from pymongo import MongoClient
from tornado import log as tornadolog
from tornado.httpserver import HTTPServer
from tornado.wsgi import WSGIContainer

formatolog = '%(asctime)s %(levelname)s %(message)s'

import setproctitle
from tornado.ioloop import IOLoop
import os
os.chdir('../../src/')
#print(os.getcwd())
import sys
sys.path.extend(os.getcwd()+'/BaseTwitterListener.py')
sys.path.extend(os.getcwd()+'/BaseAnalise.py')
sys.path.extend(os.getcwd()+'/PalavrasCategorizadas.py')
from BaseTwitterListener import BaseTwitterListener
from BaseAnalise import BaseAnalise
import PalavrasCategorizadas

app = Flask(__name__)
CORS(app)

GLOBAL_SESSION = dict() # Objeto global de sessão
GLOBAL_THREADS = []

def get_db():
    if not hasattr(g, 'sqlite_db'):
        g.cliente_db = MongoClient('127.0.0.1', 27017)['twitter_db']
        # g.cliente_db = MongoClient('172.17.0.2', 27017)['twitter_db']
    return g.cliente_db


@app.errorhandler(404)
def page_not_found(error):
    return 'Página inexistente!', 404


@app.route("/")
def hello():
    return "Servidor executando!"


@app.route("/pesquisas", methods=['GET'])
def pesquisas_get():
    r = dict(data=[])
    db = get_db()
    pesquisas = db['pesquisas']
    cursor = pesquisas.find({}).sort('tag', 1)
    for c in cursor:
        tag = c.get("tag")
        tweets = db['twitter_collection']
        qtd = tweets.count({"tag": tag})
        pqativa = db['pesquisas_ativas']
        qtd_ativa = pqativa.count({"tag": tag})
        doc = dict(tag=tag, track=c.get("track"), quantidade=qtd, ativa=qtd_ativa)
        if qtd_ativa > 0:
            patv = pqativa.find({"tag": tag})
            doc['porcstat'] = (int(patv[0].get("qtd", '0')) * 100) / int(patv[0].get("limite", '100'))
            doc['porcinfo'] = '%s de %s' % (patv[0].get("qtd", '0'), patv[0].get("limite", '100'))
        r['data'].append(doc)
    return jsonify(r), 200


@app.route("/pesquisas/add", methods=['POST'])
def pesquisas_add():
    content = request.data
    if content:
        content = loads(content.decode())
        tag = content.get('tag')
        tag = tag.replace(' ', '')
        track = content.get('track')
        if tag and track:
            d = dict(tag=tag, track=track)
            db = get_db()
            pesquisas = db['pesquisas']
            r = pesquisas.count({"tag": content.get('tag')})
            if r:
                abort(400)
            else:
                pesquisas.insert_one(document=d)
        else:
            abort(400)
    return jsonify({}), 200


@app.route("/tweets", methods=['GET'])
def tweets_get():
    r = dict(data=[])
    tag = request.args.get('tag')
    if tag:
        db = get_db()
        tweets = db['twitter_collection']
        cursor = tweets.find({"tag": tag})
        for c in cursor:
            r['data'].append(dict(texto=c.get("texto")))
    return jsonify(r), 200


@app.route("/tweets/recuperar", methods=['GET'])
def tweets_recuperar_get():
    tag = request.args.get('tag')
    limite = request.args.get('limite')
    if tag and limite and limite.isdigit() and int(limite) > 0:

        def call_recuperar(tag, track, limite):
            c = BaseTwitterListener(treino=False, limite_max=limite)
            c.coletar(tag=tag, track=track)

        db = get_db()
        pesquisas = db['pesquisas']
        r = pesquisas.find({"tag": tag})
        pqativa = db['pesquisas_ativas']
        qtd_ativa = pqativa.count({"tag": tag})
        if r and qtd_ativa == 0:
            t = threading.Timer(2, call_recuperar, (tag, r[0].get('track').split(','), int(limite)))
            t.start()
            GLOBAL_THREADS.append(t)
        else:
            abort(400)
    else:
        abort(400)
    return jsonify({}), 200


@app.route("/tweets/analise", methods=['GET'])
def tweets_analise_get():
    r = dict(data=[])
    tag = request.args.get('tag')
    if tag:
        db = get_db()
        tweets = db['twitter_analise']
        cursor = tweets.find({"tag": tag})
        for c in cursor:
            r['data'].append(dict(texto=c.get("texto"), sentimento=c.get("sentimento"), prob=c.get("prob")))
    else:
        abort(400)
    return jsonify(r), 200


@app.route("/pesquisas/analise", methods=['GET'])
def pesquisa_analise_get():
    r = dict(qtd_pos=0, qtd_neg=0, total=0)
    tag = request.args.get('tag')
    if tag:
        db = get_db()
        tweets = db['pesquisa_analise']
        cursor = tweets.find({"tag": tag})
        for c in cursor:
            r = dict(qtd_pos=c.get("qtd_pos"), qtd_neg=c.get("qtd_neg"), total=c.get("total"))
            break

    return jsonify(r), 200


@app.route("/pesquisas/analisar", methods=['GET'])
def pesquisas__analisar_get():
    r = dict(data=[])
    tag = request.args.get('tag')
    if tag:
        db = get_db()
        pesq_ativa = db['pesquisa_analise_ativa']
        if pesq_ativa.count({"tag": tag}) == 0:
            tweets = db['twitter_collection']
            if tweets.count({"tag": tag}) > 0:
                def call_analisar(tag):
                    b = BaseAnalise(tag)
                    b.analisar()
                t = threading.Timer(2, call_analisar, (tag,))
                t.start()
                GLOBAL_THREADS.append(t)
            else:
                abort(400)
        else:
            abort(400)
    else:
        abort(400)
    return jsonify(r), 200


@app.route("/tweets/nuvempalavras", methods=['GET'])
def tweets_nuvempalavras_get():
    tag = request.args.get('tag')
    db = get_db()
    tweets = db['twitter_collection']
    result = None

    from bson.code import Code
    map = Code('function() {  '
               '  var texto = this.texto;'
               '  if (texto) { '
               '    texto = texto.toLowerCase().split(" "); '
               '    for (var i = texto.length - 1; i >= 0; i--) {'
               '      if (texto[i])  {'
               '        emit(texto[i], 1);'
               '      }'
               '    }'
               '  }'
               '};')
    reduce = Code('function( key, values ) {'
                  '  var count = 0;'
                  '  values.forEach(function(v) {'
                  '    count +=v;'
                  '  });'
                  '  return count;'
                  '}')
    p = 0
    palavras = []
    tracks = []
    for c in db['pesquisas'].find({"tag": tag}):
        tracks = c.get('track')
    tracks = tracks.split(',')

    if tag:
        result = tweets.map_reduce(map, reduce, "nuvempalavras", full_response=True, query={'tag': tag})
    else:
        result = tweets.map_reduce(map, reduce, "nuvempalavras", full_response=True)

    for doc in db['nuvempalavras'].find().sort('value', -1):
        # r['data'].append('{text="%s", weight=%i},' % (doc['_id'],doc['value']))
        if doc['_id'] not in PalavrasCategorizadas.stopwords and len(doc['_id']) > 3 and str(doc['_id']).isalpha() and \
                        doc['_id'] not in tracks:
            palavras.append(dict(text=doc['_id'], weight=doc['value']))
            p += 1

    r = dict(palavras=palavras, qtd_total=p)

    return jsonify(r), 200


@app.route("/tweets/treino", methods=['GET'])
def tweets_treino_get():
    r = dict(data=[])
    db = get_db()
    tweets = db['twitter_treino']
    cursor = tweets.find({})
    for c in cursor:
        r['data'].append(dict(texto=c.get("texto"), sentimento=c.get("sentimento")))
    return jsonify(r), 200


def usuarios_autorizados():
    """ Lista de usuários autorizados a login na aplicação
    :return: dict
    """
    return {'teste': 'teste'}


@app.route("/login", methods=['GET'])
def login():
    token = uuid1()
    r = dict(token=token)
    usuario = request.args.get('usuario', None)
    r['usuario'] = usuario
    senha = request.args.get('senha', None)
    if usuario and senha and usuarios_autorizados().get(usuario, None) and usuarios_autorizados().get(usuario, None) == senha:
        GLOBAL_SESSION[usuario] = str(token)
        return jsonify(r), 200
    else:
        abort(400)


@app.route("/login/validar", methods=['GET'])
def login_validar():
    r = dict(token=uuid1())
    usuario = request.args.get('usuario', None)
    token = request.args.get('token', None)
    if usuario and token and usuarios_autorizados().get(usuario, None) and GLOBAL_SESSION.get(usuario, None) == token:
        return jsonify(r), 200
    else:
        abort(400)

if __name__ == "__main__":
    try:
        #app.run(host='0.0.0.0', port=5000)
        setproctitle.setproctitle('AnaliseTwitterServer')
        logging.basicConfig(level=logging.DEBUG, format=formatolog, datefmt='[%Y-%m-%d %H:%M:%S]', )
        tornadolog.enable_pretty_logging()
        http_server = HTTPServer(WSGIContainer(app))
        http_server.listen(5000, address="127.0.0.1")
        IOLoop.instance().start()

    except (KeyboardInterrupt, Exception) as e:
        # print(e)
        IOLoop.current().stop()
        pass

