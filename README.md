# isp-data-pollution docker script for headless pi
This is a docker container for the excellent ISP-data-pollution script (https://github.com/essandess/isp-data-pollution) tested to run on the raspberry pi 3b+ and 4b.

In order to have it running on your Pi follow the instructions below:
* Install docker (Optional: docker-compose) <br/>

* Build & run the container
```
docker build isp-pollution --tag isp-pollution
docker run -d -e gbpm=300 -e mem_lim=512 --name isp-pollution isp-pollution 
```
* (Optional) You can also use the following docker-compose code:<br/>
Note: Adjust your paths accordingly
```
version: "3.7"
services:
  isp-pollution:
    container_name: isp-pollution
    build:
      dockerfile: Dockerfile
      context: ./isp-pollution/
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
      - gbpm=300
      - mem_lim=512
    volumes:
      - /home/pi/isp/:/home/pi/isp/
    restart: always
```
