﻿"""# Access8Math: Allows access math content written by MathML in NVDA
# Copyright (C) 2017-2021 Tseng Woody <tsengwoody.tw@gmail.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details."""
# coding: utf-8

from collections import Iterable
import os
import re
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)
PATH = os.path.dirname(__file__)
PYTHON_PATH = os.path.join(PATH, 'python')
sys.path.insert(0, PYTHON_PATH)
PACKAGE_PATH = os.path.join(PATH, 'package')
sys.path.insert(0, PACKAGE_PATH)
sys.path.insert(0, PATH)

# python xml import
import globalPlugins.Access8Math.python.xml as xml
xml_NVDA = sys.modules['xml']
sys.modules['xml'] = xml

import addonHandler
import api
import controlTypes
import eventHandler
import globalPlugins
import globalPluginHandler
import globalVars
import gui
from keyboardHandler import KeyboardInputGesture
from logHandler import log
import mathPres
from mathPres.mathPlayer import MathPlayer
from NVDAObjects.IAccessible import Button, IAccessible, WindowRoot
from NVDAObjects.window import Window
from scriptHandler import script
import speech
import textInfos
import textInfos.offsets
import tones
import ui
import virtualBuffers
import wx

import A8M_PM
from A8M_PM import MathContent
import _config

addonHandler.initTranslation()

try:
	ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
	ADDON_PANEL_TITLE = str(ADDON_SUMMARY)
except:
	ADDON_PANEL_TITLE = ADDON_SUMMARY = 'Access8Math'
try:
	from speech import BreakCommand
except:
	from speech.commands import BreakCommand

from jinja2 import Environment, FileSystemLoader, select_autoescape
TEMPLATES_PATH = os.path.join(PATH, 'templates')
env = Environment(loader=FileSystemLoader(TEMPLATES_PATH), variable_start_string='{|{', variable_end_string='}|}')
#, autoescape=select_autoescape(['html', 'xml']))

def flatten(lines):
	"""
	convert tree to linear using generator
	@param lines:
	@type list
	@rtype
	"""
	for line in lines:
		if isinstance(line, Iterable) and not isinstance(line, str):
			for sub in flatten(line):
				yield sub
		else:
			yield line

def translate_SpeechCommand(serializes):
	"""
	convert Access8Math serialize object to SpeechCommand
	@param lines: source serializes
	@type list
	@rtype SpeechCommand
	"""
	pattern = re.compile(r'[@](?P<time>[\d]*)[@]')
	speechSequence = []
	for r in flatten(serializes):
		time_search = pattern.search(r)
		try:
			time = time_search.group('time')
			command = BreakCommand(time=int(time) +int(_config.Access8MathConfig["settings"]["item_interval_time"]))
			speechSequence.append(command)
		except:
			speechSequence.append(r)

	return speechSequence

def translate_Unicode(serializes):
	"""
	convert Access8Math serialize object to unicode
	@param lines: source serializes
	@type list
	@rtype unicode
	"""
	pattern = re.compile(r'[@](?P<time>[\d]*)[@]')
	sequence = ''

	for c in serializes:
		sequence = sequence +u'\n'
		for r in flatten(c):
			time_search = pattern.search(r)
			try:
				time = time_search.group('time')
			except:
				sequence = sequence +str(r)
			sequence = sequence +' '

	# replace mutiple blank to single blank
	pattern = re.compile(r'[ ]+')
	sequence = pattern.sub(lambda m: u' ', sequence)

	# replace blank line to none
	pattern = re.compile(r'\n\s*\n')
	sequence = pattern.sub(lambda m: u'\n', sequence)

	# strip blank at start and end line
	temp = ''
	for i in sequence.split('\n'):
		temp = temp +i.strip() +'\n'
	sequence = temp

	return sequence.strip()

def text2template(value, output):
	from mathProcess import textmath2laObj, laObj2mathObj, obj2html
	raw = []
	for line in value.split('\n'):
		line = line.replace('\r', '')
		if line != '':
			raw.extend(textmath2laObj(line))
		raw.append({'type': 'text-content', 'data': ''})

	data = raw
	template = env.get_template("index.template")
	content = template.render({'title': 'Access8Math', 'data': data, 'raw': raw})
	with open(output, 'w', encoding='utf8') as f:
		f.write(content)
	return output

