import ast
import configparser
import json
import os
import re
import subprocess
from subprocess import PIPE
import sys
import tempfile

def getFileName(filename: str):
    return os.path.splitext(os.path.basename(filename))[0]

def loadConfig(baseDtsFile):
    baseAbsPath = os.path.abspath(baseDtsFile)
    baseRealPath = os.path.realpath(baseDtsFile)

    baseDirPaths = set()
    result_abspath = re.search('^.*(?=arch\/)', baseAbsPath)
    result_realpath = re.search('^.*(?=arch\/)', baseRealPath)

    if result_abspath:
        baseDirPaths.add(result_abspath.group(0))
    if result_realpath:
        baseDirPaths.add(result_realpath.group(0))

    if(result_abspath == None):
        result_abspath = re.search('^.*(?=src\/)', baseAbsPath)
        if result_abspath:
            baseDirPaths.add(result_abspath.group(0))

    if(result_realpath == None):
        result_realpath = re.search('^.*(?=src\/)', baseAbsPath)
        if result_realpath:
            baseDirPaths.add(result_realpath.group(0))

    # Load configuration for the conf file
    config = ConfigHelper().load_config()

    # Add or remove projects from this list
    # Only the gerrit-events of changes to projects in this list will be processed.
    includeDirStubs =  ast.literal_eval(config.get('dtv', 'include_dir_stubs'))

    incIncludes = list()

    for includeDirStub in includeDirStubs:
        for baseDirPath in baseDirPaths:
            if os.path.exists(baseDirPath + includeDirStub):
                incIncludes.append(baseDirPath + includeDirStub)

    return incIncludes

def annotateDTS(dtsFile, incIncludes, out_dir = None, level = 2):

    if out_dir:
        if not os.path.exists(out_dir):
            print("Path '{}' not found!".format(out_dir))
            exit(1)
    else:
        out_dir = os.path.dirname(os.path.realpath(__file__))

    # force include dir of dtsFile
    cppIncludes = ' -I ' + os.path.dirname(dtsFile)
    dtcIncludes = ' -i ' + os.path.dirname(dtsFile)

    for includeDir in incIncludes:
        cppIncludes += ' -I ' + includeDir
        dtcIncludes += ' -i ' + includeDir

    # cpp ${cpp_flags} ${cpp_includes} ${dtx} | ${DTC} ${dtc_flags} ${dtc_include} -I dts
    try:
        cpp = 'cpp'
        cppFlags = ' -nostdinc -undef -D__DTS__ -x assembler-with-cpp '
        cppResult = subprocess.run(cpp + cppIncludes + cppFlags + dtsFile,
                                   stdout=PIPE, stderr=PIPE, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print('EXCEPTION!', e)
        print('stdout: {}'.format(e.output.decode(sys.getfilesystemencoding())))
        print('stderr: {}'.format(e.stderr.decode(sys.getfilesystemencoding())))
        #exit(e.returncode)

    dtsPlugin = True if re.findall(r'\s*\/plugin\/\s*;', cppResult.stdout.decode('utf-8')) else False
    if dtsPlugin:
        print('DTS file is plugin')

    dtsShowDeletedSupport = True
    try:
        subprocess.run('dtc --comment-deleted -h', stdout=PIPE, stderr=PIPE, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print('WARNING!', 'dtc version doesn\'t support "comment-deleted" option')
        dtsShowDeletedSupport = False

    try:
        dtc = 'dtc'
        dtcFlags = ' -@ -I dts -O dts -f -s ' + (' -T ' * level) + ' -o - '
        if dtsShowDeletedSupport:
            dtcFlags += '--comment-deleted '
        dtcResult = subprocess.run(dtc + dtcIncludes + dtcFlags,
                                   stdout=PIPE, stderr=PIPE, input=cppResult.stdout, shell=True, check=True)

    except subprocess.CalledProcessError as e:
        print('EXCEPTION!', e)
        print('stdout: {}'.format(e.output.decode(sys.getfilesystemencoding())))
        print('stderr: {}'.format(e.stderr.decode(sys.getfilesystemencoding())))
        #exit(e.returncode)

    # Create a temporary file in the current working directory
    (tmpAnnotatedFile, tmpAnnotatedFileName) = tempfile.mkstemp(dir=out_dir,
                                                                prefix=getFileName(dtsFile) + '-annotated-',
                                                                suffix='.dts')

    print("test2", tmpAnnotatedFile, tmpAnnotatedFileName)


    with os.fdopen(tmpAnnotatedFile, 'w') as output:
        output.write(dtcResult.stdout.decode('utf-8') )

    return tmpAnnotatedFileName

class ConfigHelper:

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('dtv.conf')

    def load_config(self):
        """Load the configuration from 'dtv.conf'."""

        # If the config file does not exist, create a default one
        if not os.path.exists('dtv.conf'):
            self.load_default_config()
            self.save_config(self.config)
        else:
            self.config.read('dtv.conf')

        # If the 'dtv' section does not exist, create it with default values
        self.check_dtv_or_create()

        return self.config

    def load_default_config(self):
        """Return a default configuration for the dtv tool."""

        self.config = configparser.ConfigParser()

        # set default values for the 'dtv' section
        include_dir_stubs = ["include/", "scripts/dtc/include-prefixes/"]
        editor = "gedit $srcFileName +$srcLineNum"

        self.config['dtv'] = {
            'include_dir_stubs': json.dumps(include_dir_stubs),
            'editor_cmd': json.dumps(editor)
        }

    def set_include_dirs(self, include_dirs: list):
        """Set the include directories for the dtv tool."""
        self.check_dtv_or_create()

        self.config['dtv']['include_dir_stubs'] = json.dumps(include_dirs)

    def set_editor(self, editor: str):
        """Set the editor command for the dtv tool."""
        self.check_dtv_or_create()

        self.config['dtv']['editor_cmd'] = json.dumps(editor)

    def get_include_dirs(self):
        """Get the include directories from the dtv configuration."""
        self.check_dtv_or_create()

        include_dirs = self.config.get('dtv', 'include_dir_stubs')
        return ast.literal_eval(include_dirs)

    def get_editor(self):
        """Get the editor command from the dtv configuration."""
        self.check_dtv_or_create()

        editor = self.config.get('dtv', 'editor_cmd').replace('"', '').replace("'", "")
        return editor

    def check_dtv_or_create(self):
        """Check if a section exists in the config, or create it with default values."""
        if not self.config.has_section('dtv'):
            self.load_default_config()

    def save_config(self, config=None):
        """Save the configuration to 'dtv.conf'."""

        # If a config is provided, use it; otherwise, use the default config
        if config is not None:
            self.config = config

        # If no config is loaded, load the default config
        if self.config is None:
            self.load_default_config()

        # If the 'dtv' section does not exist, create it with default values
        self.check_dtv_or_create()

        with open('dtv.conf', 'w') as configfile:
            self.config.write(configfile)