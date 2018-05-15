# Copyright 2017 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
  Created on May 8, 2018

  @author: talbpaul

  Base subclass definition for all supported type of ROM aka Surrogate Models etc
  Previous module notes:
  here we intend ROM as super-visioned learning,
  where we try to understand the underlying model by a set of labeled sample
  a sample is composed by (feature,label) that is easy translated in (input,output)
"""
#for future compatibility with Python 3--------------------------------------------------------------
from __future__ import division, print_function, unicode_literals, absolute_import
import warnings
warnings.simplefilter('default',DeprecationWarning)
#End compatibility block for Python 3----------------------------------------------------------------

from numpy import average
import sys
if sys.version_info.major > 2:
  from crow_modules.distribution1Dpy3 import CDF
else:
  from crow_modules.distribution1Dpy2 import CDF

#External Modules------------------------------------------------------------------------------------
import numpy as np
import abc
import copy
#External Modules End--------------------------------------------------------------------------------

#Internal Modules------------------------------------------------------------------------------------
from utils import utils,mathUtils
import MessageHandler

interpolationND = utils.findCrowModule('interpolationND')
#Internal Modules End--------------------------------------------------------------------------------

class supervisedLearning(utils.metaclass_insert(abc.ABCMeta),MessageHandler.MessageUser):
  """
    This is the general interface to any supervisedLearning learning method.
    Essentially it contains a train method and an evaluate method
  """
  returnType       = ''    # this describe the type of information generated the possibility are 'boolean', 'integer', 'float'
  qualityEstType   = []    # this describe the type of estimator returned known type are 'distance', 'probability'. The values are returned by the self.__confidenceLocal__(Features)
  ROMtype          = ''    # the broad class of the interpolator
  ROMmultiTarget   = False #
  ROMtimeDependent = False # is this ROM able to treat time-like (any monotonic variable) explicitly in its formulation?

  @staticmethod
  def checkArrayConsistency(arrayIn,isDynamic=False):
    """
      This method checks the consistency of the in-array
      @ In, arrayIn, object,  It should be an array
      @ In, isDynamic, bool, optional, is Dynamic?
      @ Out, (consistent, 'error msg'), tuple, tuple[0] is a bool (True -> everything is ok, False -> something wrong), tuple[1], string ,the error mesg
    """
    #checking if None provides a more clear message about the problem
    if arrayIn is None:
      return (False,' The object is None, and contains no entries!')
    if type(arrayIn).__name__ == 'list':
      if isDynamic:
        for cnt, elementArray in enumerate(arrayIn):
          resp = supervisedLearning.checkArrayConsistency(elementArray)
          if not resp[0]:
            return (False,' The element number '+str(cnt)+' is not a consistent array. Error: '+resp[1])
      else:
        return (False,' The list type is allowed for dynamic ROMs only')
    else:
      if type(arrayIn).__name__ not in ['ndarray','c1darray']:
        return (False,' The object is not a numpy array. Got type: '+type(arrayIn).__name__)
      if len(np.asarray(arrayIn).shape) > 1:
        return(False, ' The array must be 1-d. Got shape: '+str(np.asarray(arrayIn).shape))
    return (True,'')

  def __init__(self,messageHandler,**kwargs):
    """
      A constructor that will appropriately initialize a supervised learning object
      @ In, messageHandler, MessageHandler object, it is in charge of raising errors, and printing messages
      @ In, kwargs, dict, an arbitrary list of kwargs
      @ Out, None
    """
    self.printTag          = 'Supervised'
    self.messageHandler    = messageHandler
    self._dynamicHandling = False
    #booleanFlag that controls the normalization procedure. If true, the normalization is performed. Default = True
    if kwargs != None:
      self.initOptionDict = kwargs
    else:
      self.initOptionDict = {}
    if 'Features' not in self.initOptionDict.keys():
      self.raiseAnError(IOError,'Feature names not provided')
    if 'Target'   not in self.initOptionDict.keys():
      self.raiseAnError(IOError,'Target name not provided')
    self.features = self.initOptionDict['Features'].split(',')
    self.target   = self.initOptionDict['Target'  ].split(',')
    self.initOptionDict.pop('Target')
    self.initOptionDict.pop('Features')
    self.verbosity = self.initOptionDict['verbosity'] if 'verbosity' in self.initOptionDict else None
    for target in self.target:
      if self.features.count(target) > 0:
        self.raiseAnError(IOError,'The target "'+target+'" is also in the feature space!')
    #average value and sigma are used for normalization of the feature data
    #a dictionary where for each feature a tuple (average value, sigma)
    self.muAndSigmaFeatures = {}
    #these need to be declared in the child classes!!!!
    self.amITrained         = False

  def initialize(self,idict):
    """
      Initialization method
      @ In, idict, dict, dictionary of initialization parameters
      @ Out, None
    """
    pass #Overloaded by (at least) GaussPolynomialRom

  def train(self,tdict):
    """
      Method to perform the training of the supervisedLearning algorithm
      NB.the supervisedLearning object is committed to convert the dictionary that is passed (in), into the local format
      the interface with the kernels requires. So far the base class will do the translation into numpy
      @ In, tdict, dict, training dictionary
      @ Out, None
    """
    if type(tdict) != dict:
      self.raiseAnError(TypeError,'In method "train", the training set needs to be provided through a dictionary. Type of the in-object is ' + str(type(tdict)))
    names, values  = list(tdict.keys()), list(tdict.values())
    ## This is for handling the special case needed by SKLtype=*MultiTask* that
    ## requires multiple targets.

    targetValues = []
    for target in self.target:
      if target in names:
        targetValues.append(values[names.index(target)])
      else:
        self.raiseAnError(IOError,'The target '+target+' is not in the training set')

    #FIXME: when we do not support anymore numpy <1.10, remove this IF STATEMENT
    if int(np.__version__.split('.')[1]) >= 10:
      targetValues = np.stack(targetValues, axis=-1)
    else:
      sl = (slice(None),) * np.asarray(targetValues[0]).ndim + (np.newaxis,)
      targetValues = np.concatenate([np.asarray(arr)[sl] for arr in targetValues], axis=np.asarray(targetValues[0]).ndim)

    # construct the evaluation matrixes
    featureValues = np.zeros(shape=(len(targetValues),len(self.features)))
    for cnt, feat in enumerate(self.features):
      if feat not in names:
        self.raiseAnError(IOError,'The feature sought '+feat+' is not in the training set')
      else:
        valueToUse = values[names.index(feat)]
        resp = self.checkArrayConsistency(valueToUse, self.isDynamic())
        if not resp[0]:
          self.raiseAnError(IOError,'In training set for feature '+feat+':'+resp[1])
        valueToUse = np.asarray(valueToUse)
        if len(valueToUse) != featureValues[:,0].size:
          self.raiseAWarning('feature values:',featureValues[:,0].size,tag='ERROR')
          self.raiseAWarning('target values:',len(valueToUse),tag='ERROR')
          self.raiseAnError(IOError,'In training set, the number of values provided for feature '+feat+' are != number of target outcomes!')
        self._localNormalizeData(values,names,feat)
        # valueToUse can be either a matrix (for who can handle time-dep data) or a vector (for who can not)
        featureValues[:,cnt] = ( (valueToUse[:,0] if len(valueToUse.shape) > 1 else valueToUse[:]) - self.muAndSigmaFeatures[feat][0])/self.muAndSigmaFeatures[feat][1]
    self.__trainLocal__(featureValues,targetValues)
    self.amITrained = True

  def _localNormalizeData(self,values,names,feat):
    """
      Method to normalize data based on the mean and standard deviation.  If undesired for a particular ROM,
      this method can be overloaded to simply pass (see, e.g., GaussPolynomialRom).
      @ In, values, list, list of feature values (from tdict)
      @ In, names, list, names of features (from tdict)
      @ In, feat, list, list of features (from ROM)
      @ Out, None
    """
    self.muAndSigmaFeatures[feat] = mathUtils.normalizationFactors(values[names.index(feat)])

  def confidence(self,edict):
    """
      This call is used to get an estimate of the confidence in the prediction.
      The base class self.confidence will translate a dictionary into numpy array, then call the local confidence
      @ In, edict, dict, evaluation dictionary
      @ Out, confidence, float, the confidence
    """
    if type(edict) != dict:
      self.raiseAnError(IOError,'method "confidence". The inquiring set needs to be provided through a dictionary. Type of the in-object is ' + str(type(edict)))
    names, values   = list(edict.keys()), list(edict.values())
    for index in range(len(values)):
      resp = self.checkArrayConsistency(values[index], self.isDynamic())
      if not resp[0]:
        self.raiseAnError(IOError,'In evaluate request for feature '+names[index]+':'+resp[1])
    featureValues = np.zeros(shape=(values[0].size,len(self.features)))
    for cnt, feat in enumerate(self.features):
      if feat not in names:
        self.raiseAnError(IOError,'The feature sought '+feat+' is not in the evaluate set')
      else:
        resp = self.checkArrayConsistency(values[names.index(feat)], self.isDynamic())
        if not resp[0]:
          self.raiseAnError(IOError,'In training set for feature '+feat+':'+resp[1])
        featureValues[:,cnt] = values[names.index(feat)]
    return self.__confidenceLocal__(featureValues)

  def evaluate(self,edict):
    """
      Method to perform the evaluation of a point or a set of points through the previous trained supervisedLearning algorithm
      NB.the supervisedLearning object is committed to convert the dictionary that is passed (in), into the local format
      the interface with the kernels requires.
      @ In, edict, dict, evaluation dictionary
      @ Out, evaluate, numpy.array, evaluated points
    """
    if type(edict) != dict:
      self.raiseAnError(IOError,'method "evaluate". The evaluate request/s need/s to be provided through a dictionary. Type of the in-object is ' + str(type(edict)))
    names, values  = list(edict.keys()), list(edict.values())
    for index in range(len(values)):
      resp = self.checkArrayConsistency(values[index], self.isDynamic())
      if not resp[0]:
        self.raiseAnError(IOError,'In evaluate request for feature '+names[index]+':'+resp[1])
    # construct the evaluation matrix
    featureValues = np.zeros(shape=(values[0].size,len(self.features)))
    for cnt, feat in enumerate(self.features):
      if feat not in names:
        self.raiseAnError(IOError,'The feature sought '+feat+' is not in the evaluate set')
      else:
        resp = self.checkArrayConsistency(values[names.index(feat)], self.isDynamic())
        if not resp[0]:
          self.raiseAnError(IOError,'In training set for feature '+feat+':'+resp[1])
        featureValues[:,cnt] = ((values[names.index(feat)] - self.muAndSigmaFeatures[feat][0]))/self.muAndSigmaFeatures[feat][1]
    return self.__evaluateLocal__(featureValues)

  def reset(self):
    """
      Reset ROM
    """
    self.amITrained = False
    self.__resetLocal__()

  def returnInitialParameters(self):
    """
      override this method to return the fix set of parameters of the ROM
      @ In, None
      @ Out, iniParDict, dict, initial parameter dictionary
    """
    iniParDict = dict(list(self.initOptionDict.items()) + list({'returnType':self.__class__.returnType,'qualityEstType':self.__class__.qualityEstType,'Features':self.features,
                                             'Target':self.target,'returnType':self.__class__.returnType}.items()) + list(self.__returnInitialParametersLocal__().items()))
    return iniParDict

  def returnCurrentSetting(self):
    """
      return the set of parameters of the ROM that can change during simulation
      @ In, None
      @ Out, currParDict, dict, current parameter dictionary
    """
    currParDict = dict({'Trained':self.amITrained}.items() + self.__CurrentSettingDictLocal__().items())
    return currParDict

  def printXMLSetup(self,outFile,options={}):
    """
      Allows the SVE to put whatever it wants into an XML file only once (right before calling pringXML)
      @ In, outFile, Files.File, either StaticXMLOutput or DynamicXMLOutput file
      @ In, options, dict, optional, dict of string-based options to use, including filename, things to print, etc
      @ Out, None
    """
    outFile.addScalar('ROM',"type",self.printTag)
    self._localPrintXMLSetup(outFile,options)

  def _localPrintXMLSetup(self,outFile,pivotVal,options={}):
    """
      Specific local method for printing anything desired to xml file at the begin of the print.
      Overwrite in inheriting classes.
      @ In, outFile, Files.File, either StaticXMLOutput or DynamicXMLOutput file
      @ In, options, dict, optional, dict of string-based options to use, including filename, things to print, etc
      @ Out, None
    """
    pass

  def printXML(self,outFile,pivotVal,options={}):
    """
      Allows the SVE to put whatever it wants into an XML to print to file.
      @ In, outFile, Files.File, either StaticXMLOutput or DynamicXMLOutput file
      @ In, pivotVal, float, value of pivot parameters to use in printing if dynamic
      @ In, options, dict, optional, dict of string-based options to use, including filename, things to print, etc
      @ Out, None
    """
    self._localPrintXML(outFile,pivotVal,options)

  def _localPrintXML(self,node,options={}):
    """
      Specific local method for printing anything desired to xml file.  Overwrite in inheriting classes.
      @ In, outFile, Files.File, either StaticXMLOutput or DynamicXMLOutput file
      @ In, options, dict, optional, dict of string-based options to use, including filename, things to print, etc
      @ Out, None
    """
    outFile.addScalar('ROM',"noInfo",'ROM of type '+str(self.printTag.strip())+' has no special output options.')

  def isDynamic(self):
    """
      This method is a utility function that tells if the relative ROM is able to
      treat dynamic data (e.g. time-series) on its own or not (Primarly called by LearningGate)
      @ In, None
      @ Out, isDynamic, bool, True if the ROM is able to treat dynamic data, False otherwise
    """
    return self._dynamicHandling

  def reseed(self,seed):
    """
      Used to reset the seed of the ROM.  By default does nothing; overwrite in the inheriting classes as needed.
      @ In, seed, int, new seed to use
      @ Out, None
    """
    return

  @abc.abstractmethod
  def __trainLocal__(self,featureVals,targetVals):
    """
      Perform training on samples in featureVals with responses y.
      For an one-class model, +1 or -1 is returned.
      @ In, featureVals, {array-like, sparse matrix}, shape=[n_samples, n_features],
        an array of input feature values
      @ Out, targetVals, array, shape = [n_samples], an array of output target
        associated with the corresponding points in featureVals
    """

  @abc.abstractmethod
  def __confidenceLocal__(self,featureVals):
    """
      This should return an estimation of the quality of the prediction.
      This could be distance or probability or anything else, the type needs to be declared in the variable cls.qualityEstType
      @ In, featureVals, 2-D numpy array , [n_samples,n_features]
      @ Out, __confidenceLocal__, float, the confidence
    """

  @abc.abstractmethod
  def __evaluateLocal__(self,featureVals):
    """
      @ In,  featureVals, np.array, 2-D numpy array [n_samples,n_features]
      @ Out, targetVals , np.array, 1-D numpy array [n_samples]
    """

  @abc.abstractmethod
  def __resetLocal__(self):
    """
      Reset ROM. After this method the ROM should be described only by the initial parameter settings
      @ In, None
      @ Out, None
    """

  @abc.abstractmethod
  def __returnInitialParametersLocal__(self):
    """
      Returns a dictionary with the parameters and their initial values
      @ In, None
      @ Out, params, dict,  dictionary of parameter names and initial values
    """

  @abc.abstractmethod
  def __returnCurrentSettingLocal__(self):
    """
      Returns a dictionary with the parameters and their current values
      @ In, None
      @ Out, params, dict, dictionary of parameter names and current values
    """
