FROM alpine:3.16.2
#selenium fake_useragent pyvirtualdisplay
COPY requirements.txt ./
#Download and expose isp-data-pollution variables to docker container and allow headless
RUN apk update && apk add --no-cache \
    xvfb git sed tzdata chromium chromium-chromedriver \
    py3-numpy py3-requests py3-psutil py3-openssl py3-pip && \
    python3 -m pip install --upgrade pip && \
    pip3 install -U -r requirements.txt && \
    git clone https://github.com/essandess/isp-data-pollution.git && \
    mv isp-data-pollution/isp_data_pollution.py ./isp-data-pollution.py && \
    rm -rf isp-data-pollution/ && \
    sed -i -e "s/gb_per_month\ =\ 100/gb_per_month\ =\ os.environ['GBPM']/g" \
           -e "s/browserdriver_rss_limit_mb\ =\ 1024/browserdriver_rss_limit_mb\ =\ os.environ['MEM']/g" \
           -e "s/chrome_options\.add_argument('headless')/chrome_options\.add_argument('headless')\n\            chrome_options.add_argument('no-sandbox')\n\            chrome_options.add_argument('disable-dev-shm-usage')/g" \
           isp-data-pollution.py && \
    apk del git sed

ENTRYPOINT ["python3", "isp-data-pollution.py"]