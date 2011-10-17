# -*- coding:utf-8 -*-
from sqlite3 import dbapi2 as sqlite
from os import path
import numpy as np
from multiprocessMatrixMultiplication import matrixMultiplication
from sklearn.svm import LinearSVC
class SpectralFeatureAlignment():

    def __init__(self, dbDir, rawDataFolder, sourceDomain, targetDomain):
        self._dbDir = dbDir
        self._sourceDomain = sourceDomain
        self._rawDataFolder = rawDataFolder
        self._targetDomain = targetDomain
        self._tableName = sourceDomain + "to" + targetDomain
        self._connection = sqlite.connect(path.join(dbDir,sourceDomain))
        self._cursor = self._connection.cursor()
        self._lsvc = LinearSVC()

    def _getFeatures(self, maxDIFeatures=500, minFrequency=5):
        features = []
        self._cursor.execute("SELECT term FROM bookstodvd WHERE freqSource + freqTarget >= ?", [minFrequency])
        features = [a[0] for a in self._cursor.fetchall()]
        return features[:maxDIFeatures], features[maxDIFeatures:]

    def _createCooccurrenceMatrix(self, domainIndependentFeatures, domainDependentFeatures):
        domainIndependentFeaturesSet = set(domainIndependentFeatures)
        domainDependentFeaturesSet = set(domainDependentFeatures)
        def __parseFile(filePath):
            with open(filePath, "r") as f:
                for review in f:
                        reviewFeatures = set([tupel.split(":")[0].decode("utf-8") for tupel in review.split()])
                        independentFeatures = reviewFeatures & domainIndependentFeaturesSet
                        dependentFeatures = reviewFeatures & domainDependentFeaturesSet
                        for dependentFeature in dependentFeatures:
                            rowIndex = domainDependentFeatures.index(dependentFeature)
                            for independentFeature in independentFeatures:
                                matrix[rowIndex, domainIndependentFeatures.index(independentFeature)] += 1
                        
        matrix = np.zeros((len(domainDependentFeatures), len(domainIndependentFeatures)))
        __parseFile(path.join(self._rawDataFolder, self._sourceDomain, "positive.review"))
        __parseFile(path.join(self._rawDataFolder, self._sourceDomain, "negative.review"))
        __parseFile(path.join(self._rawDataFolder, self._targetDomain, "positive.review"))
        __parseFile(path.join(self._rawDataFolder, self._targetDomain, "negative.review"))
        return matrix

    def _createSquareAffinityMatrix(self, cooccurrenceMatrix):
       height = np.size(cooccurrenceMatrix, 0) 
       width = np.size(cooccurrenceMatrix, 1) 
       topMatrix = np.zeros((height, height))
       topMatrix = np.concatenate((topMatrix, cooccurrenceMatrix), axis=1)
       bottomMatrix = np.zeros((width,width))
       bottomMatrix = np.concatenate((np.transpose(cooccurrenceMatrix), bottomMatrix), axis=1)
       matrix = np.concatenate((topMatrix, bottomMatrix), axis=0)
       return matrix
   
    def _createDiagonalMatrix(self, squareAffinityMatrix):
        matrix = np.zeros((np.size(squareAffinityMatrix,0),np.size(squareAffinityMatrix, 1)))
        for i,x in enumerate(squareAffinityMatrix):
            rowSum = np.sum(x)
            if rowSum == 0:
                matrix[i][i] = 0     
            else:
                matrix[i][i] = np.sqrt(1.0 / rowSum)
        return matrix

    def _createDocumentVectors(self,domainDependentFeatures, domainIndependentFeatures, domain):
        numDomainDep = len(domainDependentFeatures)
        numDomainIndep = len(domainIndependentFeatures)
        domainDepSet = set(domainDependentFeatures)
        domainIndepSet = set(domainIndependentFeatures)
        documentVectors = []
        classifications = []
        def __parseFile(filePath):
            with open(filePath,"r") as f:
                for review in f:
                    classification = 1 if "#label#:positive" in review else 0
                    domainDepVector = np.zeros(numDomainDep)
                    domainIndepVector = np.zeros(numDomainIndep)
                    reviewFeatures = set([tupel.split(":")[0].decode("utf-8") for tupel in review.split()])
                    domainDepReviewFeatures = domainDepSet & reviewFeatures
                    domainIndepReviewFeatures = domainIndepSet & reviewFeatures
                    for feature in domainIndepReviewFeatures:
                        domainIndepVector[domainIndependentFeatures.index(feature)] = 1
                    for feature in domainDepReviewFeatures:
                        domainDepVector[domainDependentFeatures.index(feature)] = 1
                    documentVectors.append((domainIndepVector,domainDepVector))
                    classifications.append(classification)

        __parseFile(path.join(self._rawDataFolder, domain, "positive.review"))
        __parseFile(path.join(self._rawDataFolder, domain, "negative.review"))
        return documentVectors,classifications 

    def _trainClassifier(self, trainingVectors, classifications):
        self._lsvc.fit(trainingVectors,classifications)

    def _testClassifier(self,testVectors):
        return self._lsvc.predict(testVectors)




    def go(self,K=75, Y=0.6):
        domainIndependentFeatures, domainDependentFeatures = self._getFeatures(300,18)
        numDomainIndep = len(domainIndependentFeatures)
        numDomainDep = len(domainDependentFeatures)
        print "number of independent " + str(numDomainIndep) + " number of dependent " + str(numDomainDep)
        print "creating cooccurrenceMatrix..."
        a = self._createCooccurrenceMatrix(domainIndependentFeatures, domainDependentFeatures)
        print "creating SquareAffinityMatrix..."
        a = self._createSquareAffinityMatrix(a)
        print "creating DiagonalMatrix..."
        b = self._createDiagonalMatrix(a)
        print "multiplying..." 
        c = matrixMultiplication(matrixMultiplication(b,a),b)
        print "calculating eigenvalues and eigenvectors"
        eigenValues, eigenVectors = np.linalg.eig(c)
        print "finding k largest eigenvectors"
        U  = [eigenVectors[:,x].reshape(np.size(eigenVectors,0),1) for x in eigenValues.argsort()[:K]]
        U = np.concatenate(U,axis=1)[:numDomainDep]
        print "training classifier..."
        documentVectors,classifications = self._createDocumentVectors(domainDependentFeatures, domainIndependentFeatures,self._sourceDomain)
        clustering = [vector[1].dot(U).dot(Y).astype(np.float64) for vector in documentVectors]
        trainingVectors = [np.concatenate((documentVectors[x][0],documentVectors[x][1],clustering[x])) for x in range(np.size(documentVectors,axis=0))]
        self._trainClassifier(trainingVectors,classifications)
        print "testing..."
        documentVectors,classificatons = self._createDocumentVectors(domainDependentFeatures, domainIndependentFeatures,self._targetDomain)
        clustering = [vector[1].dot(U).dot(Y).astype(np.float64) for vector in documentVectors]
        testVectors = [np.concatenate((documentVectors[x][0],documentVectors[x][1],clustering[x])) for x in range(np.size(documentVectors,axis=0))]
        results = self._testClassifier(testVectors)
        print np.sum(results[:1000])
        print np.sum(results[1000:])














sfa = SpectralFeatureAlignment("/home/raphael/BachelorThesis/Data","/home/raphael/BachelorThesis/Data/processed_acl", "books", "dvd")
sfa.go()



