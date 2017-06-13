#-*- coding: utf-8 -*-
import re
import threading
from time import sleep

import tweepy
from pymongo import MongoClient

import PalavrasCategorizadas

consumer_key= ""
consumer_secret=""
access_token=""
access_token_secret=""


class BaseTwitterListener(tweepy.StreamListener):

    limite_max = 100
    flag_armazenar = True
    qtd_recuperado = 0
    twitter_stream = None
    tag = track = None
    db = clientDB = collection = pesq_ativa = None
    data_collection = 'twitter_collection'
    sentimento_default = None
    treino = None

    def __init__(self, limite_max=None, sentimento=None, treino=False, api=None):
        """Construtor padrão
        :param limite_max: Limite maximo de twittes a recuperar
        :param api: Twitter API
        """
        tweepy.StreamListener.__init__(self, api)
        if limite_max:
            self.limite_max = limite_max
        self.sentimento_default = sentimento
        self.treino = treino
        if treino:
            self.data_collection = 'twitter_treino'
        self.clientDB = MongoClient('127.0.0.1', 27017)
        self.db = self.clientDB['twitter_db']
        self.pesq_ativa = self.db['pesquisas_ativas']
        self.collection = self.db[self.data_collection]

    def on_status(self, status):
        self.tratar(status)

    def on_error(self, status_code):
        if status_code == 420:
            # returning False in on_data disconnects the stream
            return False

    def classificar_treino(self, texto):
        """Classica o texto de treino com o sentimento adequado
        :param texto: Tweet
        :return: Pos, neg ou None
        """
        sentimento = None
        try:
            neg = pos = 0
            words = texto.split(' ')
            if len(words) < 3:
                return True  # Descarta menos de tres palavras.
            for w in words:

                if w in PalavrasCategorizadas.stopwords:
                    continue
                if w in PalavrasCategorizadas.palavras_positivas:
                    idx = texto.find(w)
                    if re.match("não|nao|ñ", texto[idx - 6: idx]):
                        neg += 1
                    else:
                        pos += 1
                if w in PalavrasCategorizadas.palavras_negativas:
                    neg += 1

            score_t = pos / len(words) - neg / len(words)

            if score_t == 0:
                # sentimento = 'neutro'
                sentimento = None  # ignorando neutros
            elif score_t < 0:
                sentimento = 'neg'
            else:
                sentimento = 'pos'

        except Exception as e:
            pass

        return sentimento

    def tratar(self, status):
        """Trata os status chegando e os formata para armazenamento
        :param status: dict
        :return:
        """
        texto = status.text.strip()
        texto = re.sub('((\n)|(\r))', '', texto)
        if self.treino:
            # Remove os números quando é treino
            expSub = "(@[A-Za-z0-9]+)|(#[A-Za-z0-9]+)|([^A-Za-z \tçéáíóãõúôêâ,;])|(\w+:\/\/\S+)"
        else:
            expSub = "(@[A-Za-z0-9]+)|(#[A-Za-z0-9]+)|([^0-9A-Za-z \tçéáíóãõúôêâ,;])|(\w+:\/\/\S+)"

        texto = ' '.join(re.sub(expSub, " ", texto.lower()).split())

        if status.retweeted is False and texto and not texto.lower().startswith('rt') and \
                        len(texto.split(' ')) > (5 if self.treino else 2):
            # print(texto)
            documento = dict(tag=self.tag, track=','.join(self.track), texto=texto)
            if self.treino:
                sentimento = self.classificar_treino(texto)
                if sentimento:
                    documento['sentimento'] = self.classificar_treino(texto)
                else:
                    return
            self.armazenar(documento)
            if self.qtd_recuperado >= self.limite_max:
                if self.treino is False:
                    self.pesq_ativa.remove({'tag': self.tag})
                if self.twitter_stream:
                    self.twitter_stream.disconnect()
            pass

    def armazenar(self, documento):
        """Armazena no bando de dados os twittes
        :param documento: (dict) {tag, texto, sentimento (neg, pos)}
        :return:
        """
        if self.flag_armazenar:
            #print(documento)
            if self.collection:
                self.collection.insert_one(documento)
            self.qtd_recuperado += 1
            if self.pesq_ativa and self.treino is False:
                self.pesq_ativa.update({'tag': self.tag},
                                       {"$set": {'qtd': self.qtd_recuperado}})

    def coletar(self, tag, track, languages=['pt']):
        """Efetua a coleta dos twittes
        :param tag: Nome da tag para armazenamento no banco com forma de busca
        :param track: Lista de tags que serão utilizadas para recuperar os twittes
        :param languages: array que irá filtrar a linguagem dos textos
        :return: None
        """
        self.tag = tag
        self.track = track
        if self.treino:
            qtd = 0
        else:
            qtd = self.pesq_ativa.count({'tag': self.tag})
        if qtd == 0:

            try:
                auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
                auth.set_access_token(access_token, access_token_secret)
                api = tweepy.API(auth, timeout=10, retry_count=3, retry_delay=10)
                sleep(2)  # as vezes se a rede está com delay alto, dá erro se plugar a api direto a linha abaixo
                self.twitter_stream = tweepy.Stream(auth=api.auth, listener=self)
                self.twitter_stream.filter(track=track,
                                           languages=languages,
                                           async=True)
                if self.treino is False:
                    self.pesq_ativa.insert_one(document={'tag':self.tag, 'qtd':0, 'limite': self.limite_max})
            except Exception as e:
                # print('ERRO: %s' % str(e))
                return

        else:
            return

    def parar(self):
        if self.twitter_stream:
            if self.treino is False:
                self.pesq_ativa.remove({'tag': self.tag})
            self.twitter_stream.disconnect()


