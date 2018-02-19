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
Created on Apr 20, 2015

@author: talbpaul
"""
#for future compatibility with Python 3--------------------------------------------------------------
from __future__ import division, print_function, unicode_literals, absolute_import
import warnings
warnings.simplefilter('default',DeprecationWarning)
if not 'xrange' in dir(__builtins__):
  xrange = range
#End compatibility block for Python 3----------------------------------------------------------------

#External Modules------------------------------------------------------------------------------------
import sys
import time
import bisect
#External Modules End--------------------------------------------------------------------------------

#Internal Modules------------------------------------------------------------------------------------
from utils import utils
#Internal Modules End--------------------------------------------------------------------------------


#custom exceptions
class NoMoreSamplesNeeded(GeneratorExit):
  """
    Custom exception class for no more samples
  """
  pass

"""
HOW THIS MODULE WORKS

The intention is for a single instance of the MessageHandler class to exist in any simulation.
Currently, that instance is created in the Simulation initialization and propogated through
all the RAVEN objects.  This usually happens by passing it to BaseClass.readXML, but for
objects that don't inherit from BaseClass, the messageHandler instance should be passed
and set via instantiation or initialization.  The appropriate class member to point at the
messageHandler instance reference is "self.messageHandler," for reasons that will be made clear
with the  MessageUser superclass.

While an object can access the messageHandler to raise messages and errors, for convienience
we provide the MessageUser superclass, which BaseType and (almost?) all other Raven objects
inherit from.  This provides simplistic hooks for a developer to raise an error or message
with the standard message priorities, as

self.raiseAnError(IOError,'Input value is invalid:',value)

There are currently 4 verbosity levels/message priorities.  They are:
 - silent: only errors are displayed
 - quiet : errors and warnings are displayed
 - all   : (default) errors, warnings, and messages are displayed
 - debug : errors, warnings, messages, and debug messages are displayed

The developer can change the priority level of their raised messages through the 'verbosity'
keyword.  For example,

self.raiseAMessage('Hello, World', verbosity='silent')

will be printed along with errors if the simulation verbosity is set to 'silent', as well as
all other levels.

Additionally, other print options can be added. For example,

