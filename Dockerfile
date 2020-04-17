FROM python:3.7-alpine3.9

#install libraries for building pip libs 
RUN apk update && apk upgrade
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

#download and modify original script
RUN apk add sed git
RUN git clone https://github.com/essandess/isp-data-pollution.git
RUN mv isp-data-pollution/isp_data_pollution.py ./isp-data-pollution.py
RUN rm -rf isp-data-pollution/
RUN sed -i "s/gb_per_month\ =\ 100/gb_per_month\ =\ os.environ['gbpm']/g" isp-data-pollution.py
RUN sed -i "s/browserdriver_rss_limit_mb\ =\ 1024/browserdriver_rss_limit_mb\ =\ os.environ['mem_lim']/g" isp-data-pollution.py
RUN sed -i "s/chrome_options\.add_argument('headless')/chrome_options\.add_argument('headless')\n\            chrome_options.add_argument('no-sandbox')\n\            chrome_options.add_argument('disable-dev-shm-usage')/g" isp-data-pollution.py

#remove unnecessary packages
RUN apk del sed git make automake gcc g++ subversion

#since on alpine we need tzdata
RUN apk add --no-cache tzdata
ENV TZ=Europe/Amsterdam
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENTRYPOINT ["python3.7", "isp-data-pollution.py"]
