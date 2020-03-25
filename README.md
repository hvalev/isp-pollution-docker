# isp-data-pollution docker script for headless pi
This is a docker container for the excellent ISP-data-pollution script (https://github.com/essandess/isp-data-pollution) tested to run on the raspberry pi 3b+ and 4b.

In order to have it running on your Pi follow the instructions below:
* Install docker (Optional: docker-compose) <br/>
There are countless tutorials online on how to do that
* Download the isp-data-pollution script and docker containers from the essandess repository
```
git clone https://github.com/hvalev/isp-pollution-docker.git
git clone https://github.com/hvalev/isp-pollution-docker.git
mv isp-pollution-docker/Dockerfile isp-pollution/Dockerfile
```
* Identify the following lines in the isp-data-pollution.py script
```
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('headless')
```
* Append the following two lines, so that the code looks as following (mind the identation)    
```
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('headless')
chrome_options.add_argument('no-sandbox')
chrome_options.add_argument('disable-dev-shm-usage')
```
* Build & run the container
```
docker build isp-pollution --tag isp-pollution
docker run -d --name isp-pollution isp-pollution 
```
* (Optional) You can also use the following docker-compose code:<br/>
Note: Adjust your paths accordingly
```
version: "3.7"
services:
  isp-pollution:
    container_name: isp-pollution
    build:
      dockerfile: /home/pi/isp-pollution/Dockerfile
      context: /home/pi/isp-pollution/
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
    volumes:
      - /home/pi/isp/:/home/pi/isp/
    restart: always
```
