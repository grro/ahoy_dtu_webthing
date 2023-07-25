# ahoy_dtu_webthing
A webthing adapter to provide the [AhyoDTU](https://ahoydtu.de/)  interface via the [webthing API](https://iot.mozilla.org/wot/).

Example
```
# webthing has been started on host 192.168.0.23

curl http://192.168.0.23:7122/0/properties 

{
   "name": "Terrasse",
   "serial": "114180123418",
   "p_dc": 23
   ....
}
```

To install this software you can use [PIP](https://realpython.com/what-is-pip/) package manager as shown below
```
sudo pip install ahoy_dtu_webthing
```

After this installation you can use the Webthing http endpoint in your Python code or from the command line with
```
sudo dtu --command listen --port 7122 --base_uri http://10.1.11.35/
```
Here the webthing API is bound to the local port 7122. Additionally, the base uri of the AhyoDTU REST api must be set. 

As an alternative to the *list* command, you can also use the *register* command to register and start the webthing service as a systemd entity.
This way, the webthing service is started automatically at boot time. Starting the server manually with the *listen* command is no longer necessary.
```
sudo dtu --command register --port 7122 --base_uri http://10.1.11.35/
```  
