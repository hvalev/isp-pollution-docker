# Pollute your ISP browsing history
This is a dockerized version of script https://github.com/essandess/isp-data-pollution, which can obfuscate your browsing habits and prevent ISPs from easily interpreting your browsing data and building a profile of yourself. It is already known that some ISPs generate an additional profit by selling data of their users to third parties without obtaining consent [[1](https://github.com/essandess/isp-data-pollution)]. Using this script can act as a deterrent by polluting your browsing history with meaningless information. This method is not fool-proof as the noisy data can be separated from the genuine one without tremendous effort, but it would require some additional time and effort to do so. Ergo, if you're not a famous person or person of interest (for whatever reason), this should satisfy your needs. 

## Parameters
I have exposed two parameters from the original script -- bandwidth and memory usage to be settable as docker environment variables. </br>
`gbpm` - bandwidth usage, where 1024 corresponds to 1TB per month. </br>
`mem_lim` - limits the memory usage of the container.

## Docker
```
docker run -d --network host -e gbpm=300e me0m_lim=512 --name isp-pollution isp-pollution 
```
## Docker-compose

```
version: "3.7"
services:
  isp-pollution:
    container_name: isp-pollution
    build: https://github.com/hvalev/isp-pollution-docker.git
    network_mode: host
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
      - gbpm=300
      - mem_lim=512
    restart: always
```

## Info
A built container can be found @ https://hub.docker.com/repository/docker/hvalev/isp-pollution and is built for all architectures, but has been tested on a raspberry pi 3b+ and 4.

# How to build
```
docker build https://github.com/hvalev/isp-pollution-docker.git --tag isp-pollution
```
## Warning
The script uses python functions, which would be deprecated in versions >3.9. Hence it is not recommended to bump up the python version further.
