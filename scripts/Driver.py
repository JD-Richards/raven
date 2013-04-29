'''
Created on Feb 20, 2013

@author: crisr
'''
import xml.etree.ElementTree as ET
import os
from Simulation import Simulation
import sys

debug = True

if __name__ == '__main__':
  #open the XML
  try:
    if len(sys.argv) == 1:
      inputFile = 'test.xml' 
    else:
      inputFile = sys.argv[1]
  except:
    raise IOError ('input file not provided')
  workingDir = os.getcwd()
  if not os.path.isabs(inputFile):
    inputFile = os.path.join(workingDir,inputFile)
  if not os.path.exists(inputFile):
    print('file not found '+inputFile)
  try:
    tree = ET.parse(inputFile)
    if debug: print('opened file '+inputFile)
  except:
    tree = ET.parse(inputFile)
    raise IOError ('not able to parse ' + inputFile)
  root = tree.getroot()
  #generate all the components of the simulation
  simulation = Simulation(inputFile)
  simulation.XMLread(root)
  simulation.run()

