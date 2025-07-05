#!/usr/bin/env python3

import ast
import configparser
import hashlib
import json
import os
import re
import string
import subprocess
from subprocess import PIPE
import sys

from includetree import includeTree
from helper import loadConfig, annotateDTS, ConfigHelper
from merge import mergeDts

from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6 import QtCore, QtGui, QtWidgets, uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QDialog, QHeaderView, QMessageBox, QTreeWidgetItem, \
    QWidget
from PyQt6.uic import loadUi

import qdarktheme

from queue import Queue

DELETED_TAG = "__[|>*DELETED*<|]__"

def getTopLevelItem(trwDT):
    return trwDT.topLevelItem(trwDT.topLevelItemCount()-1)

def populateDTS(trwDT, trwIncludedFiles, filename):
    left_bracket_count = 0
    right_bracket_count = 0
    # 宣告一個存放line的list
    #line_temp = []
    lines_dict = {}

    # Clear remnants from previously opened file
    trwDT.clear()
    trwIncludedFiles.expandAll()

    with open (filename) as f:

        # Read each line in the DTS file
        lineNum = 1
        for line in f:

            # Look for the code (part before the "/*" comment)
            idx = line.rfind("/*")

            if idx < 0:
                lineContents = line.strip()
            else:
                lineContents = line[:idx].rstrip()

            if idx > 0:
                # Now pick the comment part of the line
                commentFileList = line[idx+2:].strip()[:-2]
                # Remove false positive
                if "<no-file>:<no-line>" in commentFileList:
                    commentFileList = None
            else:
                commentFileList = None

            # If found, then clean-up
            if commentFileList:
                # The last (rightmost) file in the comma-separted list of filename:lineno
                # Line numbers are made-up of integers after a ":" colon.
                listOfSourcefiles = list(map(lambda f: os.path.realpath(f.strip()), commentFileList.split(',')))
                fileWithLineNums = listOfSourcefiles[-1]

                if fileWithLineNums:
                    # Filename is the last (rightmost) word in a forward-slash-separetd path string
                    includedFilename = fileWithLineNums.split(':', 1)[0].split('/')[-1]
            else:
                fileWithLineNums = ''

            if not fileWithLineNums:
                includedFilename = ''

                # skip empty line
                if not (lineContents.lstrip()):
                    lineNum += 1
                    continue

            # find deleted tag
            isDeleted = DELETED_TAG in lineContents
            if isDeleted:
                # remove deleted tag and uncomment content
                lineContents = lineContents.replace('/* ' + DELETED_TAG + ' */ ', '')
                lineContents = re.sub(r'/\*(.*)?\*/\s*', r'\g<1>', lineContents, flags=re.S)

            # Add line to the list
            rowItem = QtWidgets.QTreeWidgetItem([str(lineNum), lineContents, includedFilename, fileWithLineNums])
            trwDT.addTopLevelItem(rowItem)
            #line_temp.append(lineContents)
            lines_dict[lineNum] = lineContents

            if "{" in lineContents:
                left_bracket_count += 1
            if "}" in lineContents:
                right_bracket_count += 1

            # Pick a different background color for each filename
            if includedFilename:
                colorHash = (int(hashlib.sha1(includedFilename.encode('utf-8')).hexdigest(), 16) % 16) * 4
                prevColorHash = colorHash
                bgColor = QColor(255-colorHash*2, 240, 192+colorHash)
            else:
                bgColor = QColor(255, 255, 255)

            rowItem.setBackground(1, bgColor)

            if isDeleted:
                rowItem.setForeground(1, QColor(255, 0, 0))
                f = rowItem.font(0)
                f.setStrikeOut(True)
                f.setBold(True)
                rowItem.setFont(1, f)

            # Include parents
            if commentFileList:
                # Skip add parents for close bracket of node
                if not (isDeleted and "};" in lineContents.strip()):
                    for fileWithLineNums in listOfSourcefiles[-2::-1]:
                        strippedLineNums = fileWithLineNums.split(':', 1)[0]
                        includedFilename = strippedLineNums.split('/')[-1]
                        rowItem = QtWidgets.QTreeWidgetItem([str(lineNum), "", includedFilename, fileWithLineNums])
                        trwDT.addTopLevelItem(rowItem)
                        item = getTopLevelItem(trwDT)
                        item.setForeground(0, QColor(255, 255, 255));
            elif not isDeleted:
                item = getTopLevelItem(trwDT)
                item.setForeground(1, QColor(175, 175, 175))
                f = item.font(0)
                item.setFont(1, f)

            lineNum += 1

        print("count of left brackets = {}, count of right brackets = {}".format(left_bracket_count, right_bracket_count))

        left_Bracket_index = None
        right_Bracket_index = None

        in_the_end = False

        while not in_the_end:
            # 產生一個暫存的list，將lines_dict的value轉換成list（不建議用 index 取 key）
            keys_sorted = sorted(lines_dict.keys())
            line_temp = [lines_dict[k] for k in keys_sorted]

            right_Bracket_index = None
            for key in keys_sorted:
                if "}" in lines_dict[key]:
                    right_Bracket_index = key
                    break
                if key == keys_sorted[-1]:
                    in_the_end = True
                    right_Bracket_index = None
                    break

            if right_Bracket_index is not None:
                # 從右括號開始往前找左括號
                left_Bracket_index = None
                for k in reversed(keys_sorted):
                    if k > right_Bracket_index:
                        continue
                    if "{" in lines_dict[k]:
                        left_Bracket_index = k
                        break

                if left_Bracket_index is not None:
                    tree_title = lines_dict[left_Bracket_index].replace("{", "").strip()


                    print(f"Tree Title: {tree_title}, Lines starting from {left_Bracket_index} to {right_Bracket_index}")

                    # 清除已處理的行
                    keys_to_delete = [k for k in keys_sorted if left_Bracket_index <= k <= right_Bracket_index]
                    for k in keys_to_delete:
                        if k in lines_dict:
                            del lines_dict[k]

                    left_Bracket_index = None
                    right_Bracket_index = None