class GenericFrame(wx.Frame):
	def __init__(self, *args, **kwargs):
		super(GenericFrame, self).__init__(*args, **kwargs)
		self.buttons = []

		self.CreateStatusBar() # A StatusBar in the bottom of the window
		self.createMenuBar()

		self.panel = wx.Panel(self, -1)
		self.createButtonBar(self.panel)

		mainSizer=wx.BoxSizer(wx.HORIZONTAL)
		for button in self.buttons:
			mainSizer.Add(button)

		self.panel.SetSizer(mainSizer)
		mainSizer.Fit(self)

	def menuData(self):
		return [
		]

	def createMenuBar(self):
		self.menuBar = wx.MenuBar()
		for eachMenuData in self.menuData():
			menuLabel = eachMenuData[0]
			menuItems = eachMenuData[1]
			self.menuBar.Append(self.createMenu(menuItems), menuLabel)

		self.SetMenuBar(self.menuBar)

	def createMenu(self, menuData):
		menu = wx.Menu()
		for eachItem in menuData:
			if len(eachItem) == 2:
				label = eachItem[0]
				subMenu = self.createMenu(eachItem[1])
				menu.AppendMenu(wx.NewId(), label, subMenu)

			else:
				self.createMenuItem(menu, *eachItem)
		return menu

	def createMenuItem(self, menu, label, status, handler, kind=wx.ITEM_NORMAL):
		if not label:
			menu.AppendSeparator()
			return
		menuItem = menu.Append(-1, label, status, kind)
		self.Bind(wx.EVT_MENU, handler, menuItem)

	def buttonData(self):
		return [
		]

	def createButtonBar(self, panel, yPos = 0):
		xPos = 0
		for eachLabel, eachHandler in self.buttonData():
			pos = (xPos, yPos)
			button = self.buildOneButton(panel, eachLabel,eachHandler, pos)
			self.buttons.append(button)
			xPos += button.GetSize().width

	def buildOneButton(self, parent, label, handler, pos=(0,0)):
		button = wx.Button(parent, -1, label, pos)
		self.Bind(wx.EVT_BUTTON, handler, button)
		return button

class TemplateFrame(GenericFrame):
	def __init__(self):
		title = _("Access8Math HTML window")
		self.file = None
		super().__init__(wx.GetApp().TopWindow, title=title)
		self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)

	def set_file(self, file):
		self.file = file

	def menuData(self):
		return [
			(_("&Menu"), (
				(_("&Exit"),_("Terminate the program"), self.OnExit),
			))
		]

	def buttonData(self):
		return (
			(_("review"), self.OnReview),
			(_("export"), self.OnExport),
		)

	def OnExit(self, event):
		self.Destroy()
		global main_frame
		main_frame = None

	def OnChar(self, event):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_ESCAPE:
			self.Destroy()
			global main_frame
			main_frame = None
			# self.Close()
		event.Skip() 

	def OnReview(self, event):
		def openfile():
			os.startfile(self.file)
		wx.CallAfter(openfile)

	def OnExport(self, event):
		def show():
			with wx.FileDialog(self, message=_("Open file..."), wildcard="zip files (*.zip)|*.zip", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
				if dialog.ShowModal() != wx.ID_OK:
					return
				src = os.path.join(PATH, 'output')
				dst = dialog.GetPath()[:-4]
				shutil.make_archive(dst, 'zip', src)
		wx.CallAfter(show)

class A8MInteractionFrame(GenericFrame):
	def __init__(self):
		title = _("Access8Math interaction window")
		super().__init__(wx.GetApp().TopWindow, title=title)
		self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)

	def menuData(self):
		return [
			(_("&Menu"), (
				(_("&Exit"),_("Terminate the program"), self.OnExit),
			))
		]

	def buttonData(self):
		return (
			(_("interaction"), self.OnInteraction),
			(_("copy"), self.OnRawdataToClip),
		)

	def OnExit(self, event):
		self.Destroy()
		global main_frame
		main_frame = None

	def OnChar(self, event):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_ESCAPE:
			self.Destroy()
			global main_frame
			main_frame = None
			# self.Close()
		event.Skip() 

	def set_mathcontent(self, mathcontent):
		self.mathcontent = mathcontent
		globalVars.mathcontent = mathcontent

	def OnInteraction(self, event):
		parent = api.getFocusObject()
		vw = A8MInteraction(parent=parent)
		vw.set(data=self.mathcontent, name="")
		vw.setFocus()

	def OnRawdataToClip(self, event):
		#api.copyToClip(self.obj.raw_data)
		api.copyToClip(self.mathcontent.root.get_mathml())
		ui.message(_("copy"))


