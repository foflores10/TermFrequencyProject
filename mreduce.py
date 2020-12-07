from pyspark import SparkContext
from pyspark.conf import SparkConf
from operator import add
from math import log
from math import sqrt
import os

#functions to be used by combineByKey to combine as list
def c1(a):
    return [a]
def c2(a, b):
    a.append(b)
    return a
def c3(a, b):
    a.extend(b)
    return a

#functions to be used in RDD calculations
def f1(a):
    a = a.split(' ')
    b = []
    for term in a:
        if term == a[0]:
            continue
        b.append((term, a[0]))
    return b
def f2(a):
    query = dict(a[1])
    numer = 0
    denom1 = 0
    denom2 = 0
    for pair in a[0]:
        denom1 = denom1 + (pair[1] * pair[1])
        if query.get(pair[0]) != None:
            numer = numer + (pair[1] * query[pair[0]])
    for pair in a[1]:
        denom2 = denom2 + (pair[1] * pair[1])
    return (numer/(sqrt(denom1)*sqrt(denom2)))

#computes tf-idf matrix
def tfidf(sc, data_path):
    #imports data and caches to memory
    tfidf_rdd = sc.textFile(data_path).cache()

    #takes count of total documents
    total_docs = tfidf_rdd.count()

    #maps data into (term, doc_id) and caches to memory
    tfidf_rdd = tfidf_rdd.flatMap(f1).cache()

    #filters empty characters and caches to memory
    temp_tf_rdd = tfidf_rdd.filter(lambda a: a[0] != '' and a[0] != ' ' and a[0] != '\n').cache()
    
    #filters any unused terms and caches to memory
    tfidf_rdd = tfidf_rdd.filter(lambda a: a[0].startswith('dis_') or a[0].startswith('gene_')).cache()

    #combines data into (term, [doc_id, doc_id2...]), maps it to (term, idf), and caches to memory
    idf_rdd = tfidf_rdd.combineByKey(c1, c2, c3)
    idf_rdd = idf_rdd.map(lambda a: (a[0], log(total_docs/len(set(a[1])), 10))).cache()

    #maps data to ((term, doc_id), 1), reduces it to compute term count per document, and caches to memory
    tf_rdd = tfidf_rdd.map(lambda a: ((a[0], a[1]), 1))
    tf_rdd = tf_rdd.reduceByKey(add).cache()

    #maps data to (doc_id, 1), reduces it to count words per document, and caches to memory
    temp_tf_rdd = temp_tf_rdd.map(lambda a: (a[1],1))
    temp_tf_rdd = temp_tf_rdd.reduceByKey(add).cache()

    #maps data to (doc_id,(word, term)) and joins it with temp_tf_rdd
    #which contains word count per document
    tf_rdd = tf_rdd.map(lambda a: (a[0][1],(a[0][0], a[1])))
    tf_rdd = tf_rdd.join(temp_tf_rdd)

    #maps data to (word,(doc_id, tf))
    tf_rdd = tf_rdd.map(lambda a: (a[1][0][0], (a[0],a[1][0][1]/a[1][1]))).cache()

    #joins tf_rdd and idf_rdd
    tfidf_rdd = tf_rdd.join(idf_rdd)

    #maps data to (word, (doc_id, tfidf)), combines it to
    #(word, [(doc_id, tfidf), (doc_id2, tfidf2)...]), and caches to memory
    tfidf_rdd = tfidf_rdd.mapValues(lambda a: (a[0][0], a[0][1]*a[1])).combineByKey(c1, c2, c3).cache()

    return tfidf_rdd

#computes relevance scores
def similarity(sc, tfidf_rdd, query):
    #checks query term against matrix to see if it exists in data
    output = tfidf_rdd.filter(lambda a: a[0] == query).collect()
    if len(output) == 0:
        return output
    
    #filters out query term from matrix and caches matrix
    tfidf_rdd = tfidf_rdd.filter(lambda a: a[0] != query).mapValues(lambda a: (a, output[0][1])).cache()

    #calculates similarity, filters out 0 scores, sorts in descending order, and caches to memory
    similarity_rdd = tfidf_rdd.mapValues(f2).filter(lambda a: a[1] != 0).sortBy(lambda a: a[1], False)\
        .cache()

    return (similarity_rdd.collect())

def main():
    #spark configuration options
    conf=SparkConf()\
    .setMaster("local[*]")\
    .setAppName("ttr")\
    .setExecutorEnv("spark.executor.memory","4g")\
    .setExecutorEnv("spark.driver.memory","4g")

    #starts spark context
    sc = SparkContext(conf=conf).getOrCreate()
    
    #data location
    data_path = "data/project2_demo.txt"

    #compute tf-idf matrix
    tfidf_rdd = tfidf(sc, data_path)
    tfidf_rdd.cache()

    #clears screen of spark context startup notifications
    os.system('clear')

    #interface
    done = False
    while not done:
        print("\nEnter a term to see its relevance to all terms in the TF-IDF matrix.")
        query = input("\nTerm: ")
        output = similarity(sc, tfidf_rdd, query)
        if len(output) == 0:
            print("\nTerm not found, try again!")
            continue
        print(f"\nRelevance scores for '{query}': (term, score)\n")
        for a in output:
            print(f"\t{a[0]}, {a[1]}")
        while True:
            answer = input("Would you like to try another term? ('y' = yes, 'n' = no): ")
            if answer == 'n':
                done = True
                break
            elif answer == 'y':
                os.system('clear')
                break
            else:
                print("try again!")
    
    #stops spark context
    sc.stop()
    
if __name__ == "__main__":
    main()