import os
import sys
import logging
import paramiko
import subprocess
from irrad_control import package_path, config_server_script


class ProcessManager(object):
    """
    Class to handle subprocesses created within irrad_control. Enables communication via SSH2 implementation of
    the paramiko library between host PC and Raspberry Pi server to run server process which handles the data
    acquisition, XY-stage etc.
    """
    
    def __init__(self):
        super(ProcessManager, self).__init__()

        # Server connection related; multiple servers can exist
        self.server = {}
        self.client = {}

        # Interpreter process; only one
        self.interpreter_proc = None

        # Keep track of processes which have been started
        self.current_procs = []

    def connect_to_server(self, hostname, username):

        # Update if we have no server credentials
        if hostname not in self.server:

            # Update server dict
            self.server[hostname] = username

        if hostname not in self.client:

            # Setup SSH client and connect to server
            self.client[hostname] = paramiko.SSHClient()
            self.client[hostname].set_missing_host_key_policy(paramiko.AutoAddPolicy())

            logging.info('Connecting to server {}@{}...'.format(username, hostname))

            # Try to connect
            try:
                self.client[hostname].connect(hostname=hostname, username=username)
            # Something went wrong
            except (paramiko.BadHostKeyException, paramiko.AuthenticationException, paramiko.SSHException) as e:
                # We need to add key, let user know
                if type(e) is paramiko.BadHostKeyException:
                    msg = "Server's host key could not be verified. Try creating key on host PC via" \
                          " ssh-keygen and copy to server via ssh-copy-id!"
                    raise e(msg)
                else:
                    raise e

            # Success
            logging.info('Successfully connected to server {}@{}!'.format(username, hostname))

        else:

            logging.info('Already connected to server {}@{}!'.format(username, hostname))
        
    def configure_server(self, hostname, py_version=None, py_update=False, git_pull=False, branch=False):

        remote_script = '/home/{}/config_server.sh'.format(self.server[hostname])

        # Move configure script to server
        self.copy_to_server(hostname, config_server_script, remote_script)

        # Add args
        _rs = remote_script
        _rs += ' -v={}'.format(sys.version_info[0] if py_version is None else py_version)
        _rs += ' -u' if py_update else ''
        _rs += ' -p' if git_pull else ''
        _rs += '' if not branch else ' -b={}'.format(branch)

        # Run script to determine whether server RPi has miniconda and all packages installed
        self._exec_cmd(hostname, 'bash {}'.format(_rs), log_stdout=True)

        # Remove script
        self._exec_cmd(hostname, 'rm {}'.format(remote_script))
        
    def start_server_process(self, hostname, port):
        
        logging.info('Starting server process listening to port {}...'.format(port))
        
        self._exec_cmd(hostname, 'nohup bash /home/{}/start_irrad_server.sh {} &'.format(self.server[hostname], port))

    def start_interpreter_process(self, setup_yaml):

        logging.info('Starting interpreter process...')

        self.interpreter_proc = self._call_script(script=os.path.join(package_path, 'irrad_interpreter.py'), args=setup_yaml)

    def _call_script(self, script, args, cmd=None):

        # Call the interpreter subprocess with the same python executable that runs irrad_control
        return subprocess.Popen('{} {} {}'.format(sys.executable if not cmd else cmd, script, args),
                                shell=True,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)

    def _exec_cmd(self, hostname, cmd, log_stdout=False):
        """Execute command on server using paramikos SSH implementation"""

        # Sanity check
        if hostname not in self.client:
            logging.warning("SSH-client not connected to server. Call {}.connect_to_server method."
                            .format(self.__class__.__name__))
            return
        
        # Execute; this is non-blocking so we have to wait until cmd has been transmitted to server before closing
        stdin, stdout, stderr = self.client[hostname].exec_command(cmd)
        
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

    def copy_to_server(self, hostname, local_filepath, remote_filepath):
        """Copy local file at local_filepath to server at remote_filepath"""

        sftp = self.client[hostname].open_sftp()
        sftp.put(local_filepath, remote_filepath)
        sftp.close()

    def kill_pid(self, pid, hostname=False):

        # We're killing a process on a server
        if hostname:

            logging.info('Killing server PC process with PID {}...'.format(pid))

            self._exec_cmd(hostname, 'kill {}'.format(pid))

        else:

            logging.info('Killing host PC process with PID {}...'.format(pid))

            subprocess.Popen(['kill', pid])