def populateIncludedFiles(trwIncludedFiles, dtsFile, inputIncludeDirs):

    trwIncludedFiles.clear()
    dtsIncludeTree = includeTree(dtsFile, inputIncludeDirs)
    dummyItem = QtWidgets.QTreeWidgetItem()
    dtsIncludeTree.populateChildrenFileNames(dummyItem)
    trwIncludedFiles.addTopLevelItem(dummyItem.child(0).clone())

def highlightFileInTree(trwIncludedFiles, fileWithLineNums):
    filePath = fileWithLineNums.split(':', 1)[0]
    fileName = filePath.split('/')[-1]
    items = trwIncludedFiles.findItems(fileName, QtCore.Qt.MatchFlag.MatchRecursive)
    currItem = next(item for item in items if item.toolTip(0) == filePath)

    # highlight/select current item
    trwIncludedFiles.setCurrentItem(currItem)

    # highlight/select all its parent items
    while (currItem.parent()):
        currItem = currItem.parent()
        currItem.setSelected(True)

def getLines(fileName, startLineNum, endLineNum):

    lines = ''

    with open(fileName) as f:
        fileLines = f.readlines()

        if (startLineNum == endLineNum):
            lines = fileLines[startLineNum-1]
        else:
            for line in range(startLineNum-1, endLineNum):
                lines += fileLines[line]

    return lines

def showOriginalLineinLabel(lblDT, lineNum, fileWithLineNums):

    filePath = fileWithLineNums.split(':', 1)[0]

    # extract line numbers in source-file
    # TODO: Special Handling for opening and closing braces in DTS
    #       (no need to show ENTIRE node, right?)
    startLineNum = int(re.split('[[:-]', fileWithLineNums)[-4].strip())
    endLineNum = int(re.split('[[:-]', fileWithLineNums)[-2].strip())
    #print('Line='+str(lineNum), 'Source='+filePath, startLineNum, 'to', endLineNum)
    lblDT.setText(getLines(filePath, startLineNum, endLineNum))

def center(window):

    # Determine the center of mainwindow
    centerPoint = QtCore.QPoint()
    centerPoint.setX(main.x() + (main.width()/2))
    centerPoint.setY(main.y() + (main.height()/2))

    # Calculate the current window's top-left such that
    # its center co-incides with the mainwindow's center
    frameGm = window.frameGeometry()
    frameGm.moveCenter(centerPoint)

    # Align current window as per above calculations
    window.move(frameGm.topLeft())


class MyDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = loadUi("settings.ui", self)
        self.ui.setWindowTitle("DTV Settings")


        self.config = ConfigHelper()

        # 將includeDirStubs轉換為字串用;隔開
        include_dir_strs = '; '.join(self.config.get_include_dirs())
        editor = self.config.get_editor()
        # 去除空格
        include_dir_strs = include_dir_strs.replace(' ', '')
        self.ui.lineEdit.setText(include_dir_strs)
        self.ui.lineEdit_2.setText(editor)


        reset_button = self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Reset)
        if reset_button: # Check if the button exists
            reset_button.clicked.connect(self.reset_defaults)

        # Save button
        accept_button = self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Save)
        if accept_button: # Check if the button exists
            accept_button.clicked.connect(self.ok)

    def reset_defaults(self):
        print("reset_defaults")

        self.config.load_default_config()
        self.ui.lineEdit.setText('; '.join(self.config.get_include_dirs()))
        self.ui.lineEdit_2.setText(self.config.get_editor())




    def ok(self):

        print("ok")

        # 將dirs回存到dtv.conf
        # 將lineEdit的內容轉換為list
        dir_str = self.ui.lineEdit.text()
        dirs = dir_str.split(';')
        editor = self.ui.lineEdit_2.text()

        self.config.set_include_dirs(dirs)
        self.config.set_editor(editor)
        self.config.save_config()

        self.close()



