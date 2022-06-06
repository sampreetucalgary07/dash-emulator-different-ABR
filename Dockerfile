FROM python:3
LABEL author="Navid Akbari <anavid.akbari@gmail.com>"
LABEL version="0.1"
LABEL description="This is custom Docker image for the headless player."

RUN apt-get update && \
    apt-get -qq install -y git

COPY . /dash-emulator

WORKDIR /dash-emulator

RUN mkdir results

RUN pip install --no-cache-dir --upgrade pip 

RUN pip install .

RUN scripts/dash-emulator.py -h

#CMD ["dash-emulator.py", "172.17.0.2/test.mpd"]
