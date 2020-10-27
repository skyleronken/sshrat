import threading
import socket
import selectors
import time
import socketserver
import paramiko

class Tunnel():
    
    def __init__(self, ssh_session, tun_type, lhost, lport, dhost, dport):
        self.tun_type = tun_type
        self.lhost = lhost
        self.lport = lport
        self.dhost = dhost
        self.dport = dport

        # create tunnel here
        if self.tun_type == ForwardTunnel:
            self.tunnel = ForwardTunnel(ssh_session, self.lhost, self.lport, self.dhost, self.dport)
        elif self.tun_type == ReverseTunnel:
            self.tunnel = ReverseTunnel(ssh_session, self.lhost, self.lport, self.dhost, self.dport)
    
    def to_str(self):
        if self.tun_type == ForwardTunnel:
            return f"{self.lhost}:{self.lport} --> {self.dhost}:{self.dport}"
        else:
            return f"{self.dhost}:{self.dport} <-- {self.lhost}:{self.lport}"

    def stop(self):
        self.tunnel.stop()

class ReverseTunnel():

    def __init__(self, ssh_session, lhost, lport, dhost, dport):
        self.session = ssh_session
        self.lhost = lhost
        self.lport = lport
        self.dhost = dhost
        self.dport = dport

        self.transport = ssh_session.get_transport()

        self.reverse_forward_tunnel(lhost, lport, dhost, dport, self.transport)
        self.handlers = []

    def stop(self):
        self.transport.cancel_port_forward(self.lhost, self.lport)
        for thr in self.handlers:
            thr.stop()

    def handler(self, rev_socket, origin, laddress):
        rev_handler = ReverseTunnelHandler(rev_socket, self.dhost, self.dport, self.lhost, self.lport)
        rev_handler.setDaemon(True)
        rev_handler.start()
        self.handlers.append(rev_handler)

    def reverse_forward_tunnel(self, lhost, lport, dhost, dport, transport):
        try:
            transport.request_port_forward(lhost, lport, handler=self.handler)
        except Exception as e:
            raise e

class ReverseTunnelHandler(threading.Thread):

    def __init__(self, rev_socket, dhost, dport, lhost, lport):

        threading.Thread.__init__(self)

        self.rev_socket = rev_socket
        self.dhost = dhost
        self.dport = dport
        self.lhost = lhost
        self.lport = lport

        self.dst_socket = socket.socket()
        try:
            self.dst_socket.connect((self.dhost, self.dport))
        except Exception as e:
            raise e

        self.keepalive = True

    def _read_from_rev(self, dst, rev):
        self._transfer_data(src_socket=rev,dest_socket=dst)

    def _read_from_dest(self, dst, rev):
        self._transfer_data(src_socket=dst,dest_socket=rev)

    def _transfer_data(self,src_socket,dest_socket):
        dest_socket.setblocking(False)
        data = src_socket.recv(1024)

        if len(data):
            try:
                dest_socket.send(data)
            except Exception as e:
                print(e)

    def stop(self):
        self.rev_socket.shutdown(2)
        self.dst_socket.shutdown(2)
        self.rev_socket.close()
        self.dst_socket.close()
        self.keepalive = False

    def run(self):
        selector = selectors.DefaultSelector()

        selector.register(fileobj=self.rev_socket,events=selectors.EVENT_READ,data=self._read_from_rev)
        selector.register(fileobj=self.dst_socket,events=selectors.EVENT_READ,data=self._read_from_dest)

        while self.keepalive:
            events = selector.select(5)
            if len(events) > 0:
                for key, _ in events:
                    callback = key.data
                    try:
                        callback(dst=self.dst_socket,rev=self.rev_socket)
                    except Exception as e:
                        print(e)
                time.sleep(0)



# credits to paramiko-tunnel
class ForwardTunnel(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, ssh_session, lhost, lport, dhost, dport):
        self.session = ssh_session
        self.lhost = lhost
        self.lport = lport
        self.dhost = dhost
        self.dport = dport

        super().__init__(
            server_address=(lhost, lport),
            RequestHandlerClass=ForwardTunnelHandler,
            bind_and_activate=True,
        )

        self.baddr, self.bport = self.server_address
        self.thread = threading.Thread(
            target=self.serve_forever,
            daemon=True,
        )

        self.start()

    def start(self):
        self.thread.start()

    def stop(self):
        self.shutdown()
        self.server_close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

class ForwardTunnelHandler(socketserver.BaseRequestHandler):
    sz_buf = 1024

    def __init__(self, request, cli_addr, server):
        self.selector = selectors.DefaultSelector()
        self.channel = None
        super().__init__(request, cli_addr, server)

    def _read_from_client(self, sock, mask):
        self._transfer_data(src_socket=sock, dest_socket=self.channel)

    def _read_from_channel(self, sock, mask):
        self._transfer_data(src_socket=sock,dest_socket=self.request)

    def _transfer_data(self,src_socket,dest_socket):
        src_socket.setblocking(False)
        data = src_socket.recv(self.sz_buf)

        if len(data):
            try:
                dest_socket.send(data)
            except BrokenPipeError:
                self.finish()

    def handle(self):
        peer_name = self.request.getpeername()
        try:
            self.channel = self.server.session.get_transport().open_channel(
                kind='direct-tcpip',
                dest_addr=(self.server.dhost,self.server.dport,),
                src_addr=peer_name,
            )
        except Exception as error:
            msg = f'Connection failed to {self.server.dhost}:{self.server.dport}'
            raise Exception(msg)
        
        else:
            self.selector.register(fileobj=self.channel,events=selectors.EVENT_READ,data=self._read_from_channel)
            self.selector.register(fileobj=self.request,events=selectors.EVENT_READ,data=self._read_from_client)

            if self.channel is None:
                self.finish()
                raise Exception(f'SSH Server rejected request to {self.server.dhost}:{self.server.dport}')

            while True:
                events = self.selector.select()
                for key, mask in events:
                    callback = key.data
                    callback(sock=key.fileobj,mask=mask)
                    if self.server._BaseServer__is_shut_down.is_set():
                        self.finish()
                time.sleep(0)

    def finish(self):
        if self.channel is not None:
            self.channel.shutdown(how=2)
            self.channel.close()
        self.request.shutdown(2)
        self.request.close()