class ColetarAvaliacao(threading.Thread):

    sentimento = track = tag = None
    limite = None
    c = None

    def __init__(self, tag, track, limite=1000):
        """ Recupera os twittes de avaliacao
        :param tag: Nome da tag para futura busca e separacao para classificacao
        :param track: palavras e serem buscadas
        :param limite: Limite de twittes a serem armazenados
        """
        threading.Thread.__init__(self)
        self.tag = tag
        self.track = track
        self.limite = limite

    def run(self):
        self.__iniciar()

    def __iniciar(self):
        self.c = BaseTwitterListener(treino=False, limite_max=self.limite)
        self.c.coletar(tag=self.tag, track=self.track)

    def ver_status(self):
        if self.c:
            print('Avaliacao recuperada: %s' % (self.c.qtd_recuperado))

    def parar(self):
        if self.c:
            self.c.parar()
            print('Avaliacao parada! Recuperado: %s'% (self.c.qtd_recuperado))


class ColetarTreino(threading.Thread):

    sentimento = track = None
    limite = None
    c = None

    def __init__(self, sentimento, track, limite=1000):
        threading.Thread.__init__(self)
        self.sentimento = sentimento
        self.track = track
        self.limite = limite

    def run(self):
        self.__iniciar()

    def __iniciar(self):
        self.c = BaseTwitterListener(sentimento=self.sentimento, treino=True, limite_max=self.limite)
        self.c.coletar(tag='treino', track=self.track)

    def ver_status(self):
        if self.c:
            print('Treino: %s - Recuperado: %s' % (self.sentimento, self.c.qtd_recuperado))

    def parar(self):
        if self.c:
            self.c.parar()
            print('Treino: %s - Parado! Recuperado: %s'% (self.sentimento, self.c.qtd_recuperado))


class Menu(object):

    continuar = True
    threads_treino = []
    threads_avaliacao = []

    def main_menu(self):
        while self.continuar:
            print('-----------------------------------')
            print('1 - Iniciar coleta de treino')
            print('2 - Ver status da coleta de treino')
            print('3 - Para coleta de treino')
            print('4 - Iniciar coleta de avaliacao')
            print('5 - Ver status da coleta de avaliacao')
            print('6 - Para coleta de avaliacao')
            print('0 - Sair')
            opcao = input(">>")
            if opcao:
                if opcao == '1':
                    self.coletar_treino()
                elif opcao == '2':
                    self.ver_status_treino()
                elif opcao == '3':
                    self.encerrar_treino()
                elif opcao == '4':
                    self.coletar_avaliacao()
                elif opcao == '5':
                    self.ver_status_avaliacao()
                elif opcao == '6':
                    self.encerrar_avaliacao()
                elif opcao == '0':
                    self.continuar = False
        return

    def coletar_avaliacao(self):
        if self.threads_avaliacao:
            print('Avaliacao jq iniciada!')
            return
        print('\r\n')
        print('Nome da tag')
        tag = input(">>")
        print('Track list (separado por virgulas)')
        track = input(">>")

        if tag and track:
            track = track.split(',')
            print('Iniciando coleta do treinamento...')
            cpaval = ColetarAvaliacao(tag=tag,
                                      limite=100,
                                      track=track)

            cpaval.start()
            self.threads_avaliacao.append(cpaval)
            sleep(1)

    def coletar_treino(self):
        if self.threads_treino:
            print('Treinamento ja iniciado!')
            return
        print('Iniciando coleta do treinamento...')
        cpos = ColetarTreino(sentimento='pos',
                             limite=1000,
                             track=['feliz', 'alegre', 'contente', 'animado', 'parabéns', 'felicidades', 'paz'])
        cneg = ColetarTreino(sentimento='neg',
                             limite=1000,
                             track=['triste', 'medo', 'arrependimento', 'terrorismo',
                                    'ruim', 'depressão', 'morte', 'chato', 'assassinato',
                                    'chacina'])
        cpos.start()
        cneg.start()
        self.threads_treino.append(cpos)
        self.threads_treino.append(cneg)
        sleep(1)

    def ver_status_treino(self):
        for t in self.threads_treino:
            if hasattr(t, 'ver_status'):
                t.ver_status()

    def ver_status_avaliacao(self):
        for t in self.threads_avaliacao:
            if hasattr(t, 'ver_status'):
                t.ver_status()

    def encerrar_treino(self):
        print('Aguardando encerramento das threads...')
        for t in self.threads_treino:
            t.parar()
        for t in self.threads_treino:
            t.join()
        for t in self.threads_treino:
            del t
        self.threads_treino.clear()
        print('Treino encerrado!')

    def encerrar_avaliacao(self):
        print('Aguardando encerramento das threads...')
        for t in self.threads_avaliacao:
            t.parar()
        for t in self.threads_avaliacao:
            t.join()
        for t in self.threads_avaliacao:
            del t
        self.threads_avaliacao.clear()
        print('Avaliacao encerrado!')

if __name__ == '__main__':
    try:
        m = Menu()
        m.main_menu()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Erro %s" % str(e))