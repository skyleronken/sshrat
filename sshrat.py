#!/usr/bin/env python3
import argparse
from ssh2.session import Session
import cmd2
import socket
import os
import sys

# TODO
# - Create and track tunnels
# - Upload/Download (multiple techniques in addition to scp)
# - Run scripts
# - Record all output
# - Auto unset histories, etc
# - Aliases for local scripts

class SSHRat(cmd2.Cmd):
    intro = '>> SSH RAT >>\n'
    prompt = '$ ' 

    def __init__(self):
        super().__init__()
        
        self.debug = True
        self.channel = None

        self.download_dir = os.getcwd()
        self.add_settable(cmd2.Settable('download_dir', str, 'Default destination location of downloaded files'))

    ## functionality 

    def do_connect(self, args):
        """
        
        """
        self.host = args.arg_list[0]
        self.port = int(args.arg_list[1])
        self.un = args.arg_list[2]
        self.pw = args.arg_list[3]

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))

            session = Session()
            session.handshake(sock)
            session.userauth_password(self.un, self.pw)

            self.channel = session.open_session()
            self.channel.pty()
            print("Session opened")
        except Exception as e:
            print(f"Failed to open session: {e}")

    def do__tunnel(self, args):
        """
        show tunnels"
        """
        pass

    def do__get(self, args):
        """
        download a file from target
        """
        pass

    def do__put(self, args):
        """
        upload a file to the target
        """
        pass

    ## usability features

    def do__exit(self, args):
        """
        exits everything
        """
        return -1

    def preloop(self):
        """
        Initialization before prompting user for commands.
        Unset histories, etc
        Despite the claims in the Cmd documentaion, Cmd.preloop() is not a stub.
        """
        cmd2.Cmd.preloop(self)   ## sets up command completion

    def postloop(self):
        """
        Cleanup before exiting
        """
        cmd2.Cmd.postloop(self)   ## Clean up command completion
        if self.channel is not None:
            self.channel.close()

    def do_shell(self, args):
        """
        Pass command to a system shell when line begins with '!'
        """
        os.system(args)

    def send_command(self, command):
        if self.channel is None:
            print("No channel")
            return

        self.channel.execute(command)
        size, data = self.channel.read()
        while size > 0:
            print(data.decode(), end='')
            #size, next_data = self.channel.read()
            #data = data + next_data
            size, data = self.channel.read()

        #print(data.decode())
        self.channel.get_exit_status()
        self.channel.flush()

    def default(self, statement):
        """
        Pass this as command to SSH 
        """
        if len(statement.raw) > 0:
            self.send_command(statement.raw)

if __name__ == "__main__":

    c = SSHRat()
    sys.exit(c.cmdloop())
