#!/usr/bin/python
#
# Copyright (c) 2014 Sylvain Peyrefitte
#
#
# dump_ftp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

"""
Dump ftp directory
"""

import sys, os, getopt, ssl, socket, re, errno, sha, shutil
from ftplib import FTP, FTP_TLS, error_perm

class FTP_TLS_EXPLICIT(FTP_TLS):
    """
    @summary: ftplib doesn't have explicit ssl port connection
                rewrite connect function of FTP_TLS class
    @see: http://svn.python.org/projects/python/trunk/Lib/ftplib.py
    """
    def connect(self, host='', port=0, timeout=-999):
        '''Connect to host.  Arguments are:
        - host: hostname to connect to (string, default previous host)
        - port: port to connect to (integer, default previous port)
        @see: http://svn.python.org/projects/python/trunk/Lib/ftplib.py
        '''
        if host != '':
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.af = self.sock.family
        self.sock = ssl.wrap_socket(self.sock, self.keyfile, self.certfile, ssl_version=self.ssl_version)
        self.file = self.sock.makefile('rb')
        self.welcome = self.getresp()
        return self.welcome
    
class FileDownloader(object):
    """
    @summary: Download ftp file
    """
    def __init__(self, file, size):
        """
        @param file: Target file object
        @param size: expected size
        """
        self.file = file;
        self.size = size
        self.receiveSize = 0
        self.sha = sha.new()
        self.sha.update("blob " + str(size) + "\0")
        
        
    def receive(self, data):
        """
        @summary: callback of ftplib
        @param data: binary data to record
        """
        self.receiveSize += len(data)
        self.file.write(data)
        
        #update fingerprint
        self.sha.update(data)
        
        #compute download state
        state = int(float(self.receiveSize)/float(self.size) * 100.0)
        
        sys.stdout.write("% 4d%%[%s]" % (state, ("=" * (state / 10) + " " * (10 - state / 10))))
        if self.receiveSize != self.size:
            sys.stdout.write("\r")
        else:
            sys.stdout.write(" (%s) \n"%self.sha.hexdigest())
        sys.stdout.flush()
        
class FolderParser(object):
    def __init__(self):
        self.sha = sha.new()
        self.infos = []
        self.msdos = re.compile('^(\d+\-\d+\-\d+\s+\d+:\d+(A|P)M)\s+(<DIR>|\d+)\s+(.*)$')
    def receive(self, data):
        #update fingerprint
        self.sha.update(data)
        m = self.msdos.match(data)
        self.infos.append((m.group(1), m.group(3), m.group(4)))
        

def mkdirs(path):
    """
    @summary: mkdirs with existed folder exception handler
    @param path: path to create
    """
    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise
        
        
class Dumper(object):
    """
    @summary: recursive dump context
    """
    def __init__(self, client, createEmptyDir, filter, detectLink):
        """
        @param client: ftplib client
        @param createEmptyDir: create empty directories
		@param filter: unix like filter on file name
        """
        self.client = client
        self.createEmptyDir = createEmptyDir
        self.filter = filter
        self.detectLink = detectLink
        self.folders = {}
        
    def do(self, targetDir):
        """
        @summary: Dump targetDir
		@param: target dir
        """
        folder = FolderParser()
        self.client.retrlines('LIST', folder.receive)
        srcDir = None
        #try to detect same folders
        shaFolder = folder.sha.hexdigest()
        if self.folders.has_key(shaFolder) and self.detectLink:
            srcDir = self.folders[shaFolder]
        else:
            self.folders[shaFolder] = targetDir
        
        for date, info, name in folder.infos:
            if info == '<DIR>':
                try:
                    newTargetDir = os.path.join(targetDir, name)
                    if self.createEmptyDir:
                        print "create %s"%newTargetDir
                        mkdirs(newTargetDir)
                        
                    self.client.cwd(name)
                    self.do(newTargetDir)
                    self.client.cwd('..')
                except error_perm:
                    print "\nERROR : unable to access directory %s\n"%(os.path.join(self.client.pwd(), name))
            else:
                if re.match(self.filter, name) is None:
                    continue
                
                targetFile = os.path.join(targetDir, name)
                
                mkdirs(os.path.dirname(targetFile))
                
                if not srcDir is None and os.path.exists(os.path.join(srcDir, name)):
                    srcFile = os.path.join(srcDir, name)
                    print "copy %s -> %s"%(srcFile, targetFile)
                    shutil.copy(srcFile, targetFile)
                    continue
                
                print "download %s"%targetFile
                try:
                    self.client.retrbinary('RETR %s'%name, FileDownloader(open(targetFile, 'wb'), int(info)).receive)
                except error_perm:
                    print "\nERROR : unable to access file %s\n"%(os.path.join(self.client.pwd(), name))

def help():
    print "Usage: dump_ftp.py [options] host[:port]"
    print "\t-u: user name [default : anonymous]"
    print "\t-p: password [default : anonymous@]"
    print "\t-d: target directory [default : /tmp]"
    print "\t-s: enable ssl [default : False]"
    print "\t-e: create empty directory [default : False]"  
    print "\t-f: unix like filter for file name [default : *]"
    print "\t-l: try to detect link folder [default : False]"

if __name__ == '__main__':
    
    #FTP over SSL state
    enableSSL = False
    
    #create empty directory
    createEmptyDirectory = False
    
    #username of session
    username = 'anonymous'
    
    #password of session
    password = 'anonymous@'
    
    #target dump dir
    targetDir = '/tmp'
    
    #filter on file name
    filter = ".*"
    
    #compute sha of list command and comprae to already visited folders
    detectLink = False
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "heslu:p:d:f:")
    except getopt.GetoptError:
        help()
    for opt, arg in opts:
        if opt == "-h":
            help()
            sys.exit()
        if opt == "-s":
            enableSSL = True
        if opt == "-u":
            username = arg
        if opt == "-p":
            password = arg
        if opt == "-d":
            targetDir = arg
        if opt == "-f":
            filter = arg
        if opt == "-e":
            createEmptyDirectory = True
        if opt == "-l":
            detectLink = True
            
    if ':' in args[0]:
        host, port = args[0].split(':')
    else:
        host, port = args[0], "21"
        
    #convert port as int
    port = int(port)
            
    if enableSSL:
        if port == 21:
            client = FTP_TLS(host)
            client.auth()
            client.prot_p()
        else:
            client = FTP_TLS_EXPLICIT()
            client.connect(host, port)
            client.prot_p()
    else:
        client = FTP()
        print client.connect(host, int(port))
        print client.login(username, password)
    
    #log
    client.login(username, password)
    Dumper(client, createEmptyDirectory, filter, detectLink).do(targetDir)
    client.quit()	
    