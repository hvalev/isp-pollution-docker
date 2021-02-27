# Pollute your ISP browsing history

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/hvalev/isp-pollution-docker/build)
![Docker Pulls](https://img.shields.io/docker/pulls/hvalev/isp-pollution)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/hvalev/isp-pollution)

This is a dockerized version of the [isp-pollution script](https://github.com/essandess/isp-data-pollution) by [essandess](https://github.com/essandess/). It obfuscates your real browsing history by generating faux webpage requests. This approach increases your privacy by using the [security through obscurity](https://en.wikipedia.org/wiki/Security_through_obscurity) princple. The generated fake requests will make it more difficult for your ISP to interpret your browsing history and build a profile of yourself. This approach, however, is not fool-proof as a knowledgeable person would be able to disentagle genuine requests from the fakes. Ergo, if you're not a famous person or person of interest (for whatever reason), this should satisfy most of your needs. 

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

## How to build
```
docker build https://github.com/hvalev/isp-pollution-docker.git --tag isp-pollution
```

## Warning
The script uses python functions, which would be deprecated in versions >3.9. Hence it is not recommended to bump up the python version further.