class A8MProvider(mathPres.MathPresentationProvider):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.mathcontent = None

	def getSpeechForMathMl(self, mathMl):
		self.mathcontent = MathContent(A8M_PM.mathrule, mathMl)
		return translate_SpeechCommand(self.mathcontent.pointer.serialized())

	def interactWithMathMl(self, mathMl):
		mathcontent = MathContent(A8M_PM.mathrule, mathMl)
		if _config.Access8MathConfig["settings"]["interaction_frame_show"]:
			show_main_frame(mathcontent)
		else:
			parent = api.getFocusObject()
			vw = A8MInteraction(parent=parent)
			vw.set(data=mathcontent, name="")
			vw.setFocus()


class A8MInteraction(Window):
	def __init__(self, parent, root=None):
		self.parent = parent
		super().__init__(windowHandle=self.parent.windowHandle)

	def set(self, name, data, *args, **kwargs):
		# self.name = name + " - math window"
		self.mathcontent = self.data = data

	def setFocus(self):
		eventHandler.executeEvent("gainFocus", self)

	@script(
		gestures=["kb:escape"]
	)
	def script_escape(self, gesture):
		eventHandler.executeEvent("gainFocus", self.parent)

	def _get_mathMl(self):
		return self.mathcontent.root.get_mathml()
		#return self.raw_data

	def makeTextInfo(self, position=textInfos.POSITION_FIRST):
		return A8MTextInfo(self, position)

	"""def event_gainFocus(self):
		speech.speak([_("enter interaction mode")])
		super().event_gainFocus()
		api.setReviewPosition(self.makeTextInfo(), False)"""

	def reportFocus(self):
		#super().reportFocus()
		speech.speak(translate_SpeechCommand(self.mathcontent.root.serialized()))

	def getScript(self, gesture):
		if isinstance(gesture, KeyboardInputGesture) and "NVDA" not in gesture.modifierNames and (
						gesture.mainKeyName in {
							"leftArrow", "rightArrow", "upArrow", "downArrow",
							"home", "end",
							"space", "backspace", "enter",
						}
						#or len(gesture.mainKeyName)  ==  1
		):
			return self.script_navigate
		return super().getScript(gesture)

	def script_navigate(self, gesture):
		r = False
		if gesture.mainKeyName in ["downArrow", "upArrow", "leftArrow", "rightArrow", "home"]:
			r = self.mathcontent.navigate(gesture.mainKeyName)

		if not r:
			if _config.Access8MathConfig["settings"]["no_move_beep"]:
				tones.beep(100, 100)
			else:
				speech.speak([_("no move")])

		api.setReviewPosition(self.makeTextInfo(), False)
		if self.mathcontent.pointer.parent:
			if _config.Access8MathConfig["settings"]["auto_generate"] and self.mathcontent.pointer.parent.role_level == A8M_PM.AUTO_GENERATE:
				speech.speak([self.mathcontent.pointer.des])
			elif _config.Access8MathConfig["settings"]["dictionary_generate"] and self.mathcontent.pointer.parent.role_level == A8M_PM.DIC_GENERATE:
				speech.speak([self.mathcontent.pointer.des])
		else:
			speech.speak([self.mathcontent.pointer.des])
		speech.speak(translate_SpeechCommand(self.mathcontent.pointer.serialized()))

	@script(
		gesture="kb:control+c",
		description=_("copy mathml"),
		category=ADDON_SUMMARY,
	)
	def script_rawdataToClip(self, gesture):
		#api.copyToClip(self.raw_data)
		api.copyToClip(self.mathcontent.root.get_mathml())
		ui.message(_("copy"))

	@script(
		gesture="kb:control+s",
		description=_("snapshot"),
		category=ADDON_SUMMARY,
	)
	def script_snapshot(self, gesture):
		ui.message(_("snapshot"))

	@script(
		gesture="kb:control+a",
		description=_("Insert math object by asciimath"),
		category=ADDON_SUMMARY,
	)
	def script_asciimath_insert(self, gesture):
		def show(event):
			# asciimath to mathml
			from xml.etree.ElementTree import tostring
			import asciimathml
			global main_frame
			parent = main_frame if main_frame else gui.mainFrame
			with wx.TextEntryDialog(parent=parent, message=_("Write AsciiMath Content")) as dialog:
				if dialog.ShowModal() == wx.ID_OK:
					data = dialog.GetValue()
					data = asciimathml.parse(data)
					mathml = tostring(data)
					mathml = mathml.decode("utf-8")
					mathml = mathml.replace('math>', 'mrow>')
					self.mathcontent.insert(mathml)

		wx.CallAfter(show, None)

	@script(
		gesture="kb:control+l",
		description=_("Insert math object by latex"),
		category=ADDON_SUMMARY,
	)
	def script_latex_insert(self, gesture):
		def show(event):
			# latex to mathml
			from xml.etree.ElementTree import tostring
			import latex2mathml.converter
			global main_frame
			parent = main_frame if main_frame else gui.mainFrame
			with wx.TextEntryDialog(parent=parent, message=_("Write LaTeX Content")) as dialog:
				if dialog.ShowModal() == wx.ID_OK:
					data = dialog.GetValue()
					data = latex2mathml.converter.convert(data)
					mathml = data
					# mathml = mathml.replace('math>', 'mrow>')
					self.mathcontent.insert(mathml)

		wx.CallAfter(show, None)

	@script(
		gesture="kb:control+delete",
		description=_("Delete math object"),
		category=ADDON_SUMMARY,
	)
	def script_delete(self, gesture):
		self.mathcontent.delete()