class main(QMainWindow):


    def __init__(self):
        super().__init__()
        self.ui = None
        self.load_ui()
        self.load_signals()
        self.findStr = None
        self.foundList = []
        self.foundIndex = 0

        argc = len(sys.argv)

        try:

            if argc > 1:
                dts_file = sys.argv[1]
                if argc == 2:
                    self.openDTSFile(dts_file)
                else:
                    self.openDTSFile(mergeDts(sys.argv[1:]), dts_file)
        except Exception as e:
            print(e)

    def openDTSFileUI(self):

        fileName, _ = QFileDialog.getOpenFileName(self,
                                                  "Select a DTS file to visualise...",
                                                  "", "All DTS Files (*.dts *.dtsi)",
                                                  )
        try:
            self.openDTSFile(fileName)
        except Exception as e:
            print(e)

    def openDTSFile(self, fileName, baseDtsFileName = None):

        # If user selected a file then process it...
        if fileName:
            # Don't resolve symlinks in path
            fileName = os.path.abspath(fileName)

            self.ui.setWindowTitle("DTV - " + fileName)

            self.findStr = None
            self.foundList = []
            self.foundIndex = 0

            annotatedTmpDTSFileName = None
            try:
                if baseDtsFileName:
                    incIncludes = loadConfig(baseDtsFileName)
                else:
                    incIncludes = loadConfig(fileName)

                # Resolve symlinks in path
                fileName = os.path.realpath(fileName)
                annotatedTmpDTSFileName = annotateDTS(fileName, incIncludes)
                populateIncludedFiles(self.ui.trwIncludedFiles, fileName, incIncludes)
                populateDTS(self.ui.trwDT, self.ui.trwIncludedFiles, annotatedTmpDTSFileName)
            except Exception as e:
                print('EXCEPTION!', e)
                #exit(1)
            finally:
                # Delete temporary file if created
                if annotatedTmpDTSFileName:
                    try:
                        os.remove(annotatedTmpDTSFileName)
                    except OSError:
                        pass

            self.trwDT.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.trwDT.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.trwDT.header().setSectionHidden(3, True)
            self.trwDT.header().resizeSection(1, 500)

    def highlightSourceFile(self):

        # Skip if no "current" row
        if self.ui.trwDT.currentItem() is None:
            return

        # Skip if current row is "whitespace"
        if self.ui.trwDT.currentItem().text(2) == '':
            self.ui.lblDT.setText('')
            return

        # Else identify and highlight the source file of the current row
        if self.ui.trwDT.currentItem():
            highlightFileInTree(self.ui.trwIncludedFiles, self.ui.trwDT.currentItem().text(3))
            showOriginalLineinLabel(self.ui.lblDT, int(self.ui.trwDT.currentItem().text(0)), self.ui.trwDT.currentItem().text(3))

    def launchEditor(self, srcFileName, srcLineNum):

        # Load configuration for the conf file
        config = configparser.ConfigParser()
        config.read('dtv.conf')

        # Launch user-specified editor
        editorCommand = ast.literal_eval(config.get('dtv', 'editor_cmd'))
        editorCommandEvaluated = string.Template(editorCommand).substitute(locals())

        try:
            launchEditor = subprocess.Popen(editorCommandEvaluated.split(),
                                        stdin=None, stdout=None, stderr=None,
                                        close_fds=True)
        except FileNotFoundError:
            QMessageBox.warning(self,
                            'DTV',
                            'Failed to launch editor!\n\n' +
                            editorCommandEvaluated +
                            '\n\nPlease modify "dtv.conf" using any text editor.',
                            QMessageBox.StandardButton.Ok)

    def editSourceFile(self):

        # TODO: Refactor. Same logic used by showOriginalLineinLabel() too
        lineNum = int(self.ui.trwDT.currentItem().text(0))
        fileWithLineNums = self.ui.trwDT.currentItem().text(3)
        dtsiFileName = fileWithLineNums.split(':')[0].strip()
        if dtsiFileName == '':
            QMessageBox.information(self,
                                    'DTV',
                                    'No file for the curent line',
                                    QMessageBox.StandardButton.Ok)
            return

        dtsiLineNum = int(re.split('[[:-]', fileWithLineNums)[-4].strip())
        self.launchEditor(dtsiFileName, dtsiLineNum)

    def editIncludedFile(self):
        includedFileName = self.ui.trwIncludedFiles.currentItem().toolTip(0)
        self.launchEditor(includedFileName, '0')

    def findTextinDTS(self):

        findStr = self.txtFindText.text()

        # Very common for use to click Find on empty string
        if findStr == "":
            return


        # New search string ?
        if findStr != self.findStr:
            self.findStr = findStr
            self.foundList = self.trwDT.findItems(self.findStr, QtCore.Qt.MatchFlag.MatchContains | QtCore.Qt.MatchFlag.MatchRecursive, column=1)
            self.foundIndex = 0
            numFound = len(self.foundList)
        else:
            numFound = len(self.foundList)
            if numFound:
                if ('Prev' in self.sender().objectName()):
                    # handles btnFindPrev
                    self.foundIndex = (self.foundIndex - 1) % numFound
                else:
                    # handles btnFindNext and <Enter> on txtFindText
                    self.foundIndex = (self.foundIndex + 1) % numFound

        if numFound:
            self.trwDT.setCurrentItem(self.foundList[self.foundIndex])
            self.trwDT.scrollToItem(self.foundList[self.foundIndex], QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    def showSettings(self):
        #QMessageBox.information(self,
        #                    'DTV',
        #                    'Settings GUI NOT supported yet.\n'
        #                    'Please modify "dtv.conf" using any text editor.',
        #                    QMessageBox.StandardButton.Ok)

        #self.settings_ui = loadUi('settings.ui', self)

        dialog = MyDialog()
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            print("Dialog accepted")
        else:
            print("Dialog rejected")


        return

    def center(self):
        frameGm = self.frameGeometry()
        centerPoint = self.screen().availableGeometry().center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())

    def load_ui(self):
        self.ui = loadUi('dtv.ui', self)
        self.ui.openDTS.triggered.connect(self.openDTSFileUI)
        self.ui.exitApp.triggered.connect(self.close)
        self.ui.optionsSettings.triggered.connect(self.showSettings)
        self.ui.trwDT.currentItemChanged.connect(self.highlightSourceFile)
        self.ui.trwDT.itemDoubleClicked.connect(self.editSourceFile)
        self.ui.trwIncludedFiles.itemDoubleClicked.connect(self.editIncludedFile)
        self.ui.btnFindPrev.clicked.connect(self.findTextinDTS)
        self.ui.btnFindNext.clicked.connect(self.findTextinDTS)
        self.ui.txtFindText.returnPressed.connect(self.findTextinDTS)

        #data = {"Project A": ["file_a.py", "file_a.txt", "something.xls"],
        #        "Project B": ["file_b.csv", "photo.jpg"],
        #        "Project C": []}
