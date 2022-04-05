FROM python:3-slim-buster

RUN /usr/local/bin/python -m pip install --upgrade pip  
RUN pip3 install "pyTenable>=1.4.3" python-decouple requests BeautifulSoup4 phpserialize jinja2 lxml
RUN apt-get update; apt-get -y upgrade

RUN useradd -ms /bin/bash vulnfeed

COPY templates /home/vulnfeed/templates
RUN chown -R vulnfeed:vulnfeed /home/vulnfeed/templates

COPY cisa_kev.py /
RUN chmod +x /cisa_kev.py && chown vulnfeed:vulnfeed /cisa_kev.py

RUN export PYTHONUNBUFFERED=1
ENTRYPOINT ["/cisa_kev.py"]

USER vulnfeed
WORKDIR /home/vulnfeed

HEALTHCHECK NONE