class A8MTextInfo(textInfos.offsets.OffsetsTextInfo):
	def __init__(self, obj, position):
		super().__init__(obj, position)
		self.obj = obj

	def _getStoryLength(self):
		serializes = self.obj.mathcontent.pointer.serialized()
		return len(translate_Unicode(serializes))

	def _getStoryText(self):
		"""Retrieve the entire text of the object.
		@return: The entire text of the object.
		@rtype: unicode
		"""
		serializes = self.obj.mathcontent.pointer.serialized()
		return translate_Unicode(serializes)

	def _getTextRange(self, start, end):
		"""Retrieve the text in a given offset range.
		@param start: The start offset.
		@type start: int
		@param end: The end offset (exclusive).
		@type end: int
		@return: The text contained in the requested range.
		@rtype: unicode
		"""
		text = self._getStoryText()
		return text[start:end] if text else u""


provider_list = [
	A8MProvider,
]

try:
	reader = MathPlayer()
	provider_list.append(MathPlayer)
	mathPres.registerProvider(reader, speech=True, braille=True, interaction=True)
except:
	log.warning("MathPlayer 4 not available")

_config.load()

try:
	if _config.Access8MathConfig["settings"]["provider"] == "Access8Math":
		provider = A8MProvider
	elif _config.Access8MathConfig["settings"]["provider"] == "MathPlayer":
		provider = MathPlayer
	else:
		_config.Access8MathConfig["settings"]["provider"] = "Access8Math"
		provider = A8MProvider
	reader = provider()
except:
	_config.Access8MathConfig["settings"]["provider"] = "Access8Math"
	provider = A8MProvider
	reader = provider()

mathPres.registerProvider(reader, speech=True, braille=False, interaction=True)


