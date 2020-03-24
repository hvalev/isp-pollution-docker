FROM python:3.7-alpine3.9

#install libraries for building pip libs 
RUN apk update
RUN apk add --no-cache make automake gcc g++ subversion python3-dev
RUN apk add --no-cache libffi-dev openssl-dev

#install virtual display
RUN apk add --no-cache xvfb fluxbox tmux x11vnc st xdpyinfo
#install chromium and chromedriver
RUN apk add --no-cache chromium chromium-chromedriver

#update pip
RUN python3 -m pip install --upgrade pip

#isp-pollution libs
RUN pip3 install numpy psutil requests selenium fake_useragent pyopenssl

#install python virtual display driver 
RUN pip3 install pyvirtualdisplay

ENV TZ=Europe/Amsterdam
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ADD isp-data-pollution.py isp-data-pollution.py

#PUR pyhon params into docker container variables
ENTRYPOINT ["python3.7", "isp-data-pollution.py"]