self.raiseATiming('jobID "12" action "finishedCollect")

will add a timing note to the output only if "timing" messages are requested in Simulation attributes.


TL;DR: MessageUser is a superclass that gives access to hooks to the simulation's MessageHandler
instance, while the MessageHandler is an output stream control tool.
"""

class MessageUser(object):
  """
    Inheriting from this class grants access to methods used by the MessageHandler.
    In order to work properly, a subclass of this superclass should have a member
    'self.messageHandler' that references a MessageHandler instance.

    Note that verbosity is handled by pointing "raiseA*" methods to either a message producer (error, warning, etc)
    or the "null" method, which simply does nothing.  If the developer desires to bypass the verbosity filter,
    they can directly call the _RAVEN_* methods.

    Also note that care should be taken when assigning to "self" here, as this namespace is shared with all
    inheriting entities.
  """
  def _RAVEN_error(self,etype,*args,**kwargs):
    """
      Raises an error. By default shows in all verbosity levels.
      @ In, etype, Exception, Exception class to raise (e.g. IOError)
      @ In, *args, dict, comma-seperated list of things to put in message (as print() function)
      @ In, **kwargs, dict, optional arguments, which can be:
                            verbosity, the priority of the message (default 'silent')
                            tag, the message label (default 'ERROR')
      @ Out, None
    """
    # adjust traceback depending on verbosity
    if self._RAVEN_verbosity < 3:
      # TODO this changes the traceback at the system level!  Is this okay, or do we want more local control?
      sys.tracebacklimit=0
    tag       = kwargs.get('tag'      ,'ERROR' )
    color     = kwargs.get('color'    ,None     )
    msg = ' '.join(str(a) for a in args)
    self.messageHandler.error(self,etype,msg,str(tag),color)

  def _RAVEN_warning(self,*args,**kwargs):
    """
      Prints a warning. By default shows in 'quiet', 'all', and 'debug'
      @ In, *args, dict, comma-seperated list of things to put in message (as print() function)
      @ In, **kwargs, dict, optional arguments, which can be:
                            verbosity, the priority of the message (default 'quiet')
                            tag, the message label (default 'Warning')
      @ Out, None
    """
    tag       = kwargs.get('tag'      ,'Warning')
    color     = kwargs.get('color'    ,None     )
    msg = ' '.join(str(a) for a in args)
    self.messageHandler.message(self,msg,str(tag),color)

  def _RAVEN_message(self,*args,**kwargs):
    """
      Prints a message. By default shows in 'all' and 'debug'
      @ In, *args, dict, comma-seperated list of things to put in message (as print() function)
      @ In, **kwargs, dict, optional arguments, which can be:
                            verbosity, the priority of the message (default 'all')
                            tag, the message label (default 'Message')
      @ Out, None
    """
    tag        = kwargs.get('tag'       ,'Message')
    color      = kwargs.get('color'     ,None     )
    forcePrint = kwargs.get('forcePrint',False     )
    msg = ' '.join(str(a) for a in args)
    self.messageHandler.message(self,msg,str(tag),color,forcePrint=forcePrint)

  def _RAVEN_debug(self,*args,**kwargs):
    """
      Prints a debug message. By default shows only in 'debug'
      @ In, *args, dict, comma-seperated list of things to put in message (as print() function)
      @ In, **kwargs, dict, optional arguments, which can be:
                            verbosity, the priority of the message (default 'debug')
                            tag, the message label (default 'DEBUG')
      @ Out, None
    """
    tag       = kwargs.get('tag'      ,'DEBUG')
    color     = kwargs.get('color'    ,None   )
    msg = ' '.join(str(a) for a in args)
    self.messageHandler.message(self,msg,str(tag),color)

  def _RAVEN_timing(self,*args,**kwargs):
    """
      Prints a timing message.
      Timing messages are quite specifically templated.  They should be key words followed by values in quotataion marks;
      for example:
      self.raiseATiming('jobID "self.prefix" status "PASS" residual "6.2"')
      @ In, *args, dict, comma-seperated list of things to put in message (as print() function)
      @ In, **kwargs, dict, optional arguments, which can be:
                            verbosity, the priority of the message (default 'debug')
                            tag, the message label (default 'DEBUG')
      @ Out, None
    """
    tag   = kwargs.get('tag'  , 'TIMING')
    color = kwargs.get('color', None    )
    msg = ' '.join(str(a) for a in args)
    self.messageHandler.message(self,msg,str(tag),color)

  def getLocalVerbosity(self,default=None):
    """
      Attempts to learn the local verbosity level of itself
      @ In, default, string, optional, the verbosity level to return if not found
      @ Out, verbosity, string, verbosity type (e.g. 'all')
    """
    return self._RAVEN_verbosity
    #if hasattr(self,'verbosity'):
    #  return self.verbosity
    #else:
    #  return default

  def setLocalVerbosity(self,verbosity,**options):
    """
      Sets the entity's verbosity.  Redirects debug, warning, messages, etc based on verbosity and options.
      Must be called before writing any messages.
      @ In, verbosity, string, desired verbosity level (silent, quiet, all, debug)
      @ In, options, dict, optional, additional keywords as {str:bool} to enable (e.g. {'timing':True})
      @ Out, handler, MessageHandler, instance of the message handler
    """
    # set general verbosity first
    ## if a verbosity level is desired it points to the appropriate method; otherwise, it points at "null"
    numVerbosity = self.messageHandler.getVerbosityCode(verbosity)
    ## store the verbosity locally
    self._RAVEN_verbosity = numVerbosity
    ## fully enabled, "debug" mode
    if numVerbosity == 3:
      self.raiseADebug   = self._RAVEN_debug
      self.raiseAMessage = self._RAVEN_message
      self.raiseAWarning = self._RAVEN_warning
      self.raiseAnError  = self._RAVEN_error
    ## no debug, "all" mode
    elif numVerbosity == 2:
      self.raiseADebug   = self.null
      self.raiseAMessage = self._RAVEN_message
      self.raiseAWarning = self._RAVEN_warning
      self.raiseAnError  = self._RAVEN_error
    ## warnings and errors, "quiet" mode
    elif numVerbosity == 1:
      self.raiseADebug   = self.null
      self.raiseAMessage = self.null
      self.raiseAWarning = self._RAVEN_warning
      self.raiseAnError  = self._RAVEN_error
    ## only errors, "silent" mode
    elif numVerbosity == 0:
      self.raiseADebug   = self.null
      self.raiseAMessage = self.null
      self.raiseAWarning = self.null
      self.raiseAnError  = self._RAVEN_error
    # now, set optional settings
    ## timing statements
    if options.get('timing',False):
      self.raiseATiming = self._RAVEN_timing
    else:
      self.raiseATiming = self.null

  def _RAVEN_null(self,*args,**kwargs):
    """
      Does nothing.  Used for redirecting verbosities.
      @ In, args, list, optional, unused
      @ In, kwargs, dict, optional, unused
    """
    pass

#
#
#
#
class MessageHandler(object):
  """
    Class for handling messages, warnings, and errors in RAVEN.  One instance of this
    class should be created at the start of the Simulation and propagated through
    the readMoreXML function of the BaseClass, and initialization of other classes.
  """
  def __init__(self):
    """
      Init of class
      @ In, None
      @ Out, None
    """
    self.starttime    = time.time()
    self.printTag     = 'MESSAGE HANDLER'
    self.printTime    = True
    self.inColor      = False
    self.verbCode     = {'silent':0, 'quiet':1, 'all':2, 'debug':3}
    self.colorDict    = {'debug':'yellow', 'message':'neutral', 'warning':'magenta', 'error':'red', 'timing','green'}
    self.colors={
      'neutral' : '\033[0m',
      'red'     : '\033[31m',
      'green'   : '\033[32m',
      'yellow'  : '\033[33m',
      'blue'    : '\033[34m',
      'magenta' : '\033[35m',
      'cyan'    : '\033[36m'}
    self.warnings     = [] #collection of warnings that were raised during this run
    self.warningCount = [] #count of the collections of warning above

  def initialize(self,initDict):
    """
      Initializes basic instance attributes
      @ In, initDict, dict, dictionary of global options
      @ Out, None
    """
    self.callerLength  = initDict.get('callerLength',40)
    self.tagLength     = initDict.get('tagLength',30)

  def printWarnings(self):
    """
      Prints a summary of warnings collected during the run.
      @ In, None
      @ Out, None
    """
    if len(self.warnings)>0:
      if self.verbCode[self.verbosity]>0:
        print('-'*50)
        print('There were %i warnings during the simulation run:' %sum(self.warningCount))
        for w,warning in enumerate(self.warnings):
          count = self.warningCount[w]
          time = 'time'
          if count > 1:
            time += 's'
          print('(%i %s) %s' %(self.warningCount[w],time,warning))
        print('-'*50)
      else:
        print('There were %i warnings during the simulation run.' %sum(self.warningCount))

  def paint(self,str,color):
    """
      Formats string with color
      @ In, str, string, string
      @ In, color, string, color name
      @ Out, paint, string, formatted string
    """
    if color.lower() not in self.colors.keys():
      self.messaage(self,'Requested color %s not recognized!  Skipping...' %color,'Warning','quiet')
      return str
    return self.colors[color.lower()]+str+self.colors['neutral']

  def setTimePrint(self,msg):
    """
      Allows the code to toggle timestamp printing.
      @ In, msg, string, the string that means true or false
      @ Out, None
    """
    if msg.lower() in utils.stringsThatMeanTrue():
      self.callerLength = 40
      self.tagLength = 30
      self.printTime = True
    elif msg.lower() in utils.stringsThatMeanFalse():
      self.callerLength = 25
      self.tagLength = 15
      self.printTime = False

  def setColor(self,inColor):
    """
      Allows output to screen to be colorized.
      @ In, inColor, string, boolean value
      @ Out, None
    """
    if inColor.lower() in utils.stringsThatMeanTrue():
      self.inColor = True

  def getStringFromCaller(self,obj):
    """
      Determines the appropriate print string from an object
      @ In, obj, instance, preferably an object with a printTag method; otherwise, a string or an object
      @ Out, tag, string, string to print
    """
    if type(obj).__name__ in ['str','unicode']:
      return obj
    if hasattr(obj,'printTag'):
      tag = str(obj.printTag)
    else:
      tag = str(obj)
    return tag

  def getVerbosityCode(self,verb):
    """
      Converts English-readable verbosity to computer-legible integer
      @ In, verb, string, the string verbosity equivalent
      @ Out, currentVerb, int, integer equivalent to verbosity level
    """
    verb = str(verb).strip().lower()
    if verb not in self.verbCode.keys():
      raise IOError('Verbosity key '+str(verb)+' not recognized!  Options are '+str(self.verbCode.keys()+[None]),'ERROR','silent')
    currentVerb = self.verbCode[verb]
    return currentVerb

  def error(self,caller,etype,message,tag='ERROR',color=None):
    """
      Raise an error message, unless errors are suppressed.
      @ In, caller, object, the entity desiring to print a message
      @ In, etype, Error, the type of error to throw
      @ In, message, string, the message to print
      @ In, tag, string, optional, the printed message type (usually Message, Debug, or Warning, and sometimes FIXME)
      @ In, color, string, optional, color to apply to message
      @ Out, None
    """
    self.message(caller,message,tag,color=color)
    self.printWarnings()
    raise etype(message)

  def message(self,caller,message,tag,color=None,writeTo=sys.stdout,forcePrint=False):
    """
      Print a message
      @ In, caller, object, the entity desiring to print a message
      @ In, message, string, the message to print
      @ In, tag, string, the printed message type (usually Message, Debug, or Warning, and sometimes FIXME)
      @ In, color, string, optional, color to apply to message
      @ In, forcePrint, bool, optional, force the print independent of the verbosity level. Default False
      @ Out, None
    """
    okay,msg = self._formatMessage(caller,message,tag,color,forcePrint)
    if tag.lower().strip() == 'warning':
      self.addWarning(message)
    if okay:
      print(msg,file=writeTo)
    sys.stdout.flush() # TODO what if not writing to stdout?

  def addWarning(self,msg):
    """
      Stores warnings so that they can be reported in summary later.
      @ In, msg, string, only the main part of the message, used to determine uniqueness
      @ Out, None
    """
    index = bisect.bisect_left(self.warnings,msg)
    if len(self.warnings) == 0 or index == len(self.warnings) or self.warnings[index] != msg:
      self.warnings.insert(index,msg)
      self.warningCount.insert(index,1)
    else:
      self.warningCount[index] += 1

  def _formatMessage(self,caller,message,tag,color=None,forcePrint=False):
    """
      formats message prior to printing
      @ In, caller, object, the entity desiring to print a message
      @ In, message, string, the message to print
      @ In, tag, string, the printed message type (usually Message, Debug, or Warning, and sometimes FIXME)
      @ In, color, string, optional, color to apply to message
      @ In, forcePrint, bool, optional, force the print independetly on the verbosity level? Defaul False
      @ Out, (shouldIPrint,msg), tuple, shouldIPrint -> bool, indication if the print should be allowed
                                        msg          -> string, the formatted message
    """
    # get string representation of calling entity
    ctag = self.getStringFromCaller(caller)
    # format the message for consistency
    msg=self.stdMessage(ctag,tag,message,color)
    return msg

  def stdMessage(self,pre,tag,post,color=None):
    """
      Formats string for pretty printing
      @ In, pre, string, who is printing the message
      @ In, tag, string, the type of message being printed (Error, Warning, Message, Debug, FIXME, etc)
      @ In, post, string, the actual message body
      @ In, color, string, optional, color to apply to message
      @ Out, msg, string, formatted message
    """
    msg = ''
    if self.printTime:
      curtime = time.time()-self.starttime
      msg+='('+'{:8.2f}'.format(curtime)+' sec) '
      if self.inColor:
        msg = self.paint(msg,'cyan')
    msgend = pre.ljust(self.callerLength)[0:self.callerLength] + ': '+tag.ljust(self.tagLength)[0:self.tagLength]+' -> ' + post
    if self.inColor:
      if color is not None:
        #overrides other options
        msgend = self.paint(msgend,color)
      elif tag.lower() in self.colorDict.keys():
        msgend = self.paint(msgend,self.colorDict[tag.lower()])
    msg+=msgend
    return msg