#
        #self.ui.testTree.setColumnCount(2)
        #self.ui.testTree.setHeaderLabels(["Name", "Type"])
#
        #items = []
        #for key, values in data.items():
        #    item = QTreeWidgetItem([key])
        #    for value in values:
        #        ext = value.split(".")[-1].upper()
        #        child = QTreeWidgetItem([value, ext])
        #        item.addChild(child)
        #    items.append(item)
#
        #self.ui.testTree.insertTopLevelItems(0, items)



        self.trwDT.setHeaderLabels(['Line No.', 'DTS content ....', 'Source File', 'Full path'])

        self.center()
        self.show()

    def load_signals(self):
        pass

try:
    subprocess.run('which cpp dtc', stdout=PIPE, stderr=PIPE, shell=True, check=True)
except subprocess.CalledProcessError as e:
    print('EXCEPTION!', e)
    print('stdout: {}'.format(e.output.decode(sys.getfilesystemencoding())))
    print('stderr: {}'.format(e.stderr.decode(sys.getfilesystemencoding())))
    exit(e.returncode)

try:
    subprocess.run('dtc --annotate -h', stdout=PIPE, stderr=PIPE, shell=True, check=True)
except subprocess.CalledProcessError as e:
    print('EXCEPTION!', e)
    print('EXCEPTION!', 'dtc version it too old and it doesn\'t support "annotate" option')
    exit(e.returncode)

app = QApplication(sys.argv)
qdarktheme.setup_theme("light")

main = main()

# Blocks till Qt app is running, returns err code if any
qtReturnVal = app.exec()

sys.exit(qtReturnVal)

