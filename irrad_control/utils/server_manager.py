import os
import time
import logging
import paramiko
import subprocess
import tarfile
from irrad_control import package_path, server_path


class ServerManager(object):
    """
    Class to enable communication via SSH2 implementation of the paramiko library between host PC and
    Raspberry Pi server. This class implements methods to prepare, start and monitor the server process
    which handles the data acquisition and stage. 
    """
    
    def __init__(self, hostname, username='pi'):
        super(ServerManager, self).__init__()
        
        # Input
        self.hname = hostname
        self.uname = username
        
        # Server process ID
        self._server_pid = None
        
        # Setup SSH client and connect to server
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        logging.info('Connecting to server {}@{}...'.format(username, hostname))
        
        try:
            self.client.connect(hostname=hostname, username=username)
        except (paramiko.BadHostKeyException, paramiko.AuthenticationException, paramiko.SSHException) as e:
            
            if type(e) in (paramiko.BadHostKeyException):
                msg = "Server's host key could not be verified. Try adding key via ssh-keygen and ssh-copy-id!"
                raise e(msg)
            else:
                raise e
            
        logging.info('Successfully connected to server {}@{}!'.format(username, hostname))
        
    def prepare_server(self):
        """Prepares the server by copying the all neccesarry files to it and executing check scripts"""
        
        # Server locations and files
        self.remote_path = '/home/{}/server/'.format(self.uname)
        self.archive = 'server.tgz'
        
        logging.info('Creating archive {} ...'.format(self.archive))
        
        # Removing old server folder and making new
        self.exec_cmd('rm -rf {}'.format(self.remote_path))
        self.exec_cmd('mkdir {}'.format(self.remote_path))
        
        archive_path = os.path.join(package_path, self.archive)
        
        with tarfile.open(archive_path, 'w:gz') as tgz:
            tgz.add(server_path, arcname=os.path.sep)
           
        logging.info('Copying {} to {}@{}...'.format(self.archive, self.uname, self.hname))
        
        self.copy_to_server(archive_path, self.remote_path + self.archive)
        
        logging.info('Unpacking server.tgz on server...')
        
        self.exec_cmd('cd {}; tar -xzf server.tgz'.format(self.remote_path, self.uname))
        
        logging.info('Done')
        
        # Remove archive on host PC
        self._call_subprocess(['rm', archive_path])
        
        # Run script to determine wheter server Pi has miniconda and all packages installed
        self.exec_cmd('bash {}/setup_server.sh'.format(self.remote_path), log_stdout=True)
        
    def start_server_process(self, port):
        
        logging.info('Starting server process listening to port {}...'.format(port))
        
        self.exec_cmd('source /home/pi/miniconda/bin/activate; nohup python {}/server.py {} &'.format(self.remote_path, port))
        
    def kill_server(self):
        
        if self._server_pid:
        
            logging.info('Shutting down server process with PID {}...'.format(self._server_pid))
            
            self.exec_cmd('kill {}'.format(self._server_pid))
            
        else:
            
            self.exec_cmd('killall python')
        
    def set_server_pid(self, pid):
        
        logging.info('Server process running with PID {}'.format(pid))
        
        self._server_pid = pid
        
    def _call_subprocess(self, cmd_list):
        """Calls subprocess"""
        p = subprocess.Popen(cmd_list)
        
        while p.poll() is None:
            time.sleep(0.1)
            
    def exec_cmd(self, cmd, log_stdout=False):
        """Execute command on server using paramikos SSH implementation"""
        
        # Execute; this is non-blocking so we have to wait until cmd has been transmitted to server before closing
        stdin, stdout, stderr = self.client.exec_command(cmd)
        
        # No writing to stdin and stdout happens
        stdin.close()
        stdout.channel.shutdown_write()
        
        if log_stdout:
            while not stdout.channel.exit_status_ready():
                msg = stdout.readline().strip()
                if msg:
                    logging.info(msg)
                
        stdout.close()
        stderr.close()
            
    def copy_to_server(self, local_filepath, remote_filepath):
        """Copy local file at local_filepath to server at remote_filepath"""
        
        sftp = self.client.open_sftp()
        sftp.put(local_filepath, remote_filepath)
        sftp.close()
