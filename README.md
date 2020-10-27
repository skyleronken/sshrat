# sshrat
 A simple SSH client providing RAT like functionality. 


connect [-u username] [-p password] [host] [port]

_disconnect

_tunnel add [listen_port] [connect_to] [connect_port] // forward tunnel
_tunnel add -r [listen_port] [connect_to] [connect_port] // reverse tunnel
_tunnel list
_tunnel del [index]

// all remote paths will be relative to the login directory. Best to use absolute paths.
_get [remote_path] [local_path] 
_put [local_path] [remote_path]
