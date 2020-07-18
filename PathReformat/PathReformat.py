import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import numpy
from slicer.util import VTKObservationMixin

#
# PathReformat
#

class PathReformat(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Path reformat"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["SET (Hobbyist)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
Moves a selected view along a path, and orients the plane at right angle to the path. It is intended to view cross-sections of blood vessels.
See more information in <a href="https://github.com/chir-set/PathReformat">module documentation</a>.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# PathReformatWidget
#

class PathReformatWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/PathReformat.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = PathReformatLogic()

    slicer.modules.reformat.widgetRepresentation().setEditedNode(slicer.util.getNode("vtkMRMLSliceNodeRed"))
    self.resetSliderWidget(self.ui.positionIndexSliderWidget)

    # Connections
    self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.positionIndexSliderWidget.connect("valueChanged(double)", self.logic.process)
    self.ui.redRadioButton.connect("clicked()", self.onRadioRed)
    self.ui.greenRadioButton.connect("clicked()", self.onRadioGreen)
    self.ui.yellowRadioButton.connect("clicked()", self.onRadioYellow)
    self.ui.hideCheckBox.connect("clicked()", self.onHidePath)
    
  def cleanup(self):
    self.logic.removeMarkupObservers()
      
  def onSelectNode(self):
    inputPath = self.ui.inputSelector.currentNode()
    self.logic.selectNode(inputPath)
    self.setSliderWidget()
    if inputPath is not None:
        self.ui.hideCheckBox.setChecked(not inputPath.GetDisplayVisibility())
    # Position slice view at first point
    self.ui.positionIndexSliderWidget.setValue(0)
    self.logic.process(0)
    
  def onRadioRed(self):
    self.logic.selectView("vtkMRMLSliceNodeRed")
    
  def onRadioGreen(self):
    self.logic.selectView("vtkMRMLSliceNodeGreen")
    
  def onRadioYellow(self):
    self.logic.selectView("vtkMRMLSliceNodeYellow")
    
  def onHidePath(self):
    path = self.ui.inputSelector.currentNode()
    if path is None:
        return
    path.SetDisplayVisibility(not self.ui.hideCheckBox.checked)
    
  def resetSliderWidget(self, sliderWidget):
    sliderWidget = self.ui.positionIndexSliderWidget
    sliderWidget.setDisabled(True)
    sliderWidget.minimum = 0
    sliderWidget.maximum = 0
    sliderWidget.setValue(0)
    sliderWidget.singleStep = 1
    sliderWidget.decimals = 0
    
  def setSliderWidget(self):
    inputPath = self.ui.inputSelector.currentNode()
    sliderWidget = self.ui.positionIndexSliderWidget
    if inputPath is None:
        self.resetSliderWidget(sliderWidget)
        return
    sliderWidget.setDisabled(False)
    sliderWidget.minimum = 0
    sliderWidget.maximum = (self.logic.pathArray.size / 3) - 1 - 1
    
#
# PathReformatLogic
#

class PathReformatLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    self.inputPath = None
    self.inputSliceNode = slicer.util.getNode("vtkMRMLSliceNodeRed")
    self.reformatLogic = slicer.modules.reformat.logic()
    self.pathArray = numpy.zeros(0)
    self.markupPointObserver = None
    self.markupPointRemovedObserver = None
    self.markupPointAddedObserver = None
    # on markup change, reprocess last point
    self.lastValue = 0
    # self.backgroundVolumeNode = slicer.app.layoutManager().sliceWidget(self.inputSliceNode.GetName()).sliceLogic().GetBackgroundLayer().GetVolumeNode()
  
  def resetSliceNodeOrientationToDefault(self):
    if self.inputPath is None:
        return
    slicer.app.layoutManager().sliceWidget(self.inputSliceNode.GetName()).mrmlSliceNode().SetOrientationToDefault()
    
  def fillPathArray(self):
    if self.inputPath is None or self.inputSliceNode is None:
        self.pathArray = numpy.zeros(0)
        return
    if self.inputPath.GetClassName() == "vtkMRMLMarkupsCurveNode" or self.inputPath.GetClassName() == "vtkMRMLMarkupsClosedCurveNode":
        self.pathArray = slicer.util.arrayFromMarkupsCurvePoints(self.inputPath)
        
    if self.inputPath.GetClassName() == "vtkMRMLModelNode":
        self.pathArray = slicer.util.arrayFromModelPoints(self.inputPath)

  def process(self, value):
    if self.inputSliceNode is None or self.inputPath is None:
        return
    point = self.pathArray[int(value)]
    direction = self.pathArray[int(value) + 1] - point
    self.reformatLogic.SetSliceOrigin(self.inputSliceNode, point[0], point[1], point[2])
    self.reformatLogic.SetSliceNormal(self.inputSliceNode, direction[0], direction[1], direction[2])
    self.lastValue = value

  def selectNode(self, inputPath):
    # Observe the selected markup path only. Remove from previous.
    self.removeMarkupObservers()
    self.inputPath = inputPath
    self.resetSliceNodeOrientationToDefault()
    self.fillPathArray()
    # Observe path
    if inputPath is not None and inputPath.GetClassName() == "vtkMRMLMarkupsCurveNode":
        self.markupPointObserver = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onMarkupPointEndInteraction)
        self.markupPointRemovedObserver = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onMarkupPointRemoved)
        self.markupPointAddedObserver = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent, self.onMarkupPointAdded)
    
  def selectView(self, sliceMRMLNodeName):
    self.inputSliceNode = slicer.util.getNode(sliceMRMLNodeName)
    slicer.modules.reformat.widgetRepresentation().setEditedNode(slicer.util.getNode(sliceMRMLNodeName))
    
  def removeMarkupObservers(self):
    if self.inputPath is not None:
        self.inputPath.RemoveObserver(self.markupPointObserver)
        self.inputPath.RemoveObserver(self.markupPointRemovedObserver)
        self.inputPath.RemoveObserver(self.markupPointAddedObserver)
        
  # Reposition slice if adjacent markup control point is moved
  def onMarkupPointEndInteraction(self, caller, event):
    self.fillPathArray()
    self.process(self.lastValue)
    
  # Reposition slice to start if a markup control point is removed
  def onMarkupPointRemoved(self, caller, event):
    self.fillPathArray()
    self.process(0)

  # Reposition slice to start if a markup control point is added
  def onMarkupPointAdded(self, caller, event):
    self.fillPathArray()
    self.process(0)
  
#
# PathReformatTest
#

class PathReformatTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()
