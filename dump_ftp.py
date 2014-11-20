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

import sys, os, getopt, ssl, socket, re, errno, sha
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
    
class Downloader(object):
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
        
        sys.stdout.write("% 4d%%[%s]" % (state, ("=" * (state) + " " * (100 - state))))
        if self.receiveSize != self.size:
            sys.stdout.write("\r")
        else:
            sys.stdout.write(" (%s) \n"%self.sha.hexdigest())
        sys.stdout.flush()
        
    
def listCommandMSDOS(client):
    """
    @summary: return formated result of list command
    @return: list(tuple(date, [<DIR> | fileSize], fileName)]
    """
    files = []
    client.retrlines('LIST', files.append)
    result = []
    prog = re.compile('^(\d+\-\d+\-\d+\s+\d+:\d+(A|P)M)\s+(<DIR>|\d+)\s+(.*)$')
    for f in files:
        m = prog.match(f)
        result.append((m.group(1), m.group(3), m.group(4)))
        
    return result

def mkdirs(path):
    """
    @summary: mkdis with existed folder exception handler
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
    def __init__(self, client, createEmptyDir):
        """
        @param client: ftplib client
        @param createEmptyDir: create empty directories
        """
        self.client = client
        self.createEmptyDir = createEmptyDir
        
    def do(self, targetDir):
        """
        @summary: Dump curentDir into targetDir
        """
        for date, info, name in listCommandMSDOS(self.client):
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
                    print "unable to access directory %s"%name
            else:
                targetFile = os.path.join(targetDir, name)
                print "download %s"%targetFile
                mkdirs(os.path.dirname(targetFile))
                
                self.client.retrbinary('RETR %s'%name, Downloader(open(targetFile, 'wb'), int(info)).receive)

def help():
    print "Usage: dump_ftp.py [options] host[:port]"
    print "\t-u: user name [default : anonymous]"
    print "\t-p: password [default : anonymous@]"
    print "\t-d: target directory [default : /tmp]"
    print "\t-s: enable ssl [default : False]"
    print "\t-e: create empty directory [default : False]"               

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
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hesu:p:d:")
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
        if opt == "-e":
            createEmptyDirectory = True
            
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
    Dumper(client, createEmptyDirectory).do(targetDir)
            
    