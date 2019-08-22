import os
import sys
import logging
import paramiko
import subprocess
from irrad_control import config_server_script


class ProcessManager(object):
    """
    Class to handle subprocesses created within irrad_control. Enables communication via SSH2 implementation of
    the paramiko library between host PC and Raspberry Pi server to run server process which handles the data
    acquisition, XY-stage etc.
    """
    
    def __init__(self):
        super(ProcessManager, self).__init__()

        # Server connection related
        self.server_ip = None
        self.server_uname = None
        self.client = None

        # Server process ID
        self.server_pid = None

        # Interpreter process
        self.interpreter_proc = None
        self.interpreter_pid = None

    def connect_to_server(self, hostname, username):

        # Update if we have no server credentials
        self.server_ip = hostname if self.server_ip is None else self.server_ip
        self.server_uname = username if self.server_uname is None else self.server_uname

        # Setup SSH client and connect to server
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        logging.info('Connecting to server {}@{}...'.format(username, hostname))

        # Try to connect
        try:
            self.client.connect(hostname=hostname, username=username)
        # Something went wrong
        except (paramiko.BadHostKeyException, paramiko.AuthenticationException, paramiko.SSHException) as e:
            # We need to add key, let user know
            if type(e) in (paramiko.BadHostKeyException,):
                msg = "Server's host key could not be verified. Try adding key via ssh-keygen and ssh-copy-id!"
                raise e(msg)
            else:
                raise e

        # Success
        logging.info('Successfully connected to server {}@{}!'.format(username, hostname))
        
    def configure_server(self, py_update=False, py_version=None, git_pull=False, branch=False):

        remote_script = '/home/{}/config_server.sh'.format(self.server_uname)

        # Move configure script to server
        self.copy_to_server(config_server_script, remote_script)

        # Add args
        _rs = remote_script
        _rs += ' -v={}'.format(sys.version_info[0] if py_version is None else py_version)
        _rs += ' -u' if py_update else ''
        _rs += ' -p' if git_pull else ''
        _rs += '' if not branch else ' -b={}'.format(branch)

        # Run script to determine wheter server Pi has miniconda and all packages installed
        self.exec_cmd('bash {}'.format(_rs), log_stdout=True)

        # Remove script
        self._exec_cmd('rm {}'.format(remote_script))
        
    def start_server_process(self, port):
        
        logging.info('Starting server process listening to port {}...'.format(port))
        
        self._exec_cmd('nohup bash start_irrad_server.sh {} &'.format(port))
        
    def kill_server(self):
        
        if self._server_pid:
        
            logging.info('Shutting down server process with PID {}...'.format(self._server_pid))
            
            self.exec_cmd('kill {}'.format(self._server_pid))
            
        else:
            
            self.exec_cmd('killall python')
        
    def set_server_pid(self, pid):
        
        logging.info('Server process running with PID {}'.format(pid))
        
        self._server_pid = pid

    def _call_subprocess(self, cmd, script, args):

        return subprocess.Popen('{} {} {}'.format('python' if not cmd else cmd, script, args),
                                shell=True,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)

    def _exec_cmd(self, cmd, log_stdout=False):
        """Execute command on server using paramikos SSH implementation"""

        # Sanity check
        if self.client is None:
            logging.warning("SSH-client not connected to server. Call {}.connect_to_server method."
                            .format(self.__class__.__name__))
            return
        
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
