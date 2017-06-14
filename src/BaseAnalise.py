import re

import pandas as pd
from pymongo import MongoClient
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.naive_bayes import MultinomialNB


class BaseAnalise():

    tag = None
    twitter_collection = twitter_treino = None
    dfTreino = dfTweets = twitter_analise = pesquisa_analise =None

    def __init__(self, tag):
        self.tag = tag
        self.clientDB = MongoClient('127.0.0.1', 27017)
        self.db = self.clientDB['twitter_db']
        self.twitter_collection = self.db['twitter_collection']
        self.twitter_treino = self.db['twitter_treino']
        self.twitter_analise = self.db['twitter_analise']
        self.pesquisa_analise = self.db['pesquisa_analise']
        self.pesquisa_analise_ativa = self.db['pesquisa_analise_ativa']

    def recuperar_treino(self):
        cursor = self.twitter_treino.find({})
        r = []
        for c in cursor:
            r.append([c.get("texto"), c.get('sentimento')])
        index = [i for i in range(1, len(r) + 1)]
        self.dfTreino = pd.DataFrame(data=r, index=index, columns=['texto', 'sentimento'])

    def recuperar_tweets(self):
        cursor = self.twitter_collection.find({'tag':self.tag})
        r = []
        for c in cursor:
            r.append([c.get("texto")])
        index = [i for i in range(1, len(r) + 1)]
        self.dfTweets = pd.DataFrame(data=r, index=index, columns=['texto'])

    def __split_into_lemmas(self, texto):
        bigram_vectorizer = CountVectorizer(ngram_range=(1, 3), token_pattern=r'\b\w+\b', min_df=1)
        analyze = bigram_vectorizer.build_analyzer()
        return analyze(texto)

    def get_stop_words(self):

         return 'a, agora, ainda, alguém, algum, alguma, algumas, alguns, ampla, amplas, amplo, amplos, ante, antes, ' \
                'ao, aos, após, aquela, aquelas, aquele, aqueles, aquilo, as, até, através, cada, coisa, coisas, com, ' \
                'como, contra, contudo, da, daquele, daqueles, das, de, dela, delas, dele, deles, ' \
                'depois, dessa, dessas, desse, desses, desta, destas, deste, deste, destes, deve, devem, devendo,' \
                ' dever, deverá, deverão, deveria, deveriam, devia, deviam, disse, disso, disto, dito, diz, dizem,' \
                ' do, dos, e, é, ela, elas, ele, eles, em, enquanto, entre, era, essa, essas, esse, esses, esta, está, ' \
                'estamos, estão, estas, estava, estavam, estávamos, este, estes, estou, eu, fazendo, fazer, feita, ' \
                'feitas, feito, feitos, foi, for, foram, fosse, fossem, grande, grandes, há, isso, isto, já, la, lá, ' \
                'lhe, lhes, lo, mas, me, mesma, mesmas, mesmo, mesmos, meu, meus, minha, minhas, muita, muitas, muito, ' \
                'muitos, na, não, nas, nem, nenhum, nessa, nessas, nesta, nestas, ninguém, no, nos, nós, nossa, nossas, ' \
                'nosso, nossos, num, numa, nunca, o, os, ou, outra, outras, outro, outros, para, pela, pelas, pelo,' \
                ' pelos, pequena, pequenas, pequeno, pequenos, per, perante, pode, pude, podendo, poder, poderia, ' \
                'poderiam, podia, podiam, pois, por, porém, porque, posso, pouca, poucas, pouco, poucos, primeiro, ' \
                'primeiros, própria, próprias, próprio, próprios, quais, qual, quando, quanto, quantos, que, quem, ' \
                'são, se, seja, sejam, sem, sempre, sendo, será, serão, seu, seus, si, sido, só, sob, sobre, sua, ' \
                'suas, talvez, também, tampouco, te, tem, tendo, tenha, ter, teu, teus, ti, tido, tinha, tinham, toda, ' \
                'todas, todavia, todo, todos, tu, tua, tuas, tudo, última, últimas, último, últimos, um, uma, umas, ' \
                'uns, vendo, ver, vez, vindo, vir, vos, vós'

    def analisar(self):
        try:
            self.pesquisa_analise_ativa.insert({"tag": self.tag})

            # Recupera os twittes
            self.recuperar_treino()
            self.recuperar_tweets()

            # Remove qualquer tweet e analise já feita
            self.pesquisa_analise.remove({"tag": self.tag})
            self.twitter_analise.remove({"tag": self.tag})
            # --------------------------------------------

            # Pegar as stop_words em pt
            fwords = self.get_stop_words()
            palavras = re.sub('\s', '', fwords).split(',')
            stop_words = frozenset(palavras)
            bow_transformer = CountVectorizer(analyzer=self.__split_into_lemmas,
                                              stop_words=stop_words,
                                              strip_accents='ascii').fit(self.dfTreino['texto'])

            text_bow = bow_transformer.transform(self.dfTreino['texto'])
            tfidf_transformer = TfidfTransformer().fit(text_bow)
            tfidf = tfidf_transformer.transform(text_bow)
            text_tfidf = tfidf_transformer.transform(text_bow)
            classifier_nb = MultinomialNB(class_prior=[0.30, 0.70]).fit(text_tfidf, self.dfTreino['sentimento'])


            qtd_pos = 0
            qtd_neg = 0
            total = 0

            # Analisa e guarda no banco de dados
            for _, tweet in self.dfTweets.iterrows():
                try:
                    bow_tweet = bow_transformer.transform(tweet)
                    tfidf_tweet = tfidf_transformer.transform(bow_tweet)
                    prob = round(classifier_nb.predict_proba(tfidf_tweet)[0][1], 2) * 10
                    sentimento = classifier_nb.predict(tfidf_tweet)[0]
                    documento = {'tag': self.tag,
                                 'texto': tweet.values[0],
                                 'sentimento': sentimento,
                                 'prob': prob}
                    self.twitter_analise.insert(documento)
                    if sentimento == 'pos':
                        qtd_pos +=1
                    else:
                        qtd_neg += 1
                    total += 1
                except Exception as e:
                    documento = {'tag': self.tag, 'texto': tweet.values[0], 'classe': '-', 'prob': '-'}
                    self.twitter_analise.insert(documento)

            if self.pesquisa_analise.count({"tag": self.tag}) == 0:
                self.pesquisa_analise.insert({'tag': self.tag, 'qtd_pos': qtd_pos, 'qtd_neg': qtd_neg, 'total': total})
            else:
                self.pesquisa_analise.update({'tag': self.tag},
                                            {"$set": {'qtd_pos': qtd_pos, 'qtd_neg': qtd_neg, 'total': total}})

        except Exception as e:
            pass
        finally:
            self.pesquisa_analise_ativa.remove({"tag": self.tag})


if __name__ == '__main__':
    c = BaseAnalise('trump')
    c.analisar()
