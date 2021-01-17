FROM python:3.9-rc-alpine3.11

#install libraries for building libs [1-3], virtual display [4], chromium and chromedriver [5]
RUN apk update && apk upgrade && apk add --no-cache \
    make automake gcc g++ subversion python3-dev \
    libffi-dev openssl-dev sed git tzdata \
    xvfb fluxbox tmux x11vnc st xdpyinfo \ 
    chromium chromium-chromedriver

#Update pip and install isp pollution libraries
RUN python3 -m pip install --upgrade pip && \
    pip3 install numpy psutil requests selenium \
    fake_useragent pyopenssl pyvirtualdisplay

#Download and expose isp-data-pollution variables to docker container and allow headless
RUN git clone https://github.com/essandess/isp-data-pollution.git && \
    mv isp-data-pollution/isp_data_pollution.py ./isp-data-pollution.py && \
    rm -rf isp-data-pollution/ && \
    sed -i -e "s/gb_per_month\ =\ 100/gb_per_month\ =\ os.environ['GBPM']/g" \
           -e "s/browserdriver_rss_limit_mb\ =\ 1024/browserdriver_rss_limit_mb\ =\ os.environ['MEM']/g" \
           -e "s/chrome_options\.add_argument('headless')/chrome_options\.add_argument('headless')\n\            chrome_options.add_argument('no-sandbox')\n\            chrome_options.add_argument('disable-dev-shm-usage')/g" isp-data-pollution.py

#remove unnecessary packages
RUN apk del sed git make automake gcc g++ subversion

#set timezone
ENV TZ=Europe/Amsterdam
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENTRYPOINT ["python3", "isp-data-pollution.py"]