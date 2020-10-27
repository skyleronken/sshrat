# sshrat
 A simple SSH client providing RAT like functionality. 

## connect
connect [-u username] [-p password] [host] [port]

## disconnect
_disconnect

## forward tunnel
_tunnel add [listen_port] [connect_to] [connect_port] 

## reverse tunnel
_tunnel add -r [listen_port] [connect_to] [connect_port]

## list tunnels
_tunnel list

## remove a tunnel
_tunnel del [index]

## download file
_get [remote_path] [local_path] 
* all remote paths will be relative to the login directory. Best to use absolute paths.

## upload file
_put [local_path] [remote_path]

* all remote paths will be relative to the login directory. Best to use absolute paths.