class AppWindowRoot(IAccessible):
	def event_focusEntered(self):
		def run():
			parent = api.getFocusObject()
			vw = A8MInteraction(parent=parent)
			vw.set(data=globalVars.mathcontent, name="")
			try:
				vw.setFocus()
			except:
				tones.beep(100, 100)
		wx.CallLater(100, run)

class TextMathEditField(IAccessible):
	@script(gesture="kb:NVDA+shift+m")
	def script_view_math(self, gesture):
		output_file = text2template(self.value, os.path.join(PATH, 'output', 'index.html'))
		show_template_frame(file=output_file)

		def openfile():
			os.startfile(output_file)
		# wx.CallAfter(openfile)

def show_main_frame(mathcontent):
	global main_frame
	if not main_frame:
		main_frame = A8MInteractionFrame()
	main_frame.set_mathcontent(mathcontent=mathcontent)
	main_frame.Show()
	main_frame.Raise()

def show_template_frame(file):
	global template_frame
	if not template_frame:
		template_frame = TemplateFrame()
	template_frame.set_file(file=file)
	template_frame.Show()
	template_frame.Raise()

main_frame = None
template_frame = None

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		A8M_PM.initialize(_config.Access8MathConfig)

		self.language = _config.Access8MathConfig["settings"]["language"]
		self.create_menu()

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if obj.windowClassName == "wxWindowNR" and obj.role == controlTypes.ROLE_WINDOW and obj.name == _("Access8Math interaction window"):
			clsList.insert(0, AppWindowRoot)
		if obj.windowClassName == "Edit" and obj.role == controlTypes.ROLE_EDITABLETEXT:
			clsList.insert(0, TextMathEditField)

	def create_menu(self):
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.menu = wx.Menu()

		self.generalSettings = self.menu.Append(
			wx.ID_ANY,
			_("&General settings...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onGeneralSettings, self.generalSettings)

		self.ruleSettings = self.menu.Append(
			wx.ID_ANY,
			_("&Rule settings...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onRuleSettings, self.ruleSettings)

		writeMenu = wx.Menu()
		self.asciiMath = writeMenu.Append(
			wx.ID_ANY,
			_("&asciimath...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onAsciiMathAdd, self.asciiMath)

		self.latex = writeMenu.Append(
			wx.ID_ANY,
			_("&latex...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onLatexAdd, self.latex)

		self.textmath = writeMenu.Append(
			wx.ID_ANY,
			_("&text-math...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onTextMathAdd, self.textmath)

		self.menu.AppendMenu(
			wx.ID_ANY,
			_("&Write..."),
			writeMenu
		)

		l10nMenu = wx.Menu()
		self.unicodeDictionary = l10nMenu.Append(
			wx.ID_ANY,
			_("&unicode dictionary...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onUnicodeDictionary, self.unicodeDictionary)

		self.mathRule = l10nMenu.Append(
			wx.ID_ANY,
			_("&math rule...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onMathRule, self.mathRule)

		self.newLanguageAdding = l10nMenu.Append(
			wx.ID_ANY,
			_("&New language adding...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onNewLanguageAdding, self.newLanguageAdding)

		self.menu.AppendMenu(
			wx.ID_ANY,
			_("&Localization..."),
			l10nMenu
		)

		self.about = self.menu.Append(
			wx.ID_ANY,
			_("&About...")
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onAbout, self.about)

		self.Access8Math_item = self.toolsMenu.AppendSubMenu(self.menu, _("Access8Math"), _("Access8Math"))

	def terminate(self):
		_config.save()
		try:
			self.toolsMenu.Remove(self.Access8Math_item)
		except (AttributeError, RuntimeError):
			pass

	@script(
		description=_("Change mathml provider"),
		category=ADDON_SUMMARY,
	)
	def script_change_provider(self, gesture):
		if _config.Access8MathConfig["settings"]["provider"] == "Access8Math":
			_config.Access8MathConfig["settings"]["provider"] = "MathPlayer"
		elif _config.Access8MathConfig["settings"]["provider"] == "MathPlayer":
			_config.Access8MathConfig["settings"]["provider"] = "Access8Math"
		else:
			_config.Access8MathConfig["settings"]["provider"] = "Access8Math"

		try:
			if _config.Access8MathConfig["settings"]["provider"] == "Access8Math":
				provider = A8MProvider
			elif _config.Access8MathConfig["settings"]["provider"] == "MathPlayer":
				provider = MathPlayer
			else:
				_config.Access8MathConfig["settings"]["provider"] = "Access8Math"
				provider = A8MProvider
			reader = provider()
		except:
			_config.Access8MathConfig["settings"]["provider"] = "Access8Math"
			provider = A8MProvider
			reader = provider()

		mathPres.registerProvider(reader, speech=True, braille=False, interaction=True)

		ui.message(_("mathml provider change to %s")%_config.Access8MathConfig["settings"]["provider"])

	@script(
		description=_("Shows the Access8Math settings dialog."),
		category=ADDON_SUMMARY,
	)
	def script_settings(self, gesture):
		wx.CallAfter(self.onGeneralSettings, None)

	def onGeneralSettings(self, evt):
		from dialogs import GeneralSettingsDialog
		gui.mainFrame._popupSettingsDialog(GeneralSettingsDialog, _config.Access8MathConfig)

	def onRuleSettings(self, evt):
		from dialogs import RuleSettingsDialog
		gui.mainFrame._popupSettingsDialog(RuleSettingsDialog, _config.Access8MathConfig)

	def onNewLanguageAdding(self, evt):
		from dialogs import NewLanguageAddingDialog
		NewLanguageAddingDialog(gui.mainFrame).Show()

	def onUnicodeDictionary(self, evt):
		self.language = _config.Access8MathConfig["settings"]["language"]
		from dialogs import UnicodeDicDialog
		gui.mainFrame._popupSettingsDialog(UnicodeDicDialog, _config.Access8MathConfig, self.language)

	def onMathRule(self, evt):
		self.language = _config.Access8MathConfig["settings"]["language"]
		from dialogs import MathRuleDialog
		gui.mainFrame._popupSettingsDialog(MathRuleDialog, _config.Access8MathConfig, self.language)

	def onAsciiMathAdd(self, evt):
		# asciimath to mathml
		from xml.etree.ElementTree import tostring
		import asciimathml
		global main_frame
		parent = main_frame if main_frame else gui.mainFrame
		with wx.TextEntryDialog(parent=parent, message=_("Write AsciiMath Content")) as dialog:
			if dialog.ShowModal() == wx.ID_OK:
				data = dialog.GetValue()
				data = asciimathml.parse(data)
				mathml = tostring(data)
				mathml = mathml.decode("utf-8")
				mathml = mathml.replace('math>', 'mrow>')
				mathcontent = MathContent(A8M_PM.mathrule, mathml)
				show_main_frame(mathcontent)

	def onLatexAdd(self, evt):
		# latex to mathml
		from xml.etree.ElementTree import tostring
		import latex2mathml.converter
		global main_frame
		parent = main_frame if main_frame else gui.mainFrame
		with wx.TextEntryDialog(parent=parent, message=_("Write LaTeX Content")) as dialog:
			if dialog.ShowModal() == wx.ID_OK:
				data = dialog.GetValue()
				data = latex2mathml.converter.convert(data)
				mathml = data
				mathcontent = MathContent(A8M_PM.mathrule, mathml)
				show_main_frame(mathcontent)

	def onTextMathAdd(self, evt):
		global main_frame
		parent = main_frame if main_frame else gui.mainFrame
		with wx.TextEntryDialog(parent=parent, message=_("Write TextMath Content"), style=wx.OK | wx.CANCEL | wx.TE_MULTILINE) as dialog:
			if dialog.ShowModal() == wx.ID_OK:
				value = dialog.GetValue()
				output_file = text2template(value, os.path.join(PATH, 'output', 'index.html'))
				show_template_frame(file=output_file)

	def onAbout(self, evt):
		path = os.path.join(PATH, "locale", self.language, "about.txt")
		with open(path, 'r', encoding='utf8') as f:
			aboutMessage = f.read()
		gui.messageBox(aboutMessage, _("About Access8Math"), wx.OK)
