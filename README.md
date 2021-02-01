# Pollute your ISP browsing history

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/hvalev/isp-pollution-docker/ci)
![Docker Pulls](https://img.shields.io/docker/pulls/hvalev/isp-pollution)
![Docker Stars](https://img.shields.io/docker/stars/hvalev/isp-pollution)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/hvalev/isp-pollution)

This is a dockerized version of the script [isp-pollution](https://github.com/essandess/isp-data-pollution) by [essandess](https://github.com/essandess/), which can obfuscate your browsing habits and prevent ISPs from easily interpreting your browsing data and building a profile of yourself. It is already known that some ISPs generate an additional profit by selling data of their users to third parties without obtaining consent (see link above). Using this script can act as a deterrent by polluting your browsing history with meaningless information. This method is not fool-proof as the noisy data can be separated from the genuine one moderately by a knowledgable person. Ergo, if you're not a famous person or person of interest (for whatever reason), this should satisfy most of your needs. 

## Parameters
I have exposed two parameters from the original script -- bandwidth and memory usage to be user-configurable as docker environment variables. </br>
`GBPM` - bandwidth usage, where 1024 corresponds to 1TB per month. </br>
`MEM` - limits the memory usage of the container.

## Docker
```
docker run -d --network host -e GBPM=300 -e MEM=512 --name isp-pollution hvalev/isp-pollution
```
## Docker-compose

```
version: "3.7"
services:
  isp-pollution:
    container_name: isp-pollution
    image: hvalev/isp-pollution
    network_mode: host
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
      - GBPM=300
      - MEM=512
    restart: always
```

## Info
A built container can be found @ https://hub.docker.com/repository/docker/hvalev/isp-pollution and was tested on a raspberry pi 3b+ and 4.

## How to build
```
docker build https://github.com/hvalev/isp-pollution-docker.git --tag isp-pollution
```
## Warning
The script uses python functions, which would be deprecated in versions >3.9. Hence it is not recommended to bump up the python version further.